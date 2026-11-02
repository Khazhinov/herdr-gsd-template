#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

echo "== static =="
./scripts/self-check.sh --offline

echo "== overlay =="
./tests/test_overlay.sh

echo "== reconcile =="
python3 ./tests/test_reconcile.py

echo "== routing, quotas, worker lifecycle (fake herdr-core) =="
python3 ./tests/test_orch.py

echo "template test suite: PASS"
