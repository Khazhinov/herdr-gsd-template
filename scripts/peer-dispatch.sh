#!/usr/bin/env bash
set -euo pipefail
NAME=${1:?usage: peer-dispatch.sh peer-name task-file}
TASK=${2:?}
[[ -f "$TASK" ]] || { echo "task file missing: $TASK" >&2; exit 2; }
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/.orchestration/config.env"

o=$(herdr agent get "$NAME")
s=$(printf '%s\n' "$o" | jq -r '.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"')
[[ "$s" == idle || "$s" == done ]] || { echo "$NAME not ready: $s" >&2; exit 3; }

if [[ "$NAME" == peer-exec && ${PEER_IGNORE_LIMITS:-0} != 1 ]]; then
  set +e
  ./scripts/codex-limits.py --threshold "${CODEX_HEAVY_THRESHOLD:-30}"
  rc=$?
  set -e
  [[ $rc -eq 0 ]] || { echo "heavy peer routing denied; estimator rc=$rc" >&2; exit 4; }
fi

[[ ${PEER_SKIP_RESET:-0} == 1 ]] || ./scripts/peer-reset.sh "$NAME"

# Submit exactly once. Without --wait, success acknowledges ordered terminal writes,
# not task completion. Never automatically resend after lifecycle ambiguity.
herdr agent prompt "$NAME" "$(cat "$TASK")" --timeout 300000

# Observe briefly for diagnostics only; report/sentinel remains authoritative.
for _ in $(seq 1 5); do
  sleep 1
  o=$(herdr agent get "$NAME")
  s=$(printf '%s\n' "$o" | jq -r '.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"')
  [[ "$s" == working || "$s" == blocked ]] && break
done

printf '%s\n' "$o" | jq -r '.result.agent | {name,status,pane_id}'
if [[ "$s" == idle || "$s" == done || "$s" == unknown ]]; then
  echo "submission was sent exactly once but active work was not observed; inspect before any retry" >&2
fi
echo "completion is report-based; use peer-watch.sh with the expected report path"
