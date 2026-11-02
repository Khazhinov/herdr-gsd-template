#!/usr/bin/env bash
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/.orchestration/versions.env"

MR="$ROOT/.orchestration/merge-required"
if [[ -d "$MR" ]] && find "$MR" -type f -print -quit | grep -q .; then
  echo "unresolved orchestration overlay conflicts:" >&2
  find "$MR" -type f -print >&2
  echo "merge these files into the repository, remove merge-required copies, then rerun bootstrap" >&2
  exit 5
fi

need(){ command -v "$1" >/dev/null || { echo "missing dependency: $1" >&2; exit 2; }; }
for x in git node npm npx python3 claude hc; do need "$x"; done

./scripts/version-check.py ${BOOTSTRAP_STRICT:+--strict}

echo "Installing GSD Core $GSD_VERSION for Claude (project-local)..."
npx --yes "@opengsd/gsd-core@$GSD_VERSION" --claude --local

# Workers are not GSD owners, so GSD is installed only for the owner runtime.
# Promoting another runtime to owner includes installing GSD for it.
./scripts/reconcile-runtime-config.py

mkdir -p docs/orch .orchestration/runtime
./scripts/self-check.sh --offline

cat <<'TXT'
Bootstrap complete.

  1. Open the repository in Herdr App (or any terminal with herdr-core `hc`).
  2. Start the owner: claude
  3. First prompt:
       Initialize this repository according to .claude/CLAUDE.md: run doctor,
       start the orchestration hub, show quotas and routing, then wait for my GSD command.
  4. New project: /gsd-new-project      Existing code: /gsd-onboard
  5. Then: ./scripts/apply-gsd-policy.py

Mission Control in Herdr App: ./scripts/herdr-app-install.sh
TXT
