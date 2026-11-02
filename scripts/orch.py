#!/usr/bin/env python3
"""Orchestration CLI over herdr-core (`hc`) for a GSD owner.

  quota [--refresh]                 normalized quota per agent
  route ROLE [--heavy|--light]      routing decision with reason (no side effects)
  prefer ROLE AGENT|-               manual override for the next routing of ROLE
  dispatch TASK.md --role R --id ID start a worker (execute -> own worktree)
  wait [--timeout S]                wait for worker news (hc wait --children any)
  collect ID [--keep-worker]        judge durable evidence, stop the worker
  status [--json]                   tasks, quotas, routing
  watch                             live dashboard + publisher (run in a Herdr pane)
  hub start|stop                    run `watch` in its own herdr-core terminal
  worktree create|merge|remove|path ID
  statusline-tap -- CMD...          Claude statusline wrapper that records rate limits
  gsd-cross-ai                      GSD workflow.cross_ai_command bridge (stdin -> SUMMARY)
  tools | tool-ask MODULE REQUEST   reusable tool agents (herdr-tool-agents hub)
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from orchlib import config, hc, quota, route, state, tasks  # noqa: E402


def out(obj, as_json):
    if as_json:
        print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
        return True
    return False


def fmt_reset(ts):
    if not ts:
        return "?"
    d = ts - time.time()
    if d <= 0:
        return "now"
    return f"{d / 3600:.0f}h" if d < 172800 else f"{d / 86400:.1f}d"


def quota_line(aid, q):
    if not q.get("available"):
        return f"{aid:<13} unknown  ({(q.get('extra') or {}).get('reason', '')})"
    ws = "  ".join(f"{w['name']} {w['remaining_percent']:.0f}% (reset {fmt_reset(w.get('resets_at'))})"
                   for w in q["windows"])
    flag = " STALE" if q.get("stale") else ""
    extra = q.get("extra") or {}
    if extra.get("reset_credits_available"):
        ws += f"  +{extra['reset_credits_available']} reset credits"
    eff = q["effective_remaining_percent"]
    return f"{aid:<13} {'?' if eff is None else f'{eff:.0f}':>3}%  {ws}  [{q['confidence']}]{flag}"


# ---------------------------------------------------------------- commands

def cmd_quota(cfg, a):
    qs = quota.all_quotas(cfg, refresh=a.refresh)
    if not out(qs, a.json):
        for aid, q in qs.items():
            print(quota_line(aid, q))
    return 0


def cmd_route(cfg, a):
    heavy = True if a.heavy else (False if a.light else None)
    d = route.decide(cfg, a.role, quota.all_quotas(cfg), tasks.running_counts(cfg), heavy=heavy,
                     override=tasks.override_get(cfg).get(a.role), installed=tasks.installed(cfg))
    if not out(d, a.json):
        print(d["selected"] or "NONE")
        print(d["reason"])
    return 0 if d["selected"] else 4


def cmd_prefer(cfg, a):
    agent = None if a.agent == "-" else a.agent
    if agent and agent not in cfg["agents"]:
        raise SystemExit(f"unknown agent {agent}")
    print(json.dumps(tasks.override_set(cfg, a.role, agent)))
    return 0


def cmd_dispatch(cfg, a):
    heavy = True if a.heavy else (False if a.light else None)
    wt = True if a.worktree else (False if a.no_worktree else None)
    t = tasks.dispatch(cfg, a.task, a.role, a.id, agent=a.agent, heavy=heavy, worktree=wt,
                       base=a.base, report=a.report)
    if not out(t, a.json):
        print(f"{t['id']}: {t['agent']} in {t['terminal']} cwd={t['cwd']}")
        print(f"reason: {t['reason']}")
        print(f"report: {t['report']}")
        print("next: orch.py wait   then   orch.py collect " + t["id"])
    return 0


def cmd_wait(cfg, a):
    r = hc.wait(children="any", timeout=a.timeout)
    ready = [t["id"] for t in tasks.refresh(cfg) if t.get("state") == "running" and t.get("sentinel")]
    res = {"hc": r, "reports_ready": ready}
    if not out(res, a.json):
        print(json.dumps(r) if not isinstance(r, str) else r)
        print("reports ready: " + (", ".join(ready) or "none"))
    return 0


def cmd_collect(cfg, a):
    r = tasks.collect(cfg, a.id, keep_worker=a.keep_worker)
    out(r, True)
    return 0 if r["state"] == "complete" else 1


def cmd_status(cfg, a):
    s = state.compose(cfg, with_planning=a.planning)
    if out(s, a.json):
        return 0
    print(render(s, color=False))
    return 0


def cmd_worktree(cfg, a):
    if a.op == "create":
        p, b = tasks.wt_create(cfg, a.id)
        print(p)
    elif a.op == "path":
        print(tasks.wt_paths(cfg, a.id)[0])
    elif a.op == "merge":
        tasks.wt_merge(cfg, a.id)
        print(f"merged {tasks.wt_paths(cfg, a.id)[1]}")
    elif a.op == "remove":
        p, b = tasks.wt_paths(cfg, a.id)
        tasks.wt_remove(cfg, p)
        print(f"removed {p}; branch {b} kept")
    return 0


def cmd_statusline_tap(a):
    """Claude Code statusline command. Records rate_limits, then hands the same
    input to the previous statusline command so the user's line is unchanged."""
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        snap = {"observed_at": time.time(), "rate_limits": data.get("rate_limits"),
                "session_id": data.get("session_id")}
        quota.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = quota.CLAUDE_SNAPSHOT.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap))
        tmp.replace(quota.CLAUDE_SNAPSHOT)
    except (json.JSONDecodeError, OSError):
        pass
    cmd = a.chain[1:] if a.chain[:1] == ["--"] else a.chain
    if not cmd:
        # Default chain: the user's own global statusline, so the project-level
        # tap changes nothing visible.
        try:
            g = json.loads((Path.home() / ".claude" / "settings.json").read_text()).get("statusLine") or {}
            if g.get("command") and "statusline-tap" not in g["command"]:
                cmd = [g["command"]]
        except (OSError, json.JSONDecodeError):
            pass
    if cmd:
        p = subprocess.run(cmd if len(cmd) > 1 else ["sh", "-c", cmd[0]], input=raw, text=True,
                           capture_output=True)
        sys.stdout.write(p.stdout)
    return 0


