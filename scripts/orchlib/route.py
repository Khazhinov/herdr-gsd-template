"""Deterministic worker selection. Pure: same inputs, same decision.

No agent id appears in this file: everything comes from agents.toml and
routing.toml, plus normalized quota results.
"""

import time

from .config import COST, ConfigError, reserve
from .quota import account, headroom, known


def cost(cfg, costs, aid, weight):
    """Expected quota spend of one task: measured median, else reserves.*.<weight>_cost_percent.
    Capped so a full window always admits one task (a bad sample cannot lock an agent out)."""
    stop = reserve(cfg, aid)[f"{weight}_stop_percent"]
    c = (costs or {}).get(f"{account(cfg, aid)}/{weight}")
    if c is None:
        c = reserve(cfg, aid).get(f"{weight}_cost_percent", 0)
    return max(0.0, min(float(c), 99.0 - stop))


def decide(
    cfg,
    role,
    quotas,
    running=None,
    heavy=None,
    override=None,
    installed=None,
    now=None,
    costs=None,
    pending=None,
):
    """costs: measured spend per "<account>/<weight>"; pending: per account, the
    expected spend still ahead of running tasks. Both default to none."""
    r = cfg["routing"]
    pol = r.get("roles", {}).get(role)
    if pol is None:
        raise ConfigError(f"routing.toml has no role {role!r}")
    now = now or time.time()
    running = running or {}
    heavy = pol.get("heavy", False) if heavy is None else heavy
    weight = "heavy" if heavy else "light"
    owner = r["owner"]
    auto = set(r.get("auto_stability", ["supported"]))
    unknown_policy = r.get("unknown_quota", {}).get(weight, "deny")
    strategy = pol.get("strategy", "ordered")

    cands = []
    for rank, aid in enumerate(pol.get("chain", [])):
        a = cfg["agents"][aid]
        q = quotas.get(aid)
        c = {
            "agent": aid,
            "rank": rank,
            "eligible": True,
            "why": [],
            "remaining": q.get("effective_remaining_percent") if known(q) else None,
            "headroom": headroom(q, now),
        }

        def deny(msg, c=c):
            c["eligible"] = False
            c["why"].append(msg)

        if role not in a["capabilities"]:
            deny(f"no {role} capability")
        if a["stability"] not in auto and aid != override:
            deny(f"stability {a['stability']} is not auto-routable")
        if installed is not None and not installed.get(aid, False):
            deny("not installed")
        n, cap = running.get(aid, 0), a.get("max_parallel", 1)
        if n >= cap:
            deny(f"busy {n}/{cap}")
        stop = reserve(cfg, aid)[f"{weight}_stop_percent"]
        if known(q):
            # The reserve must survive the task: subtract what running tasks on
            # the same account and this task are expected to spend.
            rem, ahead, mine = (
                q["effective_remaining_percent"],
                (pending or {}).get(account(cfg, aid), 0),
                cost(cfg, costs, aid, weight),
            )
            left = rem - ahead - mine
            calc = (
                f"quota {rem:.0f}%"
                + (f" - {ahead:.0f}% running" if ahead else "")
                + (f" - {mine:.0f}% this task = {left:.0f}%" if mine or ahead else "")
            )
            if left <= stop:
                deny(f"{calc} <= {weight} reserve {stop}%")
            else:
                c["why"].append(f"{calc} > {weight} reserve {stop}%")
        elif unknown_policy == "deny":
            state = "stale" if q and q.get("stale") else "unknown"
            deny(f"quota {state}: {weight} work fails closed")
        else:
            c["why"].append(f"quota unknown, allowed for {weight} work")
        cands.append(c)

    eligible = [c for c in cands if c["eligible"]]
    pool = eligible
    if pol.get("independent"):
        pool = [c for c in eligible if c["agent"] != owner] or eligible

    pick, how = None, strategy
    if override and any(c["agent"] == override for c in eligible):
        pick, how = next(c for c in eligible if c["agent"] == override), "manual override"
    elif pool:
        if strategy == "cheapest":
            pick = min(
                pool, key=lambda c: (COST[cfg["agents"][c["agent"]]["cost_tier"]], c["rank"])
            )
        elif strategy == "use-or-lose":
            pick = max(
                pool, key=lambda c: (c["headroom"] if c["headroom"] is not None else -1, -c["rank"])
            )
        else:
            pick = pool[0]

    selected = pick["agent"] if pick else None
    independent = (selected != owner) if (pol.get("independent") and selected) else None
    if pick:
        reason = f"{selected} for {role}/{weight} by {how}: {'; '.join(pick['why'])}"
        skipped = [
            f"{c['agent']} ({'; '.join(c['why'])})"
            for c in cands
            if c is not pick and c["rank"] < pick["rank"]
        ]
        if skipped:
            reason += " | skipped " + ", ".join(skipped)
        if independent is False:
            reason += " | NOT independent: only the owner was eligible"
    else:
        reason = f"no eligible agent for {role}/{weight}: " + ", ".join(
            f"{c['agent']} ({'; '.join(c['why'])})" for c in cands
        )
    if override and how != "manual override":
        reason += f" | override {override} ignored: not eligible"
    return {
        "role": role,
        "weight": weight,
        "strategy": strategy,
        "selected": selected,
        "independent": independent,
        "owner": owner,
        "reason": reason,
        "candidates": cands,
        "decided_at": now,
    }
