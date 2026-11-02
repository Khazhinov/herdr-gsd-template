"""Quota probes. Every probe returns the same normalized dict:

  agent, available, confidence, source, observed_at (unix s), stale,
  windows [{name, used_percent, remaining_percent, resets_at, window_minutes}],
  effective_remaining_percent (min over windows), extra {...}

Probes never guess: no reading -> available False, confidence "unknown".
"""

import glob
import json
import os
import select
import subprocess
import time
from pathlib import Path

CACHE_DIR = Path(os.environ.get("ORCH_CACHE_DIR") or Path.home() / ".cache" / "herdr-orch")
CLAUDE_SNAPSHOT = CACHE_DIR / "claude-statusline.json"
QUOTA_CACHE = CACHE_DIR / "quotas.json"


def unknown(agent, reason, source=None):
    return {
        "agent": agent,
        "available": False,
        "confidence": "unknown",
        "source": source,
        "observed_at": None,
        "stale": False,
        "windows": [],
        "effective_remaining_percent": None,
        "extra": {"reason": reason},
    }


def window(name, used, resets_at, minutes, now):
    used = max(0.0, min(100.0, float(used)))
    resets_at = float(resets_at) if resets_at else None
    # A reset needs a new observation; the old reading cannot prove a refill.
    remaining = None if resets_at and resets_at <= now else 100.0 - used
    return {
        "name": name,
        "used_percent": round(used, 1),
        "remaining_percent": round(remaining, 1) if remaining is not None else None,
        "resets_at": resets_at,
        "window_minutes": minutes,
    }


def label(minutes, fallback):
    if not minutes:
        return fallback
    return f"{minutes // 1440}d" if minutes >= 1440 and minutes % 1440 == 0 else f"{minutes // 60}h"


def finish(res, stale_after_s, now):
    ws = res["windows"]
    values = [w["remaining_percent"] for w in ws]
    res["effective_remaining_percent"] = min(values) if values and None not in values else None
    res["available"] = bool(ws) and None not in values
    res["stale"] = False
    if res["observed_at"] and stale_after_s and now - res["observed_at"] > stale_after_s:
        res["stale"] = True
    return res


# ---------------------------------------------------------------- codex


