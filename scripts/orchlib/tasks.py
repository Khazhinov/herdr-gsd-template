"""Task lifecycle on herdr-core: route -> worktree -> hc run -> report -> collect.

A worker terminal is runtime state. A task is done only when its report ends
with a sentinel and, for execution, its branch carries commits on a clean tree.
"""
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import hc, quota, route
from .config import project_name

ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,27}$")
SENTINELS = ("Result: complete", "Result: incomplete", "Major issue: yes", "Major issue: no")
OK_SENTINELS = ("Result: complete", "Major issue: no")
DEFAULT_PASS_ENV = ["PATH", "LANG", "LC_ALL", "ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy",
                    "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "HERDR_TOOL_AGENTS"]


def runtime(cfg):
    d = cfg["root"] / ".orchestration" / "runtime"
    (d / "tasks").mkdir(parents=True, exist_ok=True)
    return d


def git(cfg, *args, cwd=None, check=True):
    p = subprocess.run(["git", "-C", str(cwd or cfg["root"]), *args], capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def write_json(path, data):
    tmp = Path(str(path) + ".tmp")
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


def preview(cfg, quotas=None):
    """What each role would get right now (dashboard, `orch.py route`)."""
    quotas = quotas or quota.all_quotas(cfg)
    inst, run, ov = installed(cfg), running_counts(cfg), override_get(cfg)
    return {role: route.decide(cfg, role, quotas, run, override=ov.get(role), installed=inst)
            for role in cfg["routing"].get("roles", {})}


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
    exists = subprocess.run(["git", "-C", str(cfg["root"]), "show-ref", "--verify", "--quiet",
                             f"refs/heads/{branch}"]).returncode == 0
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
        raise SystemExit(f"refusing: live terminals still inside {path}: {', '.join(hits)} "
                         f"(collect/kill them first)")


def wt_remove(cfg, path):
    wt_guard(path)
    git(cfg, "worktree", "remove", str(path))
    git(cfg, "worktree", "prune")


def wt_merge(cfg, tid):
    path, branch = wt_paths(cfg, tid)
    if path.exists():
        if git(cfg, "status", "--porcelain", cwd=path):
            raise SystemExit(f"worktree dirty: {path}")
        wt_remove(cfg, path)
    if git(cfg, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("owner tree has uncommitted changes; commit or stash before merge")
    git(cfg, "merge", "--no-ff", "-m", f"Merge {branch}", branch)
    git(cfg, "branch", "-d", branch)


# ---------------------------------------------------------------- dispatch

PROTOCOL = """

---
## Orchestration protocol (appended by orch.py; overrides nothing above)

- Task id: `{id}`; role: `{role}`; you are a bounded worker, not the project owner.
- Work only inside `{cwd}`. Do not modify `.planning/`. Do not start other agents or GSD orchestrators.
{commit_rule}- Write your report to `{report}` (create folders as needed). Its last line must be exactly one of:
  `Result: complete`, `Result: incomplete`, `Major issue: yes`, `Major issue: no`.
- If a missing decision blocks you, stop and write the report with `Result: incomplete`.
- Never approve permission dialogs on your own; wait for a person.
{notify_rule}"""


def dispatch(cfg, task_file, role, tid, agent=None, heavy=None, worktree=None, base="HEAD", report=None):
    if not ID_RE.match(tid):
        raise SystemExit(f"invalid task id {tid!r}: {ID_RE.pattern}")
    if task_path(cfg, tid).exists() and load_task(cfg, tid).get("state") == "running":
        raise SystemExit(f"task {tid} is already running")
    body = Path(task_file).read_text()
    quotas = quota.all_quotas(cfg)
    ov = override_get(cfg).get(role)
    d = route.decide(cfg, role, quotas, running_counts(cfg), heavy=heavy,
                     override=agent or ov, installed=installed(cfg))
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
    contract.write_text(body + PROTOCOL.format(
        id=tid, role=role, cwd=cwd, report=report,
        commit_rule=(f"- Commit your work on branch `{branch}` (already checked out). "
                     f"Leave the tree clean.\n") if branch else "",
        notify_rule=(f"- When finished or blocked, run: `hc send {parent} \"orch:{tid} done {report}\"` "
                     f"(or `blocked` with one line why).\n") if parent else ""))

    argv = list(a["command"])
    if use_wt:
        common = git(cfg, "rev-parse", "--path-format=absolute", "--git-common-dir")
        argv += [x.replace("{git_common_dir}", common).replace("{cwd}", str(cwd))
                 for x in a.get("worktree_args", [])]
    # herdr-core starts programs with the core's environment, not the caller's:
    # carry PATH, proxies and locale explicitly.
    w = cfg["routing"].get("workers", {})
    keep = w.get("pass_env", DEFAULT_PASS_ENV)
    argv = ["env", *[f"{k}={os.environ[k]}" for k in keep if k in os.environ]] + argv
    first = f"Read the task contract {contract} and carry it out exactly. Task id {tid}."
    if a.get("prompt", "arg") == "arg":
        argv.append(first)

    labels = {"orch.task": tid, "orch.role": role, "orch.agent": aid, "orch.project": project_name(cfg)}
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
    t = {"id": tid, "role": role, "weight": d["weight"], "agent": aid, "terminal": addr or name,
         "startup": startup,
         "name": name, "cwd": str(cwd), "branch": branch, "base": base_commit, "report": str(report),
         "contract": str(contract), "parent": parent, "state": "running", "started_at": time.time(),
         "independent": d["independent"], "reason": d["reason"]}
    save_task(cfg, t)
    return t


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
    return {"ok": False, "why": "no agent status yet; it may wait for a person (trust/login dialog). "
                                f"Answer it in Herdr App or `hc attach {name}`. Screen tail:\n{tail}"}


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
        ok = subprocess.run(["git", "-C", str(cfg["root"]), "rev-parse", "--verify", "--quiet",
                             t["branch"]], capture_output=True).returncode == 0
        ev["commits"] = int(git(cfg, "rev-list", "--count", f"{t['base']}..{t['branch']}")) if ok else 0
        ev["clean"] = not git(cfg, "status", "--porcelain", cwd=t["cwd"]) if Path(t["cwd"]).exists() else None
    return ev


def verdict(t, ev):
    if ev["sentinel"] is None:
        return "incomplete", "no report sentinel"
    if ev["sentinel"] not in OK_SENTINELS:
        return ("complete" if ev["sentinel"] == "Major issue: yes" else "incomplete"), ev["sentinel"]
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
            return {"task": tid, "state": "running", "why": "worker still live, no report yet", "evidence": ev}
    # Reports written inside a worktree must survive its removal.
    root_report = cfg["root"] / "docs" / "orch" / f"{tid}.md"
    if Path(t["report"]).exists() and Path(t["report"]) != root_report:
        root_report.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(t["report"], root_report)
        t["report_copy"] = str(root_report)
    if not keep_worker:
        hc.kill(t["name"])
        hc.rm(t["name"])
    t.update(state=state, verdict=why, evidence=ev, finished_at=time.time())
    save_task(cfg, t)
    return {"task": tid, "state": state, "why": why, "evidence": ev, "report": t.get("report_copy") or t["report"]}


def refresh(cfg, terminals=None):
    """Attach live worker facts to running tasks (no state changes here)."""
    terminals = terminals if terminals is not None else hc.ls(all_=True)
    by_name = {t.get("name"): t for t in terminals if t.get("name")}
    out = []
    for t in all_tasks(cfg):
        term = by_name.get(t.get("name"))
        st = (term or {}).get("status") or {}
        t["live"] = {"state": (term or {}).get("state", "gone"),
                     "status": st.get("state") if isinstance(st, dict) else st,
                     "msg": st.get("msg") if isinstance(st, dict) else None,
                     "address": (term or {}).get("address")}
        t["sentinel"] = report_sentinel(t["report"])
        out.append(t)
    return out
