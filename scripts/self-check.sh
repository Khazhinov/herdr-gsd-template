#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
OFFLINE=0
[[ ${1:-} == --offline ]] && OFFLINE=1
export PYTHONDONTWRITEBYTECODE=1

fail(){ echo "FAIL: $*" >&2; exit 1; }

# The template repository carries .orchestration/template-repo; projects that
# received the overlay do not (install-into-repo.sh skips it).
TEMPLATE=0
[[ -f .orchestration/template-repo ]] && TEMPLATE=1

required=(
  AGENTS.md .claude/CLAUDE.md
  .orchestration/versions.env .orchestration/agents.toml .orchestration/routing.toml
  .orchestration/templates/task.md .orchestration/templates/report.md
  .agents/skills/gsd-context-discipline/SKILL.md .agents/skills/orch-workers/SKILL.md
  scripts/orch.py scripts/orchlib/route.py scripts/orchlib/quota.py scripts/orchlib/tasks.py
  scripts/version-check.py scripts/doctor.sh herdr-app/gsd-mission-control/main.js
)
(( TEMPLATE )) && required+=(README.md LICENSE .codex/config.toml tests/test_orch.py)
for f in "${required[@]}"; do [[ -f "$f" ]] || fail "missing $f"; done

for f in scripts/*.sh scripts/*.py; do [[ -x "$f" ]] || fail "not executable $f"; done
for f in scripts/*.sh; do bash -n "$f"; done
python3 -m py_compile scripts/*.py scripts/orchlib/*.py

python3 - <<'PY'
import json, sys, tomllib
sys.path.insert(0, "scripts")
from orchlib import config
json.load(open('.orchestration/gsd-policy.overlay.json'))
config.load('.')
print('config syntax and registry: ok')
PY

! grep -R -nE 'danger-full-access|approval_policy *= *"?never|ask-for-approval +never|dangerously-skip-permissions|bypassPermissions' \
  .orchestration/agents.toml .orchestration/routing.toml .orchestration/gsd-policy.overlay.json >/dev/null \
  || fail "unsafe shared default found (put local relaxations into .orchestration/agents.local.toml)"

# v0.2 dispatch must not depend on the legacy Herdr TUI API.
! grep -R -nE 'herdr (agent|pane) ' scripts/orch.py scripts/orchlib >/dev/null || fail "legacy herdr API in orchestration scripts"

if (( ! TEMPLATE )); then
  echo 'self-check (project): PASS'
  exit 0
fi

for f in tests/*.sh; do bash -n "$f"; done
python3 -m py_compile tests/*.py
tomllib_ok=$(python3 -c "import tomllib; tomllib.load(open('.codex/config.toml','rb')); print(1)")
[[ $tomllib_ok == 1 ]] || fail ".codex/config.toml invalid"
grep -q 'GSD_VERSION=${GSD_VERSION:-1.19.0}' .orchestration/versions.env || fail "GSD pin drift"
grep -q 'HC_MIN_VERSION=${HC_MIN_VERSION:-0.1.16}' .orchestration/versions.env || fail "herdr-core baseline drift"
grep -q 'enabled = false' .codex/config.toml || fail "Codex worker fan-out guard missing"
grep -q 'max_concurrent_threads_per_session = 1' .codex/config.toml || fail "Codex worker concurrency guard missing"

! grep -nE 'danger-full-access|approval_policy *= *"?never' .codex/config.toml >/dev/null || fail "unsafe Codex config"

grep -q 'https://github.com/open-gsd/gsd-core' README.md || fail "GSD link missing"
grep -q 'https://github.com/herdrdev/herdr-core' README.md || fail "herdr-core link missing"
grep -q 'https://github.com/anthropics/claude-code' README.md || fail "Claude link missing"
grep -q 'https://github.com/openai/codex' README.md || fail "Codex link missing"
grep -q 'https://t.me/thoughts_and_bytes/27' README.md || fail "talk post link missing"

python3 - <<'PY'
from pathlib import Path
bad = ['aut'+'o-kalym', 'zv'+'enir', 'on1'+'kel']
for p in Path('.').rglob('*'):
    if p.is_file() and not {'.git', 'runtime', 'worktrees'} & set(p.parts):
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
