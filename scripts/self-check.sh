#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
OFFLINE=0
[[ ${1:-} == --offline ]] && OFFLINE=1
cleanup_pycache(){ find scripts tests -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true; }
trap cleanup_pycache EXIT

fail(){ echo "FAIL: $*" >&2; exit 1; }

required=(
  README.md AGENTS.md LICENSE
  .claude/CLAUDE.md .codex/config.toml
  .orchestration/versions.env .orchestration/owner.env
  .agents/skills/gsd-context-discipline/SKILL.md
  .agents/skills/herdr-peer/SKILL.md
  scripts/peer-dispatch.sh scripts/peer-watch.sh scripts/peer-worktree.sh
  scripts/codex-limits.py scripts/version-check.py scripts/doctor.sh
)
for f in "${required[@]}"; do [[ -f "$f" ]] || fail "missing $f"; done

for f in scripts/*.sh scripts/*.py; do [[ -x "$f" ]] || fail "not executable $f"; done
for f in scripts/*.sh; do bash -n "$f"; done

python3 -m py_compile scripts/*.py tests/*.py
python3 tests/test_codex_limits.py
python3 tests/test_reconcile.py

python3 - <<'PY'
import json, tomllib
json.load(open('.orchestration/gsd-policy.overlay.json'))
tomllib.load(open('.codex/config.toml','rb'))
print('config syntax: ok')
PY

grep -q 'GSD_VERSION=${GSD_VERSION:-1.17.0}' .orchestration/versions.env || fail "GSD pin drift"
grep -q 'HERDR_MIN_VERSION=${HERDR_MIN_VERSION:-0.9.3}' .orchestration/versions.env || fail "Herdr baseline drift"
grep -q 'CLAUDE_MIN_VERSION=${CLAUDE_MIN_VERSION:-2.1.301}' .orchestration/versions.env || fail "Claude baseline drift"
grep -q 'CODEX_MIN_VERSION=${CODEX_MIN_VERSION:-0.163.0}' .orchestration/versions.env || fail "Codex baseline drift"

grep -q 'enabled = false' .codex/config.toml || fail "Codex peer fan-out guard missing"
grep -q 'max_concurrent_threads_per_session = 1' .codex/config.toml || fail "Codex peer concurrency guard missing"
grep -q 'ORCHESTRATION_OWNER=' .orchestration/owner.env || fail "owner marker missing"

unsafe_targets=(
  .codex/config.toml
  scripts
  .orchestration/config.env
  .orchestration/owner.env
  .orchestration/gsd-policy.overlay.json
)

! grep -R --exclude=self-check.sh -nE \
  'danger-full-access|approval_policy *= *"?never|ask-for-approval +never' \
  "${unsafe_targets[@]}" >/dev/null \
  || fail "unsafe shared Codex default found"

! grep -R -nE 'args\+=\([^)]*-c[^)]*model_reasoning_effort|agent start.*-c.*model_reasoning_effort' scripts/herdr-ensure-peers.sh scripts/peer-restart-in.sh >/dev/null \
  || fail "per-start Codex reasoning override reintroduced"

grep -q 'herdr agent prompt' scripts/peer-dispatch.sh || fail "Herdr agent API missing"
! grep -q 'pane send-text' scripts/peer-dispatch.sh || fail "raw pane dispatch found"
grep -q 'peer-root.sh.*peer-exec' scripts/peer-worktree.sh || fail "root-before-remove invariant missing"
grep -q 'agent prompt "$NAME" "/clear"' scripts/peer-reset.sh || fail "fresh Codex context reset missing"
grep -q 'peer-restart-in.sh.*peer-exec' scripts/peer-worktree.sh || fail "worktree relocation helper missing"

grep -q 'https://github.com/open-gsd/gsd-core' README.md || fail "GSD link missing"
grep -q 'https://github.com/herdrdev/herdr' README.md || fail "Herdr link missing"
grep -q 'https://github.com/anthropics/claude-code' README.md || fail "Claude link missing"
grep -q 'https://github.com/openai/codex' README.md || fail "Codex link missing"
grep -q 'https://t.me/thoughts_and_bytes/27' README.md || fail "talk post link missing"

python3 - <<'PY'
from pathlib import Path
bad = ['aut'+'o-kalym', 'zv'+'enir']
for p in Path('.').rglob('*'):
    if p.is_file() and '.git' not in p.parts:
        t = p.read_text(errors='ignore').lower()
        for x in bad:
            if x in t:
                raise SystemExit(f'domain leak: {p}')
print('privacy scan: ok')
PY

if (( ! OFFLINE )); then
  ./scripts/version-check.py --strict
fi

echo 'self-check: PASS'
