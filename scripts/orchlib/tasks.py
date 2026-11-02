"""Task lifecycle on herdr-core: route -> worktree -> hc run -> report -> collect.

A worker terminal is runtime state. A task is done only when its report ends
with a sentinel and, for execution, its branch carries commits on a clean tree.
"""

import json
import os
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from . import hc, quota, route
from .config import project_name

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,27}$")
SENTINELS = ("Result: complete", "Result: incomplete", "Major issue: yes", "Major issue: no")
OK_SENTINELS = ("Result: complete", "Major issue: no")
DEFAULT_PASS_ENV = [
    "PATH",
    "LANG",
    "LC_ALL",
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "NO_PROXY",
    "no_proxy",
    "HERDR_TOOL_AGENTS",
]


def runtime(cfg):
    d = cfg["root"] / ".orchestration" / "runtime"
    (d / "tasks").mkdir(parents=True, exist_ok=True)
    return d


def git(cfg, *args, cwd=None, check=True):
    p = subprocess.run(
        ["git", "-C", str(cwd or cfg["root"]), *args], capture_output=True, text=True
    )
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def write_json(path, data):
    tmp = Path(f"{path}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(path)


def task_path(cfg, tid):
    return runtime(cfg) / "tasks" / f"{tid}.json"


def load_task(cfg, tid):
    p = task_path(cfg, tid)
    if not p.exists():
        raise SystemExit(f"unknown task {tid}")
    return json.loads(p.read_text())


def save_task(cfg, t):
    t["updated_at"] = time.time()
    write_json(task_path(cfg, t["id"]), t)


def all_tasks(cfg):
    out = []
    for p in sorted((runtime(cfg) / "tasks").glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except json.JSONDecodeError:
            pass
    return out


def log_decision(cfg, d, tid=None):
    with open(runtime(cfg) / "decisions.jsonl", "a") as f:
        f.write(json.dumps({**d, "task": tid}, ensure_ascii=False) + "\n")


def override_get(cfg):
    p = runtime(cfg) / "override.json"
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def override_set(cfg, role, agent):
    o = override_get(cfg)
    if agent:
        o[role] = agent
    else:
        o.pop(role, None)
    write_json(runtime(cfg) / "override.json", o)
    return o


def installed(cfg):
    return {aid: bool(shutil.which(a["command"][0])) for aid, a in cfg["agents"].items()}


def running_counts(cfg):
    n = {}
    for t in all_tasks(cfg):
        if t.get("state") == "running":
            n[t["agent"]] = n.get(t["agent"], 0) + 1
    return n


def costs(cfg):
    """Measured quota spend per "<account>/<weight>": median of the last 5 tasks
    that ran alone on their account (overlapping tasks blur each other's spend)."""
    samples = {}
    for t in sorted(all_tasks(cfg), key=lambda t: t.get("finished_at") or 0):
        if t.get("quota_burn") is not None and not t.get("quota_shared"):
            samples.setdefault(f"{quota.account(cfg, t['agent'])}/{t.get('weight')}", []).append(
                t["quota_burn"]
            )
    return {k: round(statistics.median(v[-5:]), 1) for k, v in samples.items()}


def pending(cfg, quotas, measured):
    """Per account: spend still expected from running tasks (estimate minus
    what the window already lost since each task started)."""
    out = {}
    for t in all_tasks(cfg):
        if t.get("state") != "running" or t.get("agent") not in cfg["agents"]:
            continue
        est = route.cost(cfg, measured, t["agent"], t.get("weight", "heavy"))
        q = quotas.get(t["agent"])
        spent = (
            (t["quota_start"] - q["effective_remaining_percent"])
            if (quota.known(q) and t.get("quota_start") is not None)
            else 0
        )
        acct = quota.account(cfg, t["agent"])
        out[acct] = out.get(acct, 0) + max(0.0, est - max(0.0, spent))
    return out


def decide(cfg, role, quotas=None, **kw):
    """route.decide with live running counts, installed CLIs and quota costs."""
    quotas = quotas or quota.all_quotas(cfg)
    measured = costs(cfg)
    return route.decide(
        cfg,
        role,
        quotas,
        running_counts(cfg),
        installed=installed(cfg),
        costs=measured,
        pending=pending(cfg, quotas, measured),
        **kw,
    )


def preview(cfg, quotas=None):
    """What each role would get right now (dashboard, `orch.py route`)."""
    quotas = quotas or quota.all_quotas(cfg)
    ov = override_get(cfg)
    return {
        role: decide(cfg, role, quotas, override=ov.get(role))
        for role in cfg["routing"].get("roles", {})
    }


# ---------------------------------------------------------------- worktrees


def wt_paths(cfg, tid):
    w = cfg["routing"].get("workers", {})
    branch = w.get("branch_prefix", "orch/") + tid
    # Inside the repository by default: agents inherit the folder trust the
    # owner already granted, so no trust dialog blocks an unattended worker.
    root = Path(os.path.expanduser(w.get("worktree_root", ".orchestration/worktrees")))
    if not root.is_absolute():
        root = cfg["root"] / root
    return root / tid, branch


def wt_create(cfg, tid, base="HEAD"):
    path, branch = wt_paths(cfg, tid)
    if path.exists():
        raise SystemExit(f"worktree exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = (
        subprocess.run(
            [
                "git",
                "-C",
                str(cfg["root"]),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ]
        ).returncode
        == 0
    )
    if exists:
        git(cfg, "worktree", "add", str(path), branch)
    else:
        git(cfg, "worktree", "add", "-b", branch, str(path), base)
    hook = cfg["root"] / ".orchestration" / "hooks" / "worktree-env"
    if hook.exists() and os.access(hook, os.X_OK):
        subprocess.run([str(hook), str(path), tid], check=True)
    return path, branch


def terminals_inside(path):
    """Live terminals whose shell or foreground program sits inside path."""
    path = str(Path(path).resolve())
    hits = []
    for t in hc.ls():
        for cwd in (t.get("cwd"), (t.get("foreground") or {}).get("cwd")):
            if cwd and (cwd == path or cwd.startswith(path + os.sep)):
                hits.append(t["address"])
                break
    return hits


def wt_guard(path):
    hits = terminals_inside(path)
    if hits:
        raise SystemExit(
            f"refusing: live terminals still inside {path}: {', '.join(hits)} "
            f"(collect/kill them first)"
        )


def wt_remove(cfg, path):
    wt_guard(path)
    git(cfg, "worktree", "remove", str(path))
    git(cfg, "worktree", "prune")


def wt_merge(cfg, tid):
    path, branch = wt_paths(cfg, tid)
    if git(cfg, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("owner tree has uncommitted changes; commit or stash before merge")
    if path.exists():
        if git(cfg, "status", "--porcelain", cwd=path):
            raise SystemExit(f"worktree dirty: {path}")
        wt_remove(cfg, path)
    git(cfg, "merge", "--no-ff", "-m", f"Merge {branch}", branch)
    git(cfg, "branch", "-d", branch)


# ---------------------------------------------------------------- dispatch

PROTOCOL = """

---
## Orchestration protocol (appended by orch.py; overrides nothing above)

- Task id: `{id}`; role: `{role}`; you are a bounded worker, not the project owner.
- Work only inside `{cwd}`. Do not modify `.planning/`. Do not start other agents or GSD
  orchestrators.
{commit_rule}- Write your report to `{report}` (create folders as needed). Its last line must be
  exactly one of:
  `Result: complete`, `Result: incomplete`, `Major issue: yes`, `Major issue: no`.
- If a missing decision blocks you, stop and write the report with `Result: incomplete`.
- Never approve permission dialogs on your own; wait for a person.
- When the report is written, stop. The owner watches your terminal; no message is needed.
"""


def dispatch(
    cfg, task_file, role, tid, agent=None, heavy=None, worktree=None, base="HEAD", report=None
):
    if not ID_RE.match(tid):
        raise SystemExit(f"invalid task id {tid!r}: {ID_RE.pattern}")
    if task_path(cfg, tid).exists() and load_task(cfg, tid).get("state") == "running":
        raise SystemExit(f"task {tid} is already running")
    body = Path(task_file).read_text()
    quotas = quota.all_quotas(cfg)
    ov = override_get(cfg).get(role)
    d = decide(cfg, role, quotas, heavy=heavy, override=agent or ov)
    if agent and d["selected"] != agent:
        raise SystemExit(f"requested agent {agent} is not eligible: {d['reason']}")
    log_decision(cfg, d, tid)
    if not d["selected"]:
        raise SystemExit(d["reason"])
    aid = d["selected"]
    a = cfg["agents"][aid]

    use_wt = role == "execute" if worktree is None else worktree
    cwd, branch, base_commit = cfg["root"], None, git(cfg, "rev-parse", base)
    if use_wt:
        cwd, branch = wt_create(cfg, tid, base)
    report = Path(report) if report else Path(cwd) / "docs" / "orch" / f"{tid}.md"
    if not report.is_absolute():
        report = Path(cwd) / report
    parent = os.environ.get("HC_TERMINAL_ID")
    contract = runtime(cfg) / "tasks" / f"{tid}.md"
    contract.write_text(
        body
        + PROTOCOL.format(
            id=tid,
            role=role,
            cwd=cwd,
            report=report,
            commit_rule=(
                f"- You are on branch `{branch}`. Do not run git commit: sandboxes often protect "
                "`.git`. "
                f"Leave changes in the tree; the owner commits them after reading your report.\n"
            )
            if branch
            else "",
        )
    )

    argv = list(a["command"])
    if use_wt:
        common = git(cfg, "rev-parse", "--path-format=absolute", "--git-common-dir")
        argv += [
            x.replace("{git_common_dir}", common).replace("{cwd}", str(cwd))
            for x in a.get("worktree_args", [])
        ]
    # herdr-core starts programs with the core's environment, not the caller's:
    # carry PATH, proxies and locale explicitly.
    w = cfg["routing"].get("workers", {})
    keep = w.get("pass_env", DEFAULT_PASS_ENV)
    argv = ["env", *[f"{k}={os.environ[k]}" for k in keep if k in os.environ]] + argv
    first = f"Read the task contract {contract} and carry it out exactly. Task id {tid}."
    if a.get("prompt", "arg") == "arg":
        argv.append(first)

    labels = {
        "orch.task": tid,
        "orch.role": role,
        "orch.agent": aid,
        "orch.project": project_name(cfg),
    }
    if w.get("show_in_app", True) and parent:
        try:
            space = (hc.get(parent).get("labels") or {}).get("herdr.space")
        except hc.HCError:
            space = None
        if space:
            labels["herdr.space"] = space
    name = f"w-{tid}"[:32]
    res = hc.run(argv, name, cwd, labels, outlive_parent=w.get("outlive_parent", True))
    addr = res.get("address") if isinstance(res, dict) else None
    if a.get("prompt") == "send":
        hc.wait(name, timeout=120)
        hc.send(name, first)
    startup = startup_check(name)
    t = {
        "id": tid,
        "role": role,
        "weight": d["weight"],
        "agent": aid,
        "terminal": addr or name,
        "startup": startup,
        "name": name,
        "cwd": str(cwd),
        "branch": branch,
        "base": base_commit,
        "report": str(report),
        "contract": str(contract),
        "parent": parent,
        "state": "running",
        "started_at": time.time(),
        "independent": d["independent"],
        "reason": d["reason"],
    } | quota_mark(quotas.get(aid))
    save_task(cfg, t)
    return t


def quota_mark(q):
    """Gating remaining percent and the earliest reset among gating windows."""
    if not quota.known(q):
        return {"quota_start": None, "quota_reset_at": None}
    names = (q.get("extra") or {}).get("gating_windows")
    resets = [
        w.get("resets_at")
        for w in q["windows"]
        if (not names or w["name"] in names) and w.get("resets_at")
    ]
    return {
        "quota_start": q["effective_remaining_percent"],
        "quota_reset_at": min(resets) if resets else None,
    }


def quota_burn(cfg, t, now):
    """What the task's account lost while it ran; None when unmeasurable
    (no reading, or a gating window reset in between)."""
    if t.get("quota_start") is None or (t.get("quota_reset_at") and t["quota_reset_at"] <= now):
        return None
    q = quota.all_quotas(cfg, max_age=0).get(t["agent"])
    if not quota.known(q):
        return None
    return round(max(0.0, t["quota_start"] - q["effective_remaining_percent"]), 1)


def overlapped(cfg, t, now):
    acct = quota.account(cfg, t["agent"])
    return any(
        o["id"] != t["id"]
        and o.get("agent") in cfg["agents"]
        and quota.account(cfg, o["agent"]) == acct
        and (o.get("started_at") or 0) < now
        and (o.get("finished_at") or now) > t.get("started_at", now)
        for o in all_tasks(cfg)
    )


def startup_check(name, seconds=25):
    """Agents report status (OSC 7501) once their UI is up. No status after a
    short while usually means a dialog only a person should answer (folder
    trust, login). Report it instead of silently waiting."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            g = hc.get(name)
        except hc.HCError:
            return {"ok": False, "why": "worker terminal vanished"}
        if g.get("state") != "live":
            return {"ok": False, "why": f"worker exited: {hc.read(name, 20)}"[-600:]}
        st = g.get("status") or {}
        if isinstance(st, dict) and st.get("state"):
            return {"ok": True, "status": st["state"]}
        time.sleep(2)
    screen = hc.read(name, 0)
    tail = "\n".join(x for x in str(screen).splitlines() if x.strip())[-500:]
    return {
        "ok": False,
        "why": "no agent status yet; it may wait for a person (trust/login dialog). "
        f"Answer it in Herdr App or `hc attach {name}`. Screen tail:\n{tail}",
    }


def report_sentinel(path):
    try:
        lines = [x.strip() for x in Path(path).read_text().splitlines() if x.strip()]
    except OSError:
        return None
    return lines[-1] if lines and lines[-1] in SENTINELS else None


def evidence(cfg, t):
    """Durable evidence only: report sentinel, commits, clean tree."""
    ev = {"sentinel": report_sentinel(t["report"]), "report_exists": Path(t["report"]).exists()}
    if t.get("branch"):
        ok = (
            subprocess.run(
                ["git", "-C", str(cfg["root"]), "rev-parse", "--verify", "--quiet", t["branch"]],
                capture_output=True,
            ).returncode
            == 0
        )
        ev["commits"] = (
            int(git(cfg, "rev-list", "--count", f"{t['base']}..{t['branch']}")) if ok else 0
        )
        ev["clean"] = (
            not git(cfg, "status", "--porcelain", cwd=t["cwd"]) if Path(t["cwd"]).exists() else None
        )
    return ev


def verdict(t, ev):
    if ev["sentinel"] is None:
        return "incomplete", "no report sentinel"
    if ev["sentinel"] not in OK_SENTINELS:
        return ("complete" if ev["sentinel"] == "Major issue: yes" else "incomplete"), ev[
            "sentinel"
        ]
    if t.get("branch") and t["role"] == "execute":
        if not ev.get("commits"):
            return "incomplete", "report says complete but branch has no commits"
        if ev.get("clean") is False:
            return "incomplete", "worktree has uncommitted changes"
    return "complete", ev["sentinel"]


def collect(cfg, tid, keep_worker=False):
    t = load_task(cfg, tid)
    ev = evidence(cfg, t)
    state, why = verdict(t, ev)
    if state == "incomplete" and ev["sentinel"] is None:
        try:
            live = hc.get(t["name"]).get("state") == "live"
        except hc.HCError:
            live = False
        if live:
            return {
                "task": tid,
                "state": "running",
                "why": "worker still live, no report yet",
                "evidence": ev,
            }
    # Keep a copy outside the worktree: it survives an abandoned worktree.
    backup = runtime(cfg) / "reports" / f"{tid}.md"
    if Path(t["report"]).exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(t["report"], backup)
    # Workers do not commit (sandboxed .git); commit their tree once the report
    # says the work is complete. Report travels with the branch.
    if t.get("branch") and Path(t["cwd"]).exists() and ev["sentinel"] in OK_SENTINELS:
        if git(cfg, "status", "--porcelain", cwd=t["cwd"]):
            git(cfg, "add", "-A", cwd=t["cwd"])
            git(
                cfg, "commit", "-q", "-m", f"orch({tid}): {t['role']} by {t['agent']}", cwd=t["cwd"]
            )
            ev = evidence(cfg, t)
            state, why = verdict(t, ev)
    if not keep_worker:
        hc.kill(t["name"])
        hc.rm(t["name"])
    now = time.time()
    if t.get("agent") in cfg["agents"]:
        t.update(quota_burn=quota_burn(cfg, t, now), quota_shared=overlapped(cfg, t, now))
    t.update(state=state, verdict=why, evidence=ev, finished_at=now)
    save_task(cfg, t)
    return {
        "task": tid,
        "state": state,
        "why": why,
        "evidence": ev,
        "report": t["report"],
        "backup": str(backup),
    }


def refresh(cfg, terminals=None):
    """Attach live worker facts to running tasks (no state changes here)."""
    terminals = terminals if terminals is not None else hc.ls(all_=True)
    by_name = {t.get("name"): t for t in terminals if t.get("name")}
    out = []
    for t in all_tasks(cfg):
        term = by_name.get(t.get("name"))
        st = (term or {}).get("status") or {}
        t["live"] = {
            "state": (term or {}).get("state", "gone"),
            "status": st.get("state") if isinstance(st, dict) else st,
            "msg": st.get("msg") if isinstance(st, dict) else None,
            "address": (term or {}).get("address"),
        }
        t["sentinel"] = report_sentinel(t["report"])
        out.append(t)
    return out
