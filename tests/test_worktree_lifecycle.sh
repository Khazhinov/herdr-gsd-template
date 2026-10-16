#!/usr/bin/env bash
set -euo pipefail
SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

repo="$TMP/repo"
cp -a "$SOURCE" "$repo"
chown -R "$(id -u):$(id -g)" "$repo" 2>/dev/null || true
rm -rf "$repo/.git"
git -C "$repo" init -q
git -C "$repo" config user.email test@example.invalid
git -C "$repo" config user.name "Template Test"
git -C "$repo" add .
git -C "$repo" commit -qm init

mkdir -p "$TMP/bin" "$TMP/herdr-state/agents" "$TMP/herdr-state/panes"
ln -s "$repo/tests/fake-herdr.sh" "$TMP/bin/herdr"
export PATH="$TMP/bin:$PATH"
export MOCK_HERDR_STATE="$TMP/herdr-state"
export HERDR_ENV=1

pane="mock-root"
printf '%s\n' "$repo" >"$MOCK_HERDR_STATE/panes/$pane.cwd"
printf 'status=idle\npane=%q\ncwd=%q\n' "$pane" "$repo" >"$MOCK_HERDR_STATE/agents/peer-exec"

cd "$repo"
wt=$(./scripts/peer-worktree.sh create smoke 2>/dev/null)
test -d "$wt"

./scripts/peer-worktree.sh enter smoke >/dev/null
# shellcheck disable=SC1090
source "$MOCK_HERDR_STATE/agents/peer-exec"
[[ "$cwd" == "$wt" ]] || { echo "peer did not enter worktree" >&2; exit 1; }

printf 'peer result\n' >"$wt/peer-result.txt"
git -C "$wt" add peer-result.txt
git -C "$wt" commit -qm "test: peer change"

./scripts/peer-worktree.sh merge smoke >/dev/null

test -f "$repo/peer-result.txt"
test ! -d "$wt"
source "$MOCK_HERDR_STATE/agents/peer-exec"
[[ "$cwd" == "$repo" ]] || { echo "peer not returned to root" >&2; exit 1; }
! git -C "$repo" worktree list --porcelain | grep -Fq "$wt"
! git -C "$repo" show-ref --verify --quiet refs/heads/peer/smoke

echo "worktree lifecycle test: PASS"
