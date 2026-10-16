#!/usr/bin/env bash
# Exit a managed Codex agent and restart it in an explicit directory.
set -euo pipefail
NAME=${1:?usage: peer-restart-in.sh peer-name directory}
DIR=${2:?}
ROOT=$(git rev-parse --show-toplevel)
DIR=$(cd "$DIR" && pwd)

# shellcheck disable=SC1091
source "$ROOT/.orchestration/config.env"

o=$(herdr agent get "$NAME")
status=$(printf '%s\n' "$o" | jq -r '.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"')
pane=$(printf '%s\n' "$o" | jq -r '.result.agent.pane_id')
[[ "$status" == idle || "$status" == done ]] || { echo "$NAME not restart-safe: $status" >&2; exit 3; }

case "$NAME" in
  peer-review) model=${CODEX_REVIEW_MODEL:-};;
  peer-code) model=${CODEX_CODE_MODEL:-};;
  peer-exec) model=${CODEX_EXEC_MODEL:-};;
  *) echo "unknown managed peer: $NAME" >&2; exit 2;;
esac

# No blind retry: if /exit was submitted but agent remains, stop for inspection.
herdr agent prompt "$NAME" "/exit" --timeout 300000 || true
for _ in $(seq 1 30); do
  herdr agent get "$NAME" >/dev/null 2>&1 || break
  sleep 1
done
herdr agent get "$NAME" >/dev/null 2>&1 && { echo "$NAME did not exit; inspect manually" >&2; exit 1; }

herdr pane run "$pane" "cd $(printf '%q' "$DIR")"

args=()
[[ -n "$model" ]] && args+=(-m "$model")
if ((${#args[@]})); then
  herdr agent start "$NAME" --kind codex --pane "$pane" -- "${args[@]}"
else
  herdr agent start "$NAME" --kind codex --pane "$pane"
fi
echo "$NAME restarted in $DIR"
