#!/usr/bin/env bash
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
[[ ${HERDR_ENV:-0} == 1 ]] || { echo "run inside owner Herdr pane" >&2; exit 2; }

# shellcheck disable=SC1091
source "$ROOT/.orchestration/config.env"

exists(){ herdr agent get "$1" >/dev/null 2>&1; }

create(){
  local name=$1 model=$2
  exists "$name" && { echo "$name already running"; return; }

  local j pane args=()
  j=$(herdr pane split --current --direction right --cwd "$ROOT" --no-focus)
  pane=$(printf '%s\n' "$j" | jq -r '.result.pane.pane_id')
  [[ -n "$pane" && "$pane" != null ]] || { echo "failed to obtain Herdr pane id" >&2; exit 3; }

  [[ -n "$model" ]] && args+=(-m "$model")

  # Intentionally no `-c model_reasoning_effort=...` CLI override.
  # Keep Codex attached using its native project/user config and shared daemon behavior.
  if ((${#args[@]})); then
    herdr agent start "$name" --kind codex --pane "$pane" -- "${args[@]}"
  else
    herdr agent start "$name" --kind codex --pane "$pane"
  fi
}

create peer-review "${CODEX_REVIEW_MODEL:-}"
create peer-code "${CODEX_CODE_MODEL:-}"
create peer-exec "${CODEX_EXEC_MODEL:-}"

./scripts/peer-status.sh
