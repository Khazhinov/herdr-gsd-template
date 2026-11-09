#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
QUIET=0
[[ ${1:-} == --quiet ]] && QUIET=1

# Exit codes: 4 Codex sandbox, 5 herdr-core access, 6 Codex daemon,
# 7 orchestration cache, other: failed static checks or orch.py error.
echo "== agent environment =="
python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
from orchlib import hc
if hc.codex_daemon():
    print(f"Codex daemon: FAIL: {hc.DAEMON_HINT}", file=sys.stderr)
    sys.exit(6)
print("Codex daemon: not used")
PY
CACHE=${ORCH_CACHE_DIR:-$HOME/.cache/herdr-orch}
mkdir -p "$CACHE" 2>/dev/null || true
if touch "$CACHE/.doctor" 2>/dev/null && rm -f "$CACHE/.doctor"; then
  echo "orchestration cache: writable"
else
  echo "orchestration cache: FAIL: $CACHE is not writable from this command tool (OPERATIONS 3.3)" >&2
  exit 7
fi

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
  echo "Run hc get from inside the new owner agent command tool; check sandbox socket access (OPERATIONS 3.3)." >&2
  exit 5
fi

# Codex runs shell commands through its own binary inside bwrap; a permission
# profile that hides that binary breaks every command (OPERATIONS, section 3.1).
# Inside a Codex session the checks above already ran in its sandbox, and a
# nested `codex sandbox` always fails.
if [[ -n ${CODEX_THREAD_ID:-} ]]; then
  echo "== codex sandbox =="
  echo "codex sandbox: checked from inside the Codex session"
elif command -v codex >/dev/null && grep -q '^quota = "codex"' .orchestration/agents.toml; then
  echo "== codex sandbox =="
  if err=$(codex sandbox -- /bin/true 2>&1); then
    echo "codex sandbox: OK"
    if hc_err=$(codex sandbox -- hc ls --json 2>&1 >/dev/null); then
      echo "codex sandbox -> herdr-core: OK"
    else
      echo "codex sandbox -> herdr-core: FAIL: ${hc_err##*$'\n'}" >&2
      echo "Codex commands cannot reach the core socket: turn the network on in its permission profile (OPERATIONS 3.3)" >&2
      exit 5
    fi
    if cache_err=$(codex sandbox -- sh -c 'touch "$1/.doctor" && rm -f "$1/.doctor"' _ "$CACHE" 2>&1); then
      echo "codex sandbox -> orchestration cache: OK"
    else
      echo "codex sandbox -> orchestration cache: FAIL: ${cache_err##*$'\n'}" >&2
      echo "allow writes to $CACHE in the Codex permission profile (OPERATIONS 3.3)" >&2
      exit 7
    fi
  else
    echo "codex sandbox: FAIL: ${err##*$'\n'}" >&2
    echo "see .orchestration/docs/OPERATIONS.md, section 3.1" >&2
    exit 4
  fi
fi

echo "== quotas and routing =="
python3 scripts/orch.py quota
rc=0
route=$(python3 scripts/orch.py route execute) || rc=$?
echo "${route##*$'\n'}"
# Exit 4 of `route`: no agent admitted by quota reserves now; not an environment fault.
if ((rc == 4)); then
  echo "route execute: no agent admitted now (quota reserves); environment OK"
elif ((rc)); then
  exit "$rc"
fi
echo "doctor: PASS"
