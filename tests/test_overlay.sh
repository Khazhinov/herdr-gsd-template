#!/usr/bin/env bash
set -euo pipefail
SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

target="$TMP/existing"
mkdir -p "$target"
git -C "$target" init -q
git -C "$target" config user.email test@example.invalid
git -C "$target" config user.name "Template Test"

mkdir -p "$target/.claude" "$target/.codex" "$target/.agents/skills/gsd-context-discipline" "$target/scripts"
printf 'existing agents\n' >"$target/AGENTS.md"
printf 'existing claude\n' >"$target/.claude/CLAUDE.md"
printf 'existing codex\n' >"$target/.codex/config.toml"
printf 'existing skill\n' >"$target/.agents/skills/gsd-context-discipline/SKILL.md"
printf '#!/bin/sh\necho existing\n' >"$target/scripts/bootstrap.sh"
chmod +x "$target/scripts/bootstrap.sh"

"$SOURCE/scripts/install-into-repo.sh" "$target" >/dev/null

grep -qx 'existing agents' "$target/AGENTS.md"
grep -qx 'existing claude' "$target/.claude/CLAUDE.md"
grep -qx 'existing codex' "$target/.codex/config.toml"
grep -qx 'existing skill' "$target/.agents/skills/gsd-context-discipline/SKILL.md"
grep -q 'echo existing' "$target/scripts/bootstrap.sh"

test -f "$target/.orchestration/versions.env"
test -f "$target/.orchestration/owner.env"
test -f "$target/.orchestration/merge-required/AGENTS.md"
test -f "$target/.orchestration/merge-required/.claude/CLAUDE.md"
test -f "$target/.orchestration/merge-required/.codex/config.toml"
test -f "$target/.orchestration/merge-required/.agents/skills/gsd-context-discipline/SKILL.md"
test -f "$target/.orchestration/merge-required/scripts/bootstrap.sh"

# bootstrap must fail closed while conflicts remain (before reaching runtime tools).
set +e
( cd "$target" && ./.orchestration/merge-required/scripts/bootstrap.sh >/dev/null 2>"$TMP/bootstrap.err" )
rc=$?
set -e
[[ $rc -eq 5 ]]
grep -q 'unresolved orchestration overlay conflicts' "$TMP/bootstrap.err"

echo "overlay test: PASS"
