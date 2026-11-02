#!/usr/bin/env python3
"""Every key of gsd-policy.overlay.json must be accepted by the pinned GSD's
own validator (config-schema.cjs: manifest keys + capability keys + patterns).
CI installs GSD first; argv[1] may name another gsd-core directory."""
import json
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cands = [Path(sys.argv[1])] if len(sys.argv) > 1 else [root / ".claude/gsd-core", Path.home() / ".claude/gsd-core"]
core = next((p for p in cands if (p / "bin/lib/config-schema.cjs").exists()), None)
if core is None:
    print("gsd keys: SKIP (GSD not installed here)")
    raise SystemExit(0)


def flat(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from flat(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}"


keys = list(flat(json.loads((root / ".orchestration/gsd-policy.overlay.json").read_text())))
js = ("const c=require(process.argv[1]);const ks=JSON.parse(process.argv[2]);"
      "console.log(JSON.stringify(ks.filter(k=>!c.isValidConfigKey(k))))")
bad = json.loads(subprocess.run(["node", "-e", js, str(core / "bin/lib/config-schema.cjs"), json.dumps(keys)],
                                check=True, capture_output=True, text=True).stdout)
if bad:
    raise SystemExit(f"overlay keys unknown to GSD at {core}: {bad}")
print(f"gsd keys: ok ({len(keys)} keys, {core})")
