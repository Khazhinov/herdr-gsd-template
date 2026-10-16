#!/usr/bin/env python3
"""Re-apply starter-owned runtime settings after GSD installer updates runtime files.

The official GSD installer owns its generated runtime surfaces.
This script restores only the starter's marked Claude protocol block and
refreshes an already-merged Codex peer-policy block.

For an existing repository, a pre-existing Codex config must be merged manually
first. This script deliberately refuses to inject duplicate TOML tables.
"""
from pathlib import Path
import re
import sys

root = Path(__file__).resolve().parents[1]

# Claude: the GSD installer may regenerate/replace this file. A uniquely marked
# block can be safely appended/replaced without taking ownership of the rest.
claude = root / ".claude/CLAUDE.md"
claude.parent.mkdir(parents=True, exist_ok=True)
block = (root / ".orchestration/claude-owner-block.md").read_text().strip()
text = claude.read_text() if claude.exists() else ""
pat = re.compile(
    r"<!-- GSD-HERDR-STARTER:BEGIN -->.*?<!-- GSD-HERDR-STARTER:END -->",
    re.S,
)
text = pat.sub(block, text) if pat.search(text) else text.rstrip() + ("\n\n" if text.strip() else "") + block + "\n"
claude.write_text(text)

# Codex: the public template owns only the explicitly marked block.
# Never append a second [agents] / [features.multi_agent_v2] table to an
# arbitrary existing config.
codex = root / ".codex/config.toml"
codex.parent.mkdir(parents=True, exist_ok=True)
begin = "# GSD-HERDR-PEER-CONFIG:BEGIN"
end = "# GSD-HERDR-PEER-CONFIG:END"
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
        print(
            "Codex config exists but starter marker block is missing.\n"
            "Merge `.orchestration/merge-required/codex-config.toml` (or the starter block) "
            "into `.codex/config.toml` before bootstrap/reconcile.",
            file=sys.stderr,
        )
        raise SystemExit(3)
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    text = pat.sub(managed, text)
    codex.write_text(text.rstrip() + "\n")

print("runtime config reconciled")