def cmd_gsd_cross_ai(cfg, a):
    """GSD execute-phase pipes a self-contained plan prompt on stdin and expects
    a SUMMARY.md on stdout (workflow.cross_ai_command). Route it like any
    execute task, in the project root as GSD expects, and block until the
    worker's report has a sentinel."""
    prompt = sys.stdin.read()
    tid = "gsd-" + datetime.now().strftime("%m%d-%H%M%S")
    task = tasks.runtime(cfg) / "tasks" / f"{tid}.prompt.md"
    task.write_text(prompt + "\n\nWrite the report as a GSD SUMMARY.md for this plan "
                    "(title heading, what was done, files changed, verification).\n")
    t = tasks.dispatch(cfg, task, "execute", tid, worktree=False)
    print(f"cross-ai: {t['agent']} in {t['terminal']}", file=sys.stderr)
    while True:
        if tasks.report_sentinel(t["report"]):
            break
        r = hc.wait(t["name"], timeout=170)
        live = None
        try:
            live = hc.get(t["name"]).get("state")
        except hc.HCError:
            pass
        if live != "live" and not tasks.report_sentinel(t["report"]):
            break
        if isinstance(r, dict) and (r.get("status") or {}).get("state") == "blocked":
            print(f"cross-ai: worker {t['name']} is blocked; waiting for a person", file=sys.stderr)
    r = tasks.collect(cfg, tid)
    try:
        sys.stdout.write(Path(r["report"]).read_text())
    except OSError:
        pass
    return 0 if r["state"] == "complete" else 1


def hub_dir(cfg):
    d = os.environ.get("HERDR_TOOL_AGENTS") or cfg["routing"].get("tools", {}).get("hub")
    return Path(os.path.expanduser(d)) if d else None


def cmd_tools(cfg, a, ask=False):
    h = hub_dir(cfg)
    if not h or not (h / "tool_ask.py").exists():
        raise SystemExit("tool hub not configured: set HERDR_TOOL_AGENTS or [tools] hub in routing.local.toml")
    args = [sys.executable, str(h / "tool_ask.py")]
    args += ["ask", a.module, a.request, *(["--write"] if a.write else []), "--timeout", str(a.timeout)] if ask else ["list"]
    return subprocess.call(args)


# ---------------------------------------------------------------- dashboard

def bar(pct, width=20):
    if pct is None:
        return "?" * width
    n = round(width * pct / 100)
    return "#" * n + "." * (width - n)


