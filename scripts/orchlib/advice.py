"""Advice for the person running the owner: when to compact or clear the owner's
context, when to hand the owner role to another agent, when the template has a
new release. Read-only: it suggests, the person decides.

Context size drives cost: every owner request resends the whole context, so a
200k-token context costs about five times a 40k one per request.
"""

import json
import os
import re
import subprocess
import time
import tomllib
from pathlib import Path

from . import quota

SESSIONS = "owner-sessions"  # per-session context snapshots, one file per session


def settings(cfg):
    a = cfg["routing"].get("advice", {})
    return {
        "compact_tokens": a.get("compact_tokens", 100_000),
        "clear_tokens": a.get("clear_tokens", 160_000),
        "owner_switch_percent": a.get("owner_switch_percent", 10),
        "handoff_max_age_minutes": a.get("handoff_max_age_minutes", 120),
        "update_check_hours": a.get("update_check_hours", 24),
    }


# ---------------------------------------------------------------- owner context


def record_session(data, now=None):
    """Called by the Claude statusline tap: keep the context size per session."""
    cw = data.get("context_window") or {}
    tokens = None
    cur = cw.get("current_usage") or {}
    if cur:
        tokens = sum(
            int(cur.get(k) or 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
    elif cw.get("used_percentage") is not None and cw.get("context_window_size"):
        tokens = int(cw["used_percentage"] * cw["context_window_size"] / 100)
    if tokens is None and data.get("transcript_path"):
        tokens = transcript_tokens(data["transcript_path"])
    sid = str(data.get("session_id") or "unknown")
    root = (data.get("workspace") or {}).get("project_dir") or data.get("cwd")
    snap = {
        "observed_at": now or time.time(),
        "session_id": sid,
        "root": root,
        "tokens": tokens,
        "window": cw.get("context_window_size"),
        "model": (data.get("model") or {}).get("id"),
    }
    d = quota.CACHE_DIR / SESSIONS
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{sid}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps(snap))
    tmp.replace(d / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', sid)}.json")


def transcript_tokens(path, tail=400_000):
    """Last request's context from a Claude transcript (fallback when the
    statusline input has no context_window)."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, os.path.getsize(path) - tail))
            lines = f.read().decode(errors="ignore").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            u = (json.loads(line).get("message") or {}).get("usage")
        except (json.JSONDecodeError, AttributeError):
            continue
        if u:
            return sum(
                int(u.get(k) or 0)
                for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
            )
    return None


def claude_context(root, max_age=900, now=None):
    now = now or time.time()
    best = None
    for p in (quota.CACHE_DIR / SESSIONS).glob("*.json"):
        try:
            s = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if (
            s.get("root")
            and Path(s["root"]).resolve() == Path(root).resolve()
            and now - s["observed_at"] < max_age
        ):
            if best is None or s["observed_at"] > best["observed_at"]:
                best = s
    return best


def codex_context(root, now=None, max_age=900):
    """Codex owner: the newest rollout whose cwd is the project root."""
    now = now or time.time()
    base = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
    files = sorted(
        base.glob("*/*/*/rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )[:20]
    for p in files:
        if now - p.stat().st_mtime > max_age:
            break
        try:
            with open(p) as f:
                meta = json.loads(f.readline()).get("payload") or {}
            if Path(meta.get("cwd", "/nonexistent")).resolve() != Path(root).resolve():
                continue
            with open(p, "rb") as f:
                f.seek(max(0, p.stat().st_size - 300_000))
                lines = f.read().decode(errors="ignore").splitlines()
        except (OSError, json.JSONDecodeError):
            continue
        for line in reversed(lines):
            try:
                pl = json.loads(line).get("payload") or {}
            except json.JSONDecodeError:
                continue
            info = pl.get("info") if pl.get("type") == "token_count" else None
            if info:
                u = info.get("last_token_usage") or {}
                return {
                    "observed_at": p.stat().st_mtime,
                    "session_id": p.stem,
                    "root": str(root),
                    "tokens": u.get("input_tokens"),
                    "window": info.get("model_context_window"),
                    "model": None,
                }
    return None


def owner_context(cfg, now=None):
    kind = cfg["agents"][cfg["routing"]["owner"]].get("quota")
    if kind == "claude":
        return claude_context(cfg["root"], now=now)
    if kind == "codex":
        return codex_context(cfg["root"], now=now)
    return None  # other runtimes: no context telemetry yet


# ---------------------------------------------------------------- handoff (GSD pause-work)


def handoff(root):
    """GSD's own handoff: /gsd-pause-work writes .planning/HANDOFF.json."""
    p = Path(root) / ".planning" / "HANDOFF.json"
    try:
        return {"path": str(p), "mtime": p.stat().st_mtime}
    except OSError:
        return None


# ---------------------------------------------------------------- template updates


def template_info(root):
    try:
        return tomllib.loads((Path(root) / ".orchestration" / "template.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _ver(s):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", s.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def latest_release(upstream, max_age_h=24, now=None):
    """Newest vX.Y.Z tag of the template upstream, cached per upstream."""
    now = now or time.time()
    cache = quota.CACHE_DIR / "template-release.json"
    try:
        c = json.loads(cache.read_text())
        if c.get("upstream") == upstream and now - c["checked_at"] < max_age_h * 3600:
            return c.get("latest")
    except (OSError, json.JSONDecodeError, KeyError):
        pass
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", upstream],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    vers = [v for v in (_ver(line.rsplit("/", 1)[-1]) for line in out.splitlines()) if v]
    latest = ".".join(map(str, max(vers))) if vers else None
    quota.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"upstream": upstream, "checked_at": now, "latest": latest}))
    return latest


def update(cfg, now=None, check=True):
    t = template_info(cfg["root"])
    cur, up = t.get("version"), t.get("upstream")
    if not cur or not up:
        return None
    latest = latest_release(up, settings(cfg)["update_check_hours"], now) if check else None
    newer = bool(latest and _ver(latest) and _ver(cur) and _ver(latest) > _ver(cur))
    return {"installed": cur, "latest": latest, "upstream": up, "available": newer}


# ---------------------------------------------------------------- advice


def compute(cfg, quotas, running, now=None, check_update=True):
    """running: number of this project's running tasks. Returns the facts and
    a list of advice items {level: info|warn|act, kind, text, command}."""
    now = now or time.time()
    st = settings(cfg)
    owner = cfg["routing"]["owner"]
    a = cfg["agents"][owner]
    items = []
    ctx = owner_context(cfg, now)
    safe = running == 0
    if ctx and ctx.get("tokens"):
        k = ctx["tokens"] // 1000
        point = "now: no worker is running" if safe else "after the running tasks are collected"
        if ctx["tokens"] >= st["clear_tokens"]:
            items.append(
                {
                    "level": "act",
                    "kind": "context",
                    "text": f"owner context {k}k tokens: run /gsd-pause-work, "
                    f"then {a.get('clear_command', '/clear')} "
                    f"and resume ({point})",
                    "command": a.get("clear_command", "/clear"),
                }
            )
        elif ctx["tokens"] >= st["compact_tokens"]:
            items.append(
                {
                    "level": "warn",
                    "kind": "context",
                    "text": f"owner context {k}k tokens: "
                    f"{a.get('compact_command', '/compact')} ({point})",
                    "command": a.get("compact_command", "/compact"),
                }
            )
    q = quotas.get(owner)
    rem = q.get("effective_remaining_percent") if quota.known(q) else None
    switch_to = None
    if rem is not None and rem < st["owner_switch_percent"]:
        acct = quota.account(cfg, owner)
        best = None
        for aid, b in cfg["agents"].items():
            qb = quotas.get(aid)
            if (
                aid == owner
                or quota.account(cfg, aid) == acct
                or "owner" not in b.get("capabilities", [])
                or not quota.known(qb)
            ):
                continue
            if best is None or qb["effective_remaining_percent"] > best[1]:
                best = (aid, qb["effective_remaining_percent"])
        if best and best[1] > st["owner_switch_percent"]:
            switch_to = best[0]
            items.append(
                {
                    "level": "act",
                    "kind": "owner",
                    "text": f"owner {owner} has {rem:.0f}% quota left: "
                    "stop new work, /gsd-pause-work, "
                    f"then hand over to {best[0]} ({best[1]:.0f}% left)",
                    "command": f"python3 scripts/orch.py owner set {best[0]} --launch",
                }
            )
        else:
            items.append(
                {
                    "level": "act",
                    "kind": "owner",
                    "text": f"owner {owner} has {rem:.0f}% quota left and "
                    "no other owner-capable agent has more: "
                    "pause at the next safe point",
                    "command": None,
                }
            )
    h = handoff(cfg["root"])
    if (switch_to or (ctx and (ctx.get("tokens") or 0) >= st["clear_tokens"])) and (
        not h or now - h["mtime"] > st["handoff_max_age_minutes"] * 60
    ):
        items.append(
            {
                "level": "warn",
                "kind": "handoff",
                "text": "no fresh .planning/HANDOFF.json: "
                "run /gsd-pause-work before clearing or switching",
                "command": "/gsd-pause-work",
            }
        )
    up = update(cfg, now, check=check_update)
    if up and up["available"]:
        items.append(
            {
                "level": "info",
                "kind": "update",
                "text": f"template {up['latest']} available (installed {up['installed']})",
                "command": f"git clone {up['upstream']} && "
                f"<clone>/scripts/install-into-repo.sh {cfg['root']}",
            }
        )
    return {
        "owner": owner,
        "owner_quota": rem,
        "context": ctx,
        "safe_point": safe,
        "handoff": h,
        "update": up,
        "items": items,
    }
