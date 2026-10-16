#!/usr/bin/env python3
"""Best-effort Codex rate-limit estimator from local session telemetry.

Exit codes:
  0  effective remaining > threshold (heavy scheduling allowed)
  1  effective remaining <= threshold (short tasks only)
  2  telemetry unavailable / unrecognized

This is not an official billing/quota API. It parses local rollout JSONL that may change.
"""
import argparse
import glob
import json
from datetime import UTC, datetime
from pathlib import Path

def find_rl(x):
    if isinstance(x, dict):
        rl = x.get("rate_limits")
        if isinstance(rl, dict) and (
            isinstance(rl.get("primary"), dict) or isinstance(rl.get("secondary"), dict)
        ):
            return rl
        for v in x.values():
            r = find_rl(v)
            if r:
                return r
    elif isinstance(x, list):
        for v in x:
            r = find_rl(v)
            if r:
                return r
    return None

def window_stats(w, now):
    if not isinstance(w, dict):
        return None
    try:
        used = float(w.get("used_percent", 100))
    except (TypeError, ValueError):
        used = 100.0
    try:
        reset = float(w.get("resets_at", 0) or 0)
    except (TypeError, ValueError):
        reset = 0.0
    remaining = 100.0 if reset and reset <= now else max(0.0, min(100.0, 100.0 - used))
    return {
        "used_percent": round(used, 1),
        "remaining_percent": round(remaining, 1),
        "resets_at": reset,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sessions-root", type=Path, default=Path.home() / ".codex" / "sessions")
    ns = ap.parse_args()

    files = sorted(
        glob.glob(str(ns.sessions_root / "**" / "rollout-*.jsonl"), recursive=True),
        key=lambda f: Path(f).stat().st_mtime,
        reverse=True,
    )[:30]

    best = None
    best_ts = -1.0
    source = None

    for fn in files:
        fallback = Path(fn).stat().st_mtime
        try:
            lines = Path(fn).read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            rl = find_rl(obj)
            if not rl:
                continue
            try:
                ts = datetime.fromisoformat(str(obj.get("timestamp", "")).replace("Z", "+00:00")).timestamp()
            except ValueError:
                ts = fallback
            if ts > best_ts:
                best, best_ts, source = rl, ts, fn

    if not best:
        out = {"available": False, "threshold": ns.threshold, "reason": "telemetry_unavailable"}
        print(json.dumps(out) if ns.json else "codex limits: telemetry unavailable")
        return 2

    now = datetime.now(UTC).timestamp()
    primary = window_stats(best.get("primary"), now)
    secondary = window_stats(best.get("secondary"), now)
    active = [x["remaining_percent"] for x in (primary, secondary) if x is not None]

    if not active:
        out = {"available": False, "threshold": ns.threshold, "reason": "windows_unrecognized"}
        print(json.dumps(out) if ns.json else "codex limits: windows unrecognized")
        return 2

    # Scheduling is constrained by the most depleted visible active window.
    effective = min(active)
    heavy = effective > ns.threshold
    out = {
        "available": True,
        "primary": primary,
        "secondary": secondary,
        "effective_remaining_percent": round(effective, 1),
        "threshold": ns.threshold,
        "heavy_allowed": heavy,
        "source": source,
    }

    if ns.json:
        print(json.dumps(out))
    else:
        bits = []
        if primary:
            bits.append(f"primary={primary['remaining_percent']:.0f}%")
        if secondary:
            bits.append(f"secondary={secondary['remaining_percent']:.0f}%")
        print(
            f"codex limits: {', '.join(bits)}; effective={effective:.0f}%, "
            f"threshold={ns.threshold:.0f}% -> {'heavy allowed' if heavy else 'short tasks only'}"
        )
    return 0 if heavy else 1

if __name__ == "__main__":
    raise SystemExit(main())
