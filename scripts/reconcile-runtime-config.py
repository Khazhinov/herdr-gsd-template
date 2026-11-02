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
text = pat.sub(lambda _m: block, text) if pat.search(text) else text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
claude.write_text(text)

settings = root / ".claude/settings.json"
data = json.loads(settings.read_text()) if settings.exists() and settings.read_text().strip() else {}
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
    if begin not in text or end not in text:
        print("Codex config exists but the starter marker block is missing.\n"
              "Merge the block from scripts/reconcile-runtime-config.py into .codex/config.toml "
              "(without duplicating [agents] tables), then rerun.", file=sys.stderr)
        raise SystemExit(3)
    text = re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _m: managed, text, flags=re.S)
    codex.write_text(text.rstrip() + "\n")

print("runtime config reconciled")