def render(s, color=True):
    def c(code, x):
        return f"\x1b[{code}m{x}\x1b[0m" if color else x
    L = [c("1", f"GSD MISSION CONTROL  {s['project']}  owner={s['owner']}  "
               f"{datetime.fromtimestamp(s['updated_at']).strftime('%H:%M:%S')}")]
    L.append("")
    L.append(c("1", "ROUTING"))
    for role, d in s["routing"].items():
        ind = "" if d["independent"] is None else ("  independent" if d["independent"] else "  NOT independent")
        L.append(f"  {role:<9} {(d['selected'] or 'NONE'):<13} {d['weight']:<6}{ind}")
    for role, ag in (s.get("override") or {}).items():
        L.append(c("33", f"  override: {role} -> {ag}"))
    L.append("")
    L.append(c("1", "QUOTAS"))
    for aid, q in s["quotas"].items():
        if not q.get("available"):
            L.append(f"  {aid:<13} {bar(None)} unknown")
            continue
        eff = q["effective_remaining_percent"] or 0
        col = "31" if eff <= 15 else ("33" if eff <= 35 else "32")
        ws = " ".join(f"{w['name']}:{w['remaining_percent']:.0f}%/{fmt_reset(w.get('resets_at'))}"
                      for w in q["windows"])
        st = c("31", " STALE") if q.get("stale") else ""
        L.append(f"  {aid:<13} {c(col, bar(eff))} {eff:>3.0f}%  {ws}  hr={q.get('headroom')}{st}")
    L.append("")
    L.append(c("1", "TASKS"))
    running = [t for t in s["tasks"] if t.get("state") == "running"]
    done = [t for t in s["tasks"] if t.get("state") != "running"][-6:]
    for t in running:
        lv = t.get("live") or {}
        L.append(f"  > {t['id']:<22} {t['role']:<8} {t['agent']:<13} {lv.get('status') or lv.get('state'):<8} "
                 f"{lv.get('address') or ''} {(lv.get('msg') or '')[:50]}")
    for t in done:
        L.append(c("2", f"    {t['id']:<22} {t['role']:<8} {t['agent']:<13} {t.get('state'):<10} {t.get('verdict') or ''}"))
    if not s["tasks"]:
        L.append("  none")
    if s.get("tools"):
        L.append("")
        L.append(c("1", "TOOL AGENTS"))
        for t in s["tools"]:
            L.append(f"  {t['tool']:<20} {t.get('status') or t.get('state')} {t.get('address')}")
    p = s.get("planning")
    if p:
        L.append("")
        L.append(c("1", "GSD"))
        if p.get("available"):
            L.append(f"  milestone {p.get('milestone')}  phase {p.get('phase')}  plan {p.get('plan')}  "
                     f"status {p.get('status')}")
            for ph in p.get("phases", [])[-4:]:
                pl = ph.get("plans") or []
                donep = sum(1 for x in pl if x["complete"])
                L.append(f"  {'x' if ph['complete'] else ' '} {ph['id']:<5} plans {donep}/{len(pl)}  "
                         f"verify {ph.get('verification')}")
        else:
            L.append(f"  {p.get('reason')}")
    return "\n".join(L)


def cmd_watch(cfg, a):
    """Publisher + optional TUI. Refreshes quotas on a timer and recomposes on
    every herdr-core event that touches an orch-labeled terminal."""
    hub = os.environ.get("HC_TERMINAL_ID")
    interval = a.interval or cfg["routing"].get("watch", {}).get("quota_interval", 60)
    dirty = threading.Event()
    dirty.set()

    relevant = {"created", "lost", "restarted", "finished", "removed", "status", "turn", "labels"}

    def on_event(msg):
        p = msg.get("params") or {}
        # Our own doc writes and label updates would otherwise wake us forever.
        if msg.get("method") != "event" or p.get("type") not in relevant or p.get("terminal") == hub:
            return
        dirty.set()

    rpc = None
    try:
        rpc = hc.RPC(on_event)
        rpc.call("events.subscribe")
    except (OSError, hc.HCError) as e:
        print(f"event stream unavailable ({e}); polling every 5 s", file=sys.stderr)
    tty = sys.stdout.isatty() and not a.quiet
    last_q, last_plan, plan, rev = 0.0, 0.0, None, 0
    quotas = None
    planning_dir = cfg["root"] / ".planning"
    plan_mtime = None
    while True:
        # Events wake the loop at once; otherwise wake for the next quota refresh.
        dirty.wait(timeout=max(1.0, min(5 if rpc is None else 15, interval - (time.time() - last_q))))
        dirty.clear()
        now = time.time()
        if now - last_q >= interval or quotas is None:
            quotas = quota.all_quotas(cfg, max_age=interval - 1)
            last_q = now
        try:
            m = max((p.stat().st_mtime for p in planning_dir.rglob("*.md")), default=0)
        except OSError:
            m = 0
        if plan is None or m != plan_mtime or now - last_plan > 300:
            plan, plan_mtime, last_plan = state.planning(cfg["root"]), m, now
        s = state.compose(cfg, quotas, with_planning=False)
        s["planning"] = plan
        rev += 1
        state.publish(cfg, s, hub=hub, rev=rev)
        if tty:
            sys.stdout.write("\x1b[H\x1b[2J" + render(s) + "\n")
            sys.stdout.flush()
        if a.once:
            return 0
        if rpc and rpc.closed.is_set():
            rpc = None


