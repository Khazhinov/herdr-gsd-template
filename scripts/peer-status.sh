#!/usr/bin/env bash
set -euo pipefail
for a in peer-review peer-code peer-exec; do
  if o=$(herdr agent get "$a" 2>/dev/null); then printf '%s\n' "$o"|jq -r --arg a "$a" '[$a, (.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"), (.result.agent.pane_id // "?")] | @tsv';
  else printf '%s\tmissing\n' "$a"; fi
done
