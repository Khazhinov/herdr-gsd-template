#!/usr/bin/env python3
import json, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".planning/config.json"
overlay = root / ".orchestration/gsd-policy.overlay.json"

if not target.exists():
    print("missing .planning/config.json; run GSD new-project/onboard first", file=sys.stderr)
    raise SystemExit(2)

def merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a

data = json.loads(target.read_text())
policy = json.loads(overlay.read_text())
merge(data, policy)
target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
print("GSD orchestration policy applied")
print("ownership remains controlled by .orchestration/owner.env, not by GSD runtime")
