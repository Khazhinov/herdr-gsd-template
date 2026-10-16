#!/usr/bin/env python3
import json, subprocess, tempfile
from pathlib import Path
from datetime import UTC, datetime, timedelta

script = Path(__file__).parents[1] / "scripts/codex-limits.py"
future = (datetime.now(UTC) + timedelta(hours=1)).timestamp()

def run(root, threshold=30):
    return subprocess.run(
        [str(script), "--sessions-root", str(root), "--threshold", str(threshold), "--json"],
        capture_output=True, text=True
    )

# Both windows available: most depleted one constrains heavy scheduling.
with tempfile.TemporaryDirectory() as td:
    r = Path(td); p = r / "x"; p.mkdir()
    (p / "rollout-a.jsonl").write_text(json.dumps({
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": {"rate_limits": {
            "primary": {"used_percent": 25, "resets_at": future},
            "secondary": {"used_percent": 60, "resets_at": future}
        }}
    }) + "\n")
    q = run(r, 30)
    assert q.returncode == 0, q.stderr + q.stdout
    d = json.loads(q.stdout)
    assert d["primary"]["remaining_percent"] == 75
    assert d["secondary"]["remaining_percent"] == 40
    assert d["effective_remaining_percent"] == 40
    assert d["heavy_allowed"] is True
    q = run(r, 50)
    assert q.returncode == 1

# A reset window is treated as replenished.
with tempfile.TemporaryDirectory() as td:
    r = Path(td); p = r / "x"; p.mkdir()
    past = (datetime.now(UTC) - timedelta(minutes=1)).timestamp()
    (p / "rollout-a.jsonl").write_text(json.dumps({
        "timestamp": datetime.now(UTC).isoformat(),
        "rate_limits": {"primary": {"used_percent": 99, "resets_at": past}}
    }) + "\n")
    q = run(r, 30)
    assert q.returncode == 0
    assert json.loads(q.stdout)["effective_remaining_percent"] == 100

with tempfile.TemporaryDirectory() as td:
    q = run(Path(td), 30)
    assert q.returncode == 2

print("codex-limits tests: ok")
