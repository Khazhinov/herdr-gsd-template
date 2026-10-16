#!/usr/bin/env bash
set -euo pipefail
NAME=${1:?usage: peer-root.sh peer-name}; ROOT=$(git rev-parse --show-toplevel)
exec "$ROOT/scripts/peer-restart-in.sh" "$NAME" "$ROOT"
