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
for x in git node npm npx python3 jq claude codex herdr; do need "$x"; done

./scripts/version-check.py --strict

echo "Installing GSD Core $GSD_VERSION for Claude (project-local)..."
npx --yes "@opengsd/gsd-core@$GSD_VERSION" --claude --local

# Codex is intentionally a peer in this template, so GSD is not installed into
# Codex by bootstrap. If you promote Codex to owner later, install GSD for Codex
# with the official runtime installer as part of that explicit handoff.
./scripts/reconcile-runtime-config.py

mkdir -p docs/peer .orchestration/runtime
./scripts/self-check.sh --offline

cat <<'TXT'
Bootstrap complete.

New project:
  1. herdr
  2. in the first/root pane: claude
  3. ask Claude to initialize orchestration
  4. /gsd-new-project
  5. ./scripts/apply-gsd-policy.py

Existing project:
  same flow, but use /gsd-onboard before apply-gsd-policy.py

Recommended first prompt:
  Initialize this repository according to .claude/CLAUDE.md.
  Verify versions, ensure Codex peer-review/peer-code/peer-exec exist,
  show peer states and Codex quota estimate, then stop and wait for my GSD command.
TXT
