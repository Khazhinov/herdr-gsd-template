#!/usr/bin/env bash
# Start a fresh Codex chat without changing process cwd.
set -euo pipefail
NAME=${1:?usage: peer-reset.sh peer-name}

o=$(herdr agent get "$NAME")
status=$(printf '%s\n' "$o" | jq -r '.result.agent.status // .result.agent.agent_status // .result.agent.state // "unknown"')
[[ "$status" == idle || "$status" == done ]] || { echo "$NAME not reset-safe: $status" >&2; exit 3; }

# Current Codex TUI: /clear starts a new chat.
# Herdr agent prompt submits text + Enter as one ordered operation.
herdr agent prompt "$NAME" "/clear" --timeout 300000

# This wait is only readiness after reset; it is not a project-task completion check.
herdr agent wait "$NAME" --until idle --until done --timeout 300000 >/dev/null
