#!/usr/bin/env python3
"""Re-apply starter-owned runtime settings after the GSD installer rewrites
runtime files. Owns only marked blocks and one settings key:

  .claude/CLAUDE.md        <!-- GSD-HERDR-STARTER --> block
  .codex/config.toml       # GSD-HERDR-PEER-CONFIG block (worker fan-out off)
  .claude/settings.json    statusLine -> orch.py statusline-tap (Claude quota)

The tap chains to the user's global statusline, so nothing visible changes.
An existing project statusLine is kept and chained after the tap.
"""

import json
import re
import shlex
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]

claude = root / ".claude/CLAUDE.md"
claude.parent.mkdir(parents=True, exist_ok=True)
block = (root / ".orchestration/claude-owner-block.md").read_text().strip()
text = claude.read_text() if claude.exists() else ""
pat = re.compile(r"<!-- GSD-HERDR-STARTER:BEGIN -->.*?<!-- GSD-HERDR-STARTER:END -->", re.S)
text = (
    pat.sub(lambda _m: block, text)
    if pat.search(text)
    else text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
)
claude.write_text(text)

settings = root / ".claude/settings.json"
data = (
    json.loads(settings.read_text()) if settings.exists() and settings.read_text().strip() else {}
)
tap = 'python3 "${CLAUDE_PROJECT_DIR:-.}/scripts/orch.py" statusline-tap'
cur = (data.get("statusLine") or {}).get("command", "")
if "statusline-tap" not in cur:
    # Chain an existing project statusline after the tap; empty chain means
    # the tap runs the user's global statusline itself.
    cmd = tap + (" -- " + shlex.quote(cur) if cur else "")
    data["statusLine"] = {"type": "command", "command": cmd}
    settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

codex = root / ".codex/config.toml"
codex.parent.mkdir(parents=True, exist_ok=True)
begin, end = "# GSD-HERDR-PEER-CONFIG:BEGIN", "# GSD-HERDR-PEER-CONFIG:END"
managed = f"""{begin}
[agents]
enabled = false
max_concurrent_threads_per_session = 1
max_depth = 0

[features.multi_agent_v2]
enabled = false
max_concurrent_threads_per_session = 1
{end}"""
if not codex.exists() or not codex.read_text().strip():
    codex.write_text(managed + "\n")
else:
    text = codex.read_text()
    if (begin not in text or end not in text) and "managed by gsd-core installer" in text:
        # GSD is installed for Codex too (an owner-capable Codex). The GSD
        # installer owns [agents]; the worker contract forbids fan-out instead.
        print(
            "note: .codex/config.toml is managed by the GSD installer; worker fan-out block skipped"
        )
    elif begin not in text or end not in text:
        print(
            "Codex config exists but the starter marker block is missing.\n"
            "Merge the block from scripts/reconcile-runtime-config.py into .codex/config.toml "
            "(without duplicating [agents] tables), then rerun.",
            file=sys.stderr,
        )
        raise SystemExit(3)
    else:
        text = re.sub(
            re.escape(begin) + r".*?" + re.escape(end), lambda _m: managed, text, flags=re.S
        )
        codex.write_text(text.rstrip() + "\n")

# Project-local defaults: plain `codex` keeps its own terminal environment.
# The installed CLI exposes daemon_auto_start via `codex features list`.
text = codex.read_text()
if re.search(r"(?m)^daemon_auto_start\s*=", text):
    text = re.sub(r"(?m)^daemon_auto_start\s*=.*$", "daemon_auto_start = false", text)
elif re.search(r"(?m)^\[features\]\s*$", text):
    text = re.sub(r"(?m)^\[features\]\s*$", "[features]\ndaemon_auto_start = false", text, count=1)
else:
    text += "\n[features]\ndaemon_auto_start = false\nhooks = true\n"
codex.write_text(text)

# Preserve generated/vendor hooks and install our idempotent startup handler.
startup = "python3 " + shlex.quote(str(root / "scripts/session-start.py")) + " --hook"
def add_startup(data):
    groups = data.setdefault("hooks", {}).setdefault("SessionStart", [])
    for group in groups:
        group["hooks"] = [h for h in group.get("hooks", []) if "scripts/session-start.py" not in h.get("command", "")]
    groups[:] = [group for group in groups if group.get("hooks")]
    groups.append({"hooks": [{"type": "command", "command": startup, "timeout": 40}]})
    return data

hook_path = root / ".codex/hooks.json"
hook_data = json.loads(hook_path.read_text()) if hook_path.exists() else {}
hook_path.write_text(json.dumps(add_startup(hook_data), indent=2) + "\n")
data = json.loads(settings.read_text()) if settings.exists() else {}
settings.write_text(json.dumps(add_startup(data), indent=2) + "\n")

print("runtime config reconciled")
