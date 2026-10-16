#!/usr/bin/env bash
set -euo pipefail
NAME=${1:?usage: peer-watch.sh peer report [timeout-sec]}
REPORT=${2:?}
TIMEOUT=${3:-3600}
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/.orchestration/config.env"
POLL=${PEER_POLL_SECONDS:-15}
LIMIT_POLL=${PEER_LIMIT_POLL_SECONDS:-600}
GRACE=${PEER_IDLE_GRACE_SECONDS:-30}
start=$(date +%s)
last_limit=0
sentinel='^(Result: (complete|incomplete)|Major issue: (yes|no))$'

while :; do
  now=$(date +%s)

  if [[ -f "$REPORT" ]] && tail -n1 "$REPORT" | grep -Eq "$sentinel"; then
    echo "report complete: $REPORT"
    tail -n1 "$REPORT"
    exit 0
  fi

  (( now-start < TIMEOUT )) || { echo "timeout waiting report" >&2; exit 1; }

  o=$(herdr agent get "$NAME") || exit 5
  s=$(printf '%s\n' "$o" | jq -r '.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"')

  if [[ "$s" == blocked ]]; then
    echo "$NAME blocked; inspect before input" >&2
    herdr agent read "$NAME" --source recent-unwrapped --lines 80 >&2 || true
    exit 3
  fi

  if [[ "$s" == idle || "$s" == done ]]; then
    (( now-start <= GRACE )) || {
      echo "$NAME settled without report sentinel" >&2
      herdr agent read "$NAME" --source recent-unwrapped --lines 80 >&2 || true
      exit 4
    }
  fi

  if (( now-last_limit >= LIMIT_POLL )); then
    ./scripts/codex-limits.py --threshold "${CODEX_HEAVY_THRESHOLD:-30}" || true
    last_limit=$now
  fi

  sleep "$POLL"
done