def codex_rpc(timeout=15.0, argv=None):
    """Ask the Codex app-server for live account rate limits (one JSON-RPC call)."""
    argv = argv or ["codex", "app-server"]
    p = subprocess.Popen(
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    try:
        msgs = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "herdr-orch", "version": "0.2"}},
            },
            {"jsonrpc": "2.0", "method": "initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read"},
        ]
        p.stdin.write("".join(json.dumps(m) + "\n" for m in msgs).encode())
        p.stdin.flush()
        deadline = time.time() + timeout
        buf = b""
        while time.time() < deadline:
            r, _, _ = select.select([p.stdout.fileno()], [], [], max(0.0, deadline - time.time()))
            if not r:
                break
            chunk = os.read(p.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if o.get("id") == 2:
                    if "error" in o:
                        raise RuntimeError(o["error"].get("message", "rpc error"))
                    return o["result"]
        raise TimeoutError("codex app-server did not answer account/rateLimits/read")
    finally:
        p.kill()
        p.wait()
        p.stdin.close()
        p.stdout.close()


def codex_from_rpc(result, now):
    rl = result.get("rateLimits") or {}
    ws = []
    for key, fallback in (("primary", "short"), ("secondary", "long")):
        w = rl.get(key)
        if isinstance(w, dict) and w.get("usedPercent") is not None:
            m = w.get("windowDurationMins")
            ws.append(window(label(m, fallback), w["usedPercent"], w.get("resetsAt"), m, now))
    credits = (result.get("rateLimitResetCredits") or {}).get("credits") or []
    denied = result.get("ordinaryUsageAllowed") is False or bool(rl.get("rateLimitReachedType"))
    if denied:
        if not ws:
            ws = [window("denied", 100, None, None, now)]
        for w in ws:
            w["remaining_percent"] = 0.0
    return {
        "agent": "codex",
        "available": True,
        "confidence": "official-rpc",
        "source": "codex app-server account/rateLimits/read",
        "observed_at": now,
        "stale": False,
        "windows": ws,
        "extra": {
            "plan": rl.get("planType"),
            "limit_reached": rl.get("rateLimitReachedType"),
            "usage_allowed": result.get("ordinaryUsageAllowed"),
            "reset_credits_available": sum(1 for c in credits if c.get("status") == "available"),
        },
    }


def _find_rl(x):
    if isinstance(x, dict):
        rl = x.get("rate_limits")
        if isinstance(rl, dict) and (
            isinstance(rl.get("primary"), dict) or isinstance(rl.get("secondary"), dict)
        ):
            return rl
        for v in x.values():
            r = _find_rl(v)
            if r:
                return r
    elif isinstance(x, list):
        for v in x:
            r = _find_rl(v)
            if r:
                return r
    return None


def codex_from_rollouts(sessions_root, now):
    """Fallback: last rate_limits event in local Codex session logs."""
    from datetime import datetime

    files = sorted(
        glob.glob(str(Path(sessions_root) / "**" / "rollout-*.jsonl"), recursive=True),
        key=lambda f: Path(f).stat().st_mtime,
        reverse=True,
    )[:30]
    best, best_ts, src = None, -1.0, None
    for fn in files:
        mtime = Path(fn).stat().st_mtime
        try:
            lines = Path(fn).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if "rate_limits" not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rl = _find_rl(obj)
            if not rl:
                continue
            try:
                ts = datetime.fromisoformat(
                    str(obj.get("timestamp", "")).replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                ts = mtime
            if ts > best_ts:
                best, best_ts, src = rl, ts, fn
    if not best:
        return None
    ws = []
    for key, fallback in (("primary", "short"), ("secondary", "long")):
        w = best.get(key)
        if isinstance(w, dict) and w.get("used_percent") is not None:
            m = w.get("window_minutes")
            ws.append(window(label(m, fallback), w["used_percent"], w.get("resets_at"), m, now))
    return {
        "agent": "codex",
        "available": True,
        "confidence": "parsed-local-telemetry",
        "source": src,
        "observed_at": best_ts,
        "stale": False,
        "windows": ws,
        "extra": {},
    }


def probe_codex(now, stale_after_s, rpc=codex_rpc, sessions_root=None):
    try:
        res = codex_from_rpc(rpc(), now)
    except Exception as e:  # missing binary, protocol change, offline
        res = codex_from_rollouts(sessions_root or Path.home() / ".codex" / "sessions", now)
        if res is None:
            return unknown("codex", f"rpc failed ({e}); no local telemetry")
        res["extra"]["rpc_error"] = str(e)
    return finish(res, stale_after_s, now)


# ---------------------------------------------------------------- claude


def merge_sessions(now, stale_after_s):
    """Every Claude session taps its statusline. An idle session still renders
    its last-known rate_limits, possibly from before a reset, so the newest tap
    is not the newest reading. Per window: the latest resets_at is the current
    window, and within one window usage only grows, so the highest used wins."""
    best, seen = {}, None
    for p in (CACHE_DIR / "owner-sessions").glob("*.json"):
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        rl = d.get("rate_limits")
        if not isinstance(rl, dict) or now - d.get("observed_at", 0) > stale_after_s:
            continue
        seen = max(seen or 0, d["observed_at"])
        for key, w in rl.items():
            if not isinstance(w, dict) or w.get("used_percentage") is None:
                continue
            cur = best.get(key)
            k = (w.get("resets_at") or 0, w["used_percentage"])
            if cur is None or k > (cur.get("resets_at") or 0, cur["used_percentage"]):
                best[key] = w
    return {"observed_at": seen, "rate_limits": best} if best else None


def probe_claude(now, stale_after_s, snapshot=None):
    """Read the snapshot written by `orch.py statusline-tap` from Claude Code's
    statusline input (rate_limits.five_hour / seven_day)."""
    snap = Path(snapshot or CLAUDE_SNAPSHOT)
    merged = None if snapshot else merge_sessions(now, stale_after_s)
    try:
        data = merged or json.loads(snap.read_text())
    except (OSError, json.JSONDecodeError):
        return unknown(
            "claude",
            "no statusline snapshot; install the tap (reconcile-runtime-config.py)",
            str(snap),
        )
    rl = data.get("rate_limits")
    if not isinstance(rl, dict):
        return unknown(
            "claude",
            "statusline reports no rate_limits (API key or non-subscription auth)",
            str(snap),
        )
    ws = []
    for key, name, minutes in (("five_hour", "5h", 300), ("seven_day", "7d", 10080)):
        w = rl.get(key)
        if isinstance(w, dict) and w.get("used_percentage") is not None:
            ws.append(window(name, w["used_percentage"], w.get("resets_at"), minutes, now))
    extra = {
        k: v for k, v in rl.items() if k not in ("five_hour", "seven_day") and isinstance(v, dict)
    }
    res = {
        "agent": "claude",
        "available": True,
        "confidence": "official-statusline",
        "source": str(snap),
        "observed_at": data.get("observed_at"),
        "stale": False,
        "windows": ws,
        "extra": {"other_limits": sorted(extra)},
    }
    return finish(res, stale_after_s, now)


def probe_static(agent, spec, now):
    if not isinstance(spec, dict) or spec.get("remaining_percent") is None:
        return unknown(agent, "quota = static but quota_static.remaining_percent is not set")
    reset = float(spec["resets_at"]) if spec.get("resets_at") else None
    period = spec.get("period_minutes")
    if reset and reset <= now and period:
        reset += (int((now - reset) // (period * 60)) + 1) * period * 60
    res = {
        "agent": agent,
        "available": True,
        "confidence": "configured-static",
        "source": "agents config",
        "observed_at": now,
        "stale": False,
        "windows": [window("budget", 100 - float(spec["remaining_percent"]), reset, period, now)],
        "extra": {},
    }
    return finish(res, 0, now)


# ---------------------------------------------------------------- facade


def account(cfg, aid):
    """Agents that draw on one quota (variants of one CLI) share this key."""
    kind = cfg["agents"][aid].get("quota", "none")
    return kind if kind in ("codex", "claude") else aid


def probe(cfg, aid, now=None, shared=None):
    """One reading per probe kind: agent variants (e.g. two Codex models on one
    account) share the account's quota. `shared` caches readings within a call."""
    now = now or time.time()
    a = cfg["agents"][aid]
    stale_s = 60 * cfg["routing"].get("unknown_quota", {}).get("stale_after_minutes", 30)
    kind = a.get("quota", "none")
    shared = {} if shared is None else shared
    if kind in ("codex", "claude"):
        if kind not in shared:
            shared[kind] = (
                probe_codex(now, stale_s) if kind == "codex" else probe_claude(now, stale_s)
            )
        res = json.loads(json.dumps(shared[kind]))
        res["agent"] = aid
    elif kind == "static":
        res = probe_static(aid, a.get("quota_static"), now)
    else:
        return unknown(aid, "no quota probe for this agent")
    return gate(cfg, aid, res)


def gate(cfg, aid, res):
    """Apply this project's window selection to an account's raw reading."""
    res = json.loads(json.dumps(res))
    res["agent"] = aid
    # Routing may consider only some windows (e.g. a team that watches the
    # weekly window by hand). Other windows stay visible but do not gate.
    names = cfg["agents"][aid].get("quota_windows")
    if names and res["windows"]:
        gating = [w for w in res["windows"] if w["name"] in names]
        res["effective_remaining_percent"] = (
            min(w["remaining_percent"] for w in gating)
            if gating and all(w["remaining_percent"] is not None for w in gating)
            else None
        )
        res["extra"]["gating_windows"] = names
        res["available"] = res["effective_remaining_percent"] is not None
    return res


def all_quotas(cfg, max_age=60.0, refresh=False):
    """Quotas are per account, not per project: cache them for every project."""
    now = time.time()
    cache = {}
    try:
        cache = json.loads(QUOTA_CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    out, changed, refreshed = {}, False, set()
    for aid in cfg["agents"]:
        kind = cfg["agents"][aid].get("quota", "none")
        if kind == "static":
            out[aid] = probe_static(aid, cfg["agents"][aid].get("quota_static"), now)
            continue
        key = account(cfg, aid)
        c = cache.get(key)
        if key not in refreshed and (refresh or not c or now - c.get("probed_at", 0) >= max_age):
            if kind == "codex":
                c = probe_codex(now, 0)
            elif kind == "claude":
                c = probe_claude(now, 0)
            else:
                c = unknown(aid, "no quota probe for this agent")
            c["probed_at"] = now
            cache[key] = c
            changed = True
            refreshed.add(key)
        c = json.loads(json.dumps(c))
        c.setdefault("extra", {}).pop("gating_windows", None)
        for w in c["windows"]:
            if w.get("resets_at") and w["resets_at"] <= now:
                w["remaining_percent"] = None
        c = finish(
            c, 60 * cfg["routing"].get("unknown_quota", {}).get("stale_after_minutes", 30), now
        )
        out[aid] = gate(cfg, aid, c)
    if changed:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Shared by every project: unique temp name per writer.
        tmp = QUOTA_CACHE.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache, indent=1))
        tmp.replace(QUOTA_CACHE)
    return out


def known(q):
    return bool(
        q
        and q.get("available")
        and not q.get("stale")
        and q.get("effective_remaining_percent") is not None
    )


def headroom(q, now=None):
    """Percent of quota per hour left before the tightest window resets.
    High = capacity that expires unused unless spent soon."""
    if not known(q):
        return None
    now = now or time.time()
    names = (q.get("extra") or {}).get("gating_windows")
    ws = [w for w in q["windows"] if not names or w["name"] in names] or q["windows"]
    w = min(
        ws,
        key=lambda w: (
            w["remaining_percent"] if w["remaining_percent"] is not None else float("inf")
        ),
    )
    hours = max(1.0, ((w.get("resets_at") or now + 3600 * 24 * 7) - now) / 3600)
    return round(w["remaining_percent"] / hours, 2)
