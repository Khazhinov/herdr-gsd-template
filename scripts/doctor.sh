#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
QUIET=0
[[ ${1:-} == --quiet ]] && QUIET=1

echo "== versions =="
./scripts/version-check.py || true

echo "== repository =="
git rev-parse --show-toplevel >/dev/null
echo "planning: $([[ -d .planning ]] && echo initialized || echo 'not initialized')"

echo "== static checks =="
./scripts/self-check.sh --offline >/dev/null
echo "static checks: PASS"

echo "== herdr-core =="
if hc server status --json >/dev/null 2>&1; then
  echo "core: reachable ($(hc --version))"
  [[ -n ${HC_TERMINAL_ID:-} ]] && echo "this terminal: $HC_TERMINAL_ID" || { ((QUIET)) || echo "not inside an hc terminal: workers will have no parent"; }
else
  echo "core: NOT reachable; workers cannot start" >&2
fi

echo "== quotas and routing =="
python3 scripts/orch.py quota
python3 scripts/orch.py route execute | tail -1
echo "doctor: PASS"
