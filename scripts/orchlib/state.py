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
    for pat in (
        ".claude/gsd-core/bin/gsd-tools.cjs",
        ".codex/gsd-core/bin/gsd-tools.cjs",
        str(Path.home() / ".claude/gsd-core/bin/gsd-tools.cjs"),
    ):
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


def gsd_query(root, tool, *args):
    p = subprocess.run(
        ["node", tool, "query", *args], cwd=root, capture_output=True, text=True, timeout=30
    )
    out = p.stdout.strip()
    # Payloads over 50 KB spill to a temp file: "@file:<path>".
    return json.loads(Path(out[6:]).read_text() if out.startswith("@file:") else out)


def planning(root):
    """The whole milestone plan as GSD knows it: every ROADMAP phase
    (`roadmap analyze`) and, for phases already planned, their plans, waves and
    tasks (`planning.inspect`, schema v1, GSD >= 1.19). Read-only queries."""
    if not (root / ".planning").exists():
        return {"available": False, "reason": "no .planning/"}
    tool = gsd_tools(root)
    if not tool:
        return {"available": False, "reason": "GSD not installed in this project"}
    try:
        data = gsd_query(root, tool, "planning", "inspect")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"available": False, "reason": f"planning.inspect unavailable: {e}"}
    if data.get("schema_version") != 1:
        return {
            "available": False,
            "reason": f"unsupported planning.inspect schema {data.get('schema_version')}",
        }
    try:
        roadmap = gsd_query(root, tool, "roadmap", "analyze")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        roadmap = {}
    return {"available": True, "stopped_at": stopped_at(root), **summarize(data, roadmap)}


def _v(x):
    return x.get("value") if isinstance(x, dict) else x


def _first_line(text, n=140):
    return text.strip().splitlines()[0][:n] if isinstance(text, str) and text.strip() else None


def summarize(d, roadmap=None):
    planned = {}
    for ph in d.get("phases", []):
        plans = []
        for p in ph.get("plans") or []:
            if not isinstance(p, dict) or p.get("superseded"):
                continue
            plans.append(
                {
                    "id": p.get("id"),
                    "complete": bool(p.get("hasSummary")),
                    "wave": p.get("wave"),
                    "title": _first_line(p.get("objective")),
                    "tasks": [
                        {
                            "n": t.get("index"),
                            "name": _first_line(t.get("name"), 100)
                            or t.get("type")
                            or t.get("kind"),
                            "status": t.get("status") or "unknown",
                            "checkpoint": "checkpoint" in str(t.get("type") or t.get("kind") or ""),
                        }
                        for t in p.get("tasks") or []
                        if isinstance(t, dict)
                    ],
                }
            )
        planned[str(ph.get("phase_id"))] = {
            "dir": ph.get("dir"),
            "complete": ph.get("complete"),
            "goal": _v(ph.get("goal")),
            "verification": (ph.get("verification") or {}).get("status"),
            "plans": plans,
        }
    phases = []
    for rp in (roadmap or {}).get("phases", []):
        num = str(rp.get("number"))
        ph = planned.pop(num, {})
        phases.append(
            {
                "id": num,
                "name": rp.get("name"),
                "goal": rp.get("goal") or ph.get("goal"),
                "status": rp.get("disk_status"),
                "complete": bool(rp.get("roadmap_complete") or ph.get("complete")),
                "verification": ph.get("verification"),
                "plans": ph.get("plans", []),
            }
        )
    # Phases on disk that the ROADMAP no longer lists still show.
    for num, ph in planned.items():
        phases.append(
            {
                "id": num,
                "name": ph.get("dir"),
                "goal": ph.get("goal"),
                "status": None,
                "complete": ph.get("complete"),
                "verification": ph.get("verification"),
                "plans": ph["plans"],
            }
        )
    act = d.get("active") or {}
    return {
        "milestone": (d.get("milestone") or {}).get("version"),
        "milestone_name": (d.get("milestone") or {}).get("name"),
        "progress": (roadmap or {}).get("progress_percent"),
        "phase": _v(act.get("phase")),
        "plan": _v(act.get("plan")),
        "status": _v(act.get("status")),
        "phases": phases,
    }


def providers(cfg, quotas, now, costs=None):
    """Quota per agent environment (one account per probe kind), not per
    model variant: variants of one CLI share the same windows."""
    out = {}
    for aid, a in cfg["agents"].items():
        kind = a.get("quota", "none")
        if kind == "none" or aid not in quotas:
            continue
        key = quota.account(cfg, aid)
        q = quotas[aid]
        if key not in out:
            out[key] = {
                k: q.get(k)
                for k in ("available", "confidence", "stale", "windows", "observed_at", "extra")
            }
            out[key]["agents"] = []
            # Measured spend of one task on this account (see tasks.costs).
            out[key]["task_cost"] = {w: (costs or {}).get(f"{key}/{w}") for w in ("heavy", "light")}
        out[key]["agents"].append(aid)
    return out


def compose(cfg, quotas=None, with_planning=True, terminals=None):
    quotas = quotas or quota.all_quotas(cfg)
    now = time.time()
    try:
        terms = terminals if terminals is not None else hc.ls(all_=True)
    except Exception:
        terms = []
    tools = [
        {
            "name": t.get("name"),
            "address": t.get("address"),
            "tool": (t.get("labels") or {}).get("orch.tool"),
            "status": (t.get("status") or {}).get("state")
            if isinstance(t.get("status"), dict)
            else t.get("status"),
            "state": t.get("state"),
        }
        for t in terms
        if (t.get("labels") or {}).get("orch.tool")
    ]
    return {
        "schema": 1,
        "project": project_name(cfg),
        "root": str(cfg["root"]),
        "owner": cfg["routing"]["owner"],
        "updated_at": now,
        "quotas": {
            a: {
                k: q.get(k)
                for k in (
                    "available",
                    "confidence",
                    "stale",
                    "windows",
                    "effective_remaining_percent",
                    "observed_at",
                    "extra",
                    "source",
                )
            }
            | {"headroom": quota.headroom(q, now)}
            for a, q in quotas.items()
        },
        "providers": providers(cfg, quotas, now, tasks.costs(cfg)),
        "routing": {
            role: {k: d[k] for k in ("selected", "weight", "strategy", "independent", "reason")}
            for role, d in tasks.preview(cfg, quotas).items()
        },
        "override": tasks.override_get(cfg),
        "tasks": [
            {
                k: t.get(k)
                for k in (
                    "id",
                    "role",
                    "agent",
                    "state",
                    "terminal",
                    "name",
                    "branch",
                    "report",
                    "started_at",
                    "finished_at",
                    "verdict",
                    "live",
                    "sentinel",
                    "independent",
                    "reason",
                )
            }
            for t in tasks.refresh(cfg, terms)
        ],
        "tools": tools,
        "planning": planning(cfg["root"]) if with_planning else None,
    }


def publish(cfg, state, hub=None, rev=None):
    path = tasks.runtime(cfg) / "state.json"
    tasks.write_json(path, state)
    hc.doc_put_once(f"orch-{state['project']}"[:32], state)
    if hub:
        labels = {
            "orch.hub": state["project"],
            "orch.state": str(path),
            "orch.rev": str(rev or int(state["updated_at"])),
        }
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
