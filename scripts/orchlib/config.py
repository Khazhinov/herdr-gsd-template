"""Load and validate the agent registry and routing policy."""

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLES = {"owner", "plan", "execute", "review", "research", "debug"}
STABILITY = {"supported", "candidate", "experimental"}
COST = {"cheap": 0, "standard": 1, "premium": 2}
PROBES = {"codex", "claude", "static", "none"}
STRATEGIES = {"ordered", "cheapest", "use-or-lose"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


class ConfigError(Exception):
    pass


def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


def _toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def load(root=None):
    root = Path(root or os.environ.get("ORCH_ROOT") or ROOT).resolve()
    orch = root / ".orchestration"
    agents = _toml(orch / "agents.toml")
    routing = _toml(orch / "routing.toml")
    # Local overrides stay out of git: personal models, sandbox flags, budgets.
    for base, name in ((agents, "agents.local.toml"), (routing, "routing.local.toml")):
        p = orch / name
        if p.exists():
            merge(base, _toml(p))
    cfg = {"root": root, "agents": agents.get("agents", {}), "routing": routing}
    validate(cfg)
    return cfg


def validate(cfg):
    agents, r = cfg["agents"], cfg["routing"]
    if not agents:
        raise ConfigError("agents.toml defines no agents")
    for aid, a in agents.items():
        where = f"agents.{aid}"
        if not NAME_RE.match(aid):
            raise ConfigError(f"{where}: id must match {NAME_RE.pattern}")
        cmd = a.get("command")
        if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
            raise ConfigError(f"{where}.command must be a non-empty list of strings")
        if a.get("prompt", "arg") not in ("arg", "send"):
            raise ConfigError(f"{where}.prompt must be 'arg' or 'send'")
        bad = set(a.get("capabilities", [])) - ROLES
        if bad or not a.get("capabilities"):
            raise ConfigError(f"{where}.capabilities invalid: {sorted(bad) or 'empty'}")
        if a.get("cost_tier") not in COST:
            raise ConfigError(f"{where}.cost_tier must be one of {sorted(COST)}")
        if a.get("quota", "none") not in PROBES:
            raise ConfigError(
                f"{where}.quota: unknown probe {a.get('quota')!r}; known {sorted(PROBES)}"
            )
        if a.get("stability") not in STABILITY:
            raise ConfigError(f"{where}.stability must be one of {sorted(STABILITY)}")
    owner = r.get("owner")
    if owner not in agents or "owner" not in agents[owner]["capabilities"]:
        raise ConfigError(f"routing.owner {owner!r} is not an agent with the owner capability")
    for role, pol in r.get("roles", {}).items():
        if role not in ROLES:
            raise ConfigError(f"routing.roles.{role}: unknown role")
        if pol.get("strategy", "ordered") not in STRATEGIES:
            raise ConfigError(f"routing.roles.{role}.strategy must be one of {sorted(STRATEGIES)}")
        for aid in pol.get("chain", []):
            if aid not in agents:
                raise ConfigError(f"routing.roles.{role}.chain: unknown agent {aid!r}")
    for k in ("heavy", "light"):
        if r.get("unknown_quota", {}).get(k, "deny") not in ("deny", "allow"):
            raise ConfigError(f"routing.unknown_quota.{k} must be deny or allow")


def reserve(cfg, aid):
    res = cfg["routing"].get("reserves", {})
    out = {"heavy_stop_percent": 30, "light_stop_percent": 10}
    out.update(res.get("default", {}))
    out.update(res.get(aid, {}))
    return out


def project_name(cfg):
    name = re.sub(r"[^a-z0-9_-]+", "-", cfg["root"].name.lower()).strip("-") or "project"
    return name[:24]
