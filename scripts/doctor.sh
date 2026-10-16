#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
QUIET=0
[[ ${1:-} == --quiet ]] && QUIET=1

echo "== versions =="
./scripts/version-check.py --strict

echo "== repository =="
git rev-parse --show-toplevel >/dev/null
python3 - <<'PY'
from pathlib import Path
owner={}
for raw in Path('.orchestration/owner.env').read_text().splitlines():
    if raw.startswith('ORCHESTRATION_OWNER='):
        owner['owner']=raw
print("owner marker: .orchestration/owner.env")
print("planning:", "initialized" if Path('.planning').exists() else "not initialized")
PY

echo "== static checks =="
./scripts/self-check.sh --offline >/dev/null
echo "static checks: PASS"

if [[ ${HERDR_ENV:-0} == 1 ]]; then
  echo "== Herdr =="
  herdr --version
  ./scripts/peer-status.sh || true
else
  (( QUIET )) || echo "Herdr runtime: not inside a Herdr pane (HERDR_ENV != 1)"
fi

set +e
./scripts/codex-limits.py --json
LIMIT_RC=$?
set -e
case "$LIMIT_RC" in
  0|1) ;;
  2) (( QUIET )) || echo "Codex quota telemetry: unavailable; heavy auto-routing will fail closed" ;;
  *) echo "Codex quota estimator unexpected rc=$LIMIT_RC" >&2; exit "$LIMIT_RC" ;;
esac

echo "doctor: PASS"