def cmd_hub(cfg, a):
    """Run `watch` in its own herdr-core terminal: the publisher that feeds the
    Herdr App mod. It outlives the owner session and appears in the owner's space."""
    name = f"orch-{config.project_name(cfg)}"[:32]
    live = [t for t in hc.ls() if t.get("name") == name]
    if a.op == "stop":
        for t in live:
            hc.kill(t["address"])
            hc.rm(t["address"])
        print(f"{name} stopped" if live else f"{name} not running")
        return 0
    if live:
        print(f"{name} already running as {live[0]['address']}")
        return 0
    labels = {"orch.project": config.project_name(cfg)}
    me = os.environ.get("HC_TERMINAL_ID")
    if me and cfg["routing"].get("workers", {}).get("show_in_app", True):
        space = (hc.get(me).get("labels") or {}).get("herdr.space")
        if space:
            labels["herdr.space"] = space
    keep = cfg["routing"].get("workers", {}).get("pass_env", tasks.DEFAULT_PASS_ENV)
    argv = ["env", *[f"{k}={os.environ[k]}" for k in keep if k in os.environ],
            sys.executable, str(Path(__file__).resolve()), "--root", str(cfg["root"]), "watch"]
    r = hc.run(argv, name, cfg["root"], labels, no_parent=True)
    print(f"{name} started as {r.get('address') if isinstance(r, dict) else r}")
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="project root (default: this repository)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def p(name, **kw):
        sp = sub.add_parser(name, **kw)
        sp.add_argument("--json", action="store_true")
        return sp

    s = p("quota")
    s.add_argument("--refresh", action="store_true")
    s = p("route")
    s.add_argument("role")
    s.add_argument("--heavy", action="store_true")
    s.add_argument("--light", action="store_true")
    s = p("prefer")
    s.add_argument("role")
    s.add_argument("agent", help="agent id, or - to clear")
    s = p("dispatch")
    s.add_argument("task")
    s.add_argument("--role", required=True)
    s.add_argument("--id", required=True)
    s.add_argument("--agent")
    s.add_argument("--heavy", action="store_true")
    s.add_argument("--light", action="store_true")
    s.add_argument("--worktree", action="store_true")
    s.add_argument("--no-worktree", action="store_true")
    s.add_argument("--base", default="HEAD")
    s.add_argument("--report")
    s = p("wait")
    s.add_argument("--timeout", type=int, default=180)
    s = p("collect")
    s.add_argument("id")
    s.add_argument("--keep-worker", action="store_true")
    s = p("status")
    s.add_argument("--no-planning", dest="planning", action="store_false")
    s = p("watch")
    s.add_argument("--interval", type=int)
    s.add_argument("--once", action="store_true")
    s.add_argument("--quiet", action="store_true")
    s = p("hub")
    s.add_argument("op", choices=["start", "stop"])
    s = p("worktree")
    s.add_argument("op", choices=["create", "merge", "remove", "path"])
    s.add_argument("id")
    s = sub.add_parser("statusline-tap")
    s.add_argument("chain", nargs=argparse.REMAINDER)
    p("gsd-cross-ai")
    p("tools")
    s = p("tool-ask")
    s.add_argument("module")
    s.add_argument("request")
    s.add_argument("--write", action="store_true")
    s.add_argument("--timeout", type=int, default=300)

    a = ap.parse_args(argv)
    if a.cmd == "statusline-tap":
        return cmd_statusline_tap(a)
    try:
        cfg = config.load(a.root)
    except config.ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    if a.cmd == "tools":
        return cmd_tools(cfg, a)
    if a.cmd == "tool-ask":
        return cmd_tools(cfg, a, ask=True)
    try:
        return globals()["cmd_" + a.cmd.replace("-", "_")](cfg, a)
    except (RuntimeError, hc.HCError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
