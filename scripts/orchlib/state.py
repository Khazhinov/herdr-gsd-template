"""One machine-readable snapshot for dashboards: routing, quotas, tasks, GSD.

Published three ways, all optional for orchestration itself:
  .orchestration/runtime/state.json   (files: Herdr App mod, TUI, humans)
  hc document orch-<project>          (herdr-core doc event for subscribers)
  labels on the watch terminal        (orch.rev, orch.q.*: re-render trigger
                                       for Herdr App mods without polling)
"""
import glob
import json
import re
import subprocess
import time
from pathlib import Path

from . import hc, quota, tasks
from .config import project_name


def gsd_tools(root):
    for pat in (".claude/gsd-core/bin/gsd-tools.cjs", ".codex/gsd-core/bin/gsd-tools.cjs",
                str(Path.home() / ".claude/gsd-core/bin/gsd-tools.cjs")):
        hits = glob.glob(str(root / pat)) if not pat.startswith("/") else glob.glob(pat)
        if hits:
            return hits[0]
    return None


def stopped_at(root):
    """GSD's own resume point from the STATE.md frontmatter."""
    try:
        head = (root / ".planning" / "STATE.md").read_text().split("---")[1]
    except (OSError, IndexError):
        return None
    m = re.search(r"^stopped_at:\s*(.+)$", head, re.M)
    return m.group(1).strip().strip('"') if m else None


def planning(root):
    """GSD's own read-only snapshot (planning.inspect, schema v1, GSD >= 1.19)."""
    if not (root / ".planning").exists():
        return {"available": False, "reason": "no .planning/"}
    tool = gsd_tools(root)
    if not tool:
        return {"available": False, "reason": "GSD not installed in this project"}
    try:
        p = subprocess.run(["node", tool, "query", "planning", "inspect"], cwd=root,
                           capture_output=True, text=True, timeout=30)
        out = p.stdout.strip()
        # Payloads over 50 KB spill to a temp file: "@file:<path>".
        data = json.loads(Path(out[6:]).read_text() if out.startswith("@file:") else out)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"available": False, "reason": f"planning.inspect unavailable: {e}"}
    if data.get("schema_version") != 1:
        return {"available": False, "reason": f"unsupported planning.inspect schema {data.get('schema_version')}"}
    return {"available": True, "stopped_at": stopped_at(root), **summarize(data)}


def _v(x):
    return x.get("value") if isinstance(x, dict) else x


def summarize(d):
    phases = []
    for ph in d.get("phases", []):
        plans = ph.get("plans") or []
        phases.append({
            "id": ph.get("phase_id"), "dir": ph.get("dir"), "complete": ph.get("complete"),
            "goal": _v(ph.get("goal")),
            "verification": (ph.get("verification") or {}).get("status"),
            "plans": [{"id": p.get("id"), "complete": bool(p.get("hasSummary")), "wave": p.get("wave"),
                       "title": (p.get("objective") or "").strip().splitlines()[0][:120] if p.get("objective") else None}
                      for p in plans if isinstance(p, dict) and not p.get("superseded")],
        })
    act = d.get("active") or {}
    prog = d.get("progress") or {}
    return {"milestone": (d.get("milestone") or {}).get("version"),
            "progress": {k: v for k, v in prog.items()},
            "milestone_name": (d.get("milestone") or {}).get("name"),
            "phase": _v(act.get("phase")), "plan": _v(act.get("plan")), "status": _v(act.get("status")),
            "phases": phases}


def providers(cfg, quotas, now):
    """Quota per agent environment (one account per probe kind), not per
    model variant: variants of one CLI share the same windows."""
    out = {}
    for aid, a in cfg["agents"].items():
        kind = a.get("quota", "none")
        if kind == "none" or aid not in quotas:
            continue
        key = kind if kind in ("codex", "claude") else aid
        q = quotas[aid]
        if key not in out:
            out[key] = {k: q.get(k) for k in ("available", "confidence", "stale", "windows", "observed_at", "extra")}
            out[key]["agents"] = []
        out[key]["agents"].append(aid)
    return out


def compose(cfg, quotas=None, with_planning=True, terminals=None):
    quotas = quotas or quota.all_quotas(cfg)
    now = time.time()
    try:
        terms = terminals if terminals is not None else hc.ls(all_=True)
    except Exception:
        terms = []
    tools = [{"name": t.get("name"), "address": t.get("address"), "tool": (t.get("labels") or {}).get("orch.tool"),
              "status": (t.get("status") or {}).get("state") if isinstance(t.get("status"), dict) else t.get("status"),
              "state": t.get("state")}
             for t in terms if (t.get("labels") or {}).get("orch.tool")]
    return {"schema": 1, "project": project_name(cfg), "root": str(cfg["root"]),
            "owner": cfg["routing"]["owner"], "updated_at": now,
            "quotas": {a: {k: q.get(k) for k in ("available", "confidence", "stale", "windows",
                                                 "effective_remaining_percent", "observed_at", "extra", "source")}
                       | {"headroom": quota.headroom(q, now)} for a, q in quotas.items()},
            "providers": providers(cfg, quotas, now),
            "routing": {role: {k: d[k] for k in ("selected", "weight", "strategy", "independent", "reason")}
                        for role, d in tasks.preview(cfg, quotas).items()},
            "override": tasks.override_get(cfg),
            "tasks": [{k: t.get(k) for k in ("id", "role", "agent", "state", "terminal", "name", "branch", "report",
                                             "started_at", "finished_at", "verdict", "live", "sentinel",
                                             "independent", "reason")}
                      for t in tasks.refresh(cfg, terms)],
            "tools": tools,
            "planning": planning(cfg["root"]) if with_planning else None}


def publish(cfg, state, hub=None, rev=None):
    path = tasks.runtime(cfg) / "state.json"
    tasks.write_json(path, state)
    hc.doc_put_once(f"orch-{state['project']}"[:32], state)
    if hub:
        labels = {"orch.hub": state["project"], "orch.state": str(path), "orch.rev": str(rev or int(state["updated_at"]))}
        for a, q in state["quotas"].items():
            eff = q.get("effective_remaining_percent")
            labels[f"orch.q.{a}"] = "?" if eff is None or q.get("stale") else f"{eff:.0f}"
        for role, d in state["routing"].items():
            labels[f"orch.route.{role}"] = d["selected"] or "-"
        try:
            hc.label(hub, labels)
        except hc.HCError:
            pass
    return path
