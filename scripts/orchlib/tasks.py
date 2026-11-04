"""Task lifecycle on herdr-core: route -> worktree -> hc run -> report -> collect.

A worker terminal is runtime state. A task is done only when its report ends
with a sentinel and, for execution, its branch carries commits on a clean tree.
"""

import fcntl
import json
import os
import re
import shutil
import statistics
import subprocess
import time
from contextlib import contextmanager, suppress
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
    "HERDR_AGENT_KIT",
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
        except (OSError, json.JSONDecodeError):  # removed or replaced by another process meanwhile
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


@contextmanager
def admission():
    quota.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(quota.CACHE_DIR / "admission.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def ledger():
    path = quota.CACHE_DIR / "ledger.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        data = {"entries": [], "samples": {}, "history": []}
    data.setdefault("entries", [])
    data.setdefault("samples", {})
    data.setdefault("history", [])
    try:
        live = {t.get("address") for t in hc.ls(all_=True)}
    except (OSError, hc.HCError):
        live = None
    now = time.time()
    data["history"] = [e for e in data["history"] if now - e.get("finished_at", 0) < 86400]
    old = data["entries"]
    data["entries"] = [
        e
        for e in old
        if now - e.get("started_at", 0) < 86400
        and (
            (e.get("state") == "starting" and now - e.get("started_at", 0) < 60)
            or live is None
            or e.get("terminal") in live
        )
    ]
    if len(old) != len(data["entries"]):
        write_json(path, data)
    return data


def save_ledger(data):
    write_json(quota.CACHE_DIR / "ledger.json", data)


def ledger_drop(cfg, tid):
    with admission():
        data = ledger()
        data["entries"] = [
            e
            for e in data["entries"]
            if not (e["project_root"] == str(cfg["root"]) and e["task_id"] == tid)
        ]
        save_ledger(data)


def running_counts(cfg, data=None):
    n = {}
    if data is None:
        with admission():
            data = ledger()
    entries = data["entries"]
    for e in entries:
        n[e["agent"]] = n.get(e["agent"], 0) + 1
        key = f"account:{e['account']}"
        n[key] = n.get(key, 0) + 1
    return n


def costs(cfg, data=None):
    if data is None:
        with admission():
            data = ledger()
    samples = data["samples"]
    return {k: round(statistics.median(v[-5:]), 1) for k, v in samples.items() if v}


def pending(cfg, quotas, measured, data=None):
    """Per account: spend still expected from running tasks (estimate minus
    what the window already lost since each task started)."""
    if data is None:
        with admission():
            data = ledger()
    entries = data["entries"]
    out = {}
    for acct in {e["account"] for e in entries}:
        group = [e for e in entries if e["account"] == acct]
        q = next((quotas[aid] for aid in quotas if quota.account(cfg, aid) == acct), None)
        if not q:
            continue
        for w in q.get("windows", []):
            name = w["name"]
            estimates = sum(e.get("cost_estimate", {}).get(name, 0) for e in group)
            earliest = min(group, key=lambda e: e["started_at"])
            start = earliest.get("quota_start", {}).get(name)
            drop = (
                max(0, start - w["remaining_percent"])
                if start is not None and w["remaining_percent"] is not None
                else 0
            )
            out.setdefault(acct, {})[name] = max(0.0, estimates - drop)
    return out


def decide(cfg, role, quotas=None, **kw):
    """route.decide with live running counts, installed CLIs and quota costs."""
    quotas = quotas if quotas is not None else quota.all_quotas(cfg)
    data = kw.pop("ledger_data", None)
    if data is None:
        with admission():
            data = ledger()
    measured = costs(cfg, data)
    return route.decide(
        cfg,
        role,
        quotas,
        running_counts(cfg, data),
        installed=installed(cfg),
        costs=measured,
        pending=pending(cfg, quotas, measured, data),
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
    t = load_task(cfg, tid)
    if t.get("state") != "complete" or t.get("branch") != branch:
        raise SystemExit(f"task {tid} must be collected complete on {branch}")
    if git(cfg, "status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("owner tree has uncommitted changes; commit or stash before merge")
    planning_guard(cfg, t)
    changed = set(git(cfg, "diff", "--name-only", f"HEAD...{branch}").splitlines())
    untracked = set(git(cfg, "ls-files", "--others", "--exclude-standard").splitlines())
    collisions = changed & untracked
    if collisions:
        raise SystemExit("merge would overwrite untracked files: " + ", ".join(sorted(collisions)))
    preflight = subprocess.run(
        ["git", "-C", str(cfg["root"]), "merge-tree", "--write-tree", "HEAD", branch],
        capture_output=True,
        text=True,
    )
    if preflight.returncode:
        raise SystemExit(f"merge conflict: {preflight.stdout.strip() or preflight.stderr.strip()}")
    if path.exists():
        if git(cfg, "status", "--porcelain", cwd=path):
            raise SystemExit(f"worktree dirty: {path}")
        wt_guard(path)
    git(cfg, "merge", "--no-ff", "-m", f"Merge {branch}", branch)
    if path.exists():
        wt_remove(cfg, path)
    git(cfg, "branch", "-d", branch)


def planning_guard(cfg, t):
    files = set()
    if t.get("branch"):
        files.update(
            git(
                cfg, "diff", "--name-only", f"{t['base']}..{t['branch']}", "--", ".planning/"
            ).splitlines()
        )
        if Path(t["cwd"]).exists():
            files.update(
                git(
                    cfg,
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                    "--",
                    ".planning/",
                    cwd=t["cwd"],
                ).splitlines()
            )
    if files:
        raise SystemExit("worker changed .planning/: " + ", ".join(sorted(files)))


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
    cfg,
    task_file,
    role,
    tid,
    agent=None,
    heavy=None,
    worktree=None,
    base="HEAD",
    report=None,
    replace=False,
    of=None,
):
    if not ID_RE.match(tid):
        raise SystemExit(f"invalid task id {tid!r}: {ID_RE.pattern}")
    body = Path(task_file).read_text()
    quotas = quota.all_quotas(cfg)
    ov = override_get(cfg).get(role)
    excluded = quota.account(cfg, load_task(cfg, of)["agent"]) if of else None
    with admission():
        data = ledger()
        if task_path(cfg, tid).exists():
            old = load_task(cfg, tid)
            if not replace or old.get("state") in ("running", "starting"):
                raise SystemExit(f"task {tid} already exists (use --replace for a collected task)")
            if wt_paths(cfg, tid)[0].exists():
                raise SystemExit(f"task {tid} worktree still exists; merge or remove it first")
        d = decide(
            cfg,
            role,
            quotas,
            heavy=heavy,
            override=agent or ov,
            exclude_account=excluded,
            ledger_data=data,
        )
        if agent and d["selected"] != agent:
            raise SystemExit(f"requested agent {agent} is not eligible: {d['reason']}")
        log_decision(cfg, d, tid)
        if not d["selected"]:
            raise SystemExit(d["reason"])
        aid = d["selected"]
        if task_path(cfg, tid).exists():
            archive = runtime(cfg) / "archive" / f"{tid}-{int(time.time() * 1000)}"
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(task_path(cfg, tid), archive / f"{tid}.json")
            old_report = runtime(cfg) / "reports" / f"{tid}.md"
            if not old_report.exists() and old.get("report") and Path(old["report"]).exists():
                old_report = Path(old["report"])
            if old_report.exists():
                shutil.move(old_report, archive / f"{tid}.md")
        acct = quota.account(cfg, aid)
        marks = quota_mark(quotas.get(aid))
        raw_windows = {
            w["name"]: w["remaining_percent"]
            for w in (quotas.get(aid) or {}).get("windows", [])
            if w["remaining_percent"] is not None
        }
        estimates = {
            name: route.cost(cfg, costs(cfg, data), aid, d["weight"], name) for name in raw_windows
        }
        entry = {
            "account": acct,
            "project_root": str(cfg["root"]),
            "task_id": tid,
            "agent": aid,
            "weight": d["weight"],
            "cost_estimate": estimates,
            "started_at": time.time(),
            "quota_start": raw_windows,
            "state": "starting",
        }
        data["entries"].append(entry)
        save_ledger(data)
    a = cfg["agents"][aid]

    created = False
    cwd = cfg["root"]
    addr = None
    try:
        use_wt = role == "execute" if worktree is None else worktree
        cwd, branch, base_commit = cfg["root"], None, git(cfg, "rev-parse", base)
        if use_wt:
            cwd = wt_paths(cfg, tid)[0]
            created = not cwd.exists()
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
                    f"- You are on branch `{branch}`. Do not run git commit: "
                    "sandboxes often protect "
                    "`.git`. "
                    "Leave changes in the tree; "
                    "the owner commits them after reading your report.\n"
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
        with admission():
            data = ledger()
            for e in data["entries"]:
                if e["project_root"] == str(cfg["root"]) and e["task_id"] == tid:
                    e.update(state="running", terminal=addr or name)
            save_ledger(data)
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
            "started_at": entry["started_at"],
            "independent": d["independent"],
            "reason": d["reason"],
        } | marks
        save_task(cfg, t)
        return t

    except BaseException as exc:
        if addr:
            with suppress(Exception):
                hc.kill(addr)
                hc.rm(addr)
        ledger_drop(cfg, tid)
        if created and Path(cwd).exists():
            with suppress(Exception):  # best effort: the launch error is what matters
                wt_remove(cfg, cwd)
        save_task(cfg, {"id": tid, "state": "failed", "error": str(exc), "agent": aid})
        raise


def quota_mark(q):
    """Remaining and reset time for each gating window at admission."""
    if not quota.known(q):
        return {
            "quota_start": None,
            "quota_reset_at": None,
            "quota_start_windows": {},
            "quota_resets": {},
        }
    names = (q.get("extra") or {}).get("gating_windows")
    windows = [w for w in q["windows"] if not names or w["name"] in names]
    resets = [w.get("resets_at") for w in windows if w.get("resets_at")]
    return {
        "quota_start": q["effective_remaining_percent"],
        "quota_reset_at": min(resets) if resets else None,
        "quota_start_windows": {w["name"]: w["remaining_percent"] for w in windows},
        "quota_resets": {w["name"]: w.get("resets_at") for w in windows},
    }


def quota_burn(cfg, t, now):
    """Measured spend per gating window; omit windows without valid readings."""
    if not t.get("quota_start_windows"):
        return {}
    q = quota.all_quotas(cfg, max_age=0).get(t["agent"])
    if not q:
        return {}
    current = {w["name"]: w["remaining_percent"] for w in q["windows"]}
    return {
        name: round(max(0.0, start - current[name]), 1)
        for name, start in t["quota_start_windows"].items()
        if name in current
        and current[name] is not None
        and not (t.get("quota_resets", {}).get(name) and t["quota_resets"][name] <= now)
    }


def overlapped(cfg, t, now):
    acct = quota.account(cfg, t["agent"])
    with admission():
        data = ledger()
    entries = data["entries"] + data["history"]
    return any(
        e["account"] == acct
        and (e["project_root"], e["task_id"]) != (str(cfg["root"]), t["id"])
        and e["started_at"] < now
        and e.get("finished_at", now) > t.get("started_at", now)
        for e in entries
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
    if t.get("state") != "running":
        raise SystemExit(f"task {tid} is not running")
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
    if keep_worker:
        return {"task": tid, "state": "running", "why": "worker kept; no commit", "evidence": ev}
    planning_guard(cfg, t)
    hc.kill(t["terminal"])
    try:
        stopped = hc.get(t["terminal"]).get("state") != "live"
    except hc.HCError as exc:
        if exc.kind != "not_found":
            raise
        stopped = True
    if not stopped:
        hc.wait(t["terminal"], timeout=30)
        stopped = hc.get(t["terminal"]).get("state") != "live"
    if not stopped:
        raise SystemExit(f"worker {t['terminal']} did not exit")
    ev = evidence(cfg, t)
    state, why = verdict(t, ev)
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
    now = time.time()
    if t.get("agent") in cfg["agents"]:
        t.update(quota_burn=quota_burn(cfg, t, now), quota_shared=overlapped(cfg, t, now))
    with admission():
        data = ledger()
        data["entries"] = [
            e
            for e in data["entries"]
            if not (e["project_root"] == str(cfg["root"]) and e["task_id"] == tid)
        ]
        acct = quota.account(cfg, t["agent"])
        data["history"].append(
            {
                "account": acct,
                "project_root": str(cfg["root"]),
                "task_id": tid,
                "started_at": t["started_at"],
                "finished_at": now,
            }
        )
        if not t.get("quota_shared"):
            for name, value in t.get("quota_burn", {}).items():
                key = f"{acct}/{t['weight']}/{name}"
                data["samples"].setdefault(key, []).append(value)
                data["samples"][key] = data["samples"][key][-5:]
        save_ledger(data)
    hc.rm(t["terminal"])
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
