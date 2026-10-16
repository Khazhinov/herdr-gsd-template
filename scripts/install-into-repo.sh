#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: install-into-repo.sh /path/to/repo}
SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TARGET=$(cd "$TARGET" && pwd)

[[ -d "$TARGET/.git" ]] || { echo "target is not a git repo" >&2; exit 2; }

MR="$TARGET/.orchestration/merge-required"
mkdir -p "$MR"

copy_one() {
  local src=$1
  local rel=$2
  local dst="$TARGET/$rel"
  if [[ -e "$dst" ]]; then
    if cmp -s "$src" "$dst"; then
      return
    fi
    mkdir -p "$MR/$(dirname "$rel")"
    cp -p "$src" "$MR/$rel"
    echo "kept existing $rel; merge-required copy created"
  else
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  fi
}

copy_tree_conflict_safe() {
  local rel=$1
  local srcroot="$SOURCE/$rel"
  [[ -d "$srcroot" ]] || return
  while IFS= read -r -d '' src; do
    sub=${src#"$srcroot/"}
    [[ "$sub" == merge-required/* ]] && continue
    copy_one "$src" "$rel/$sub"
  done < <(find "$srcroot" -type f -print0)
}

copy_tree_conflict_safe .agents
copy_tree_conflict_safe .orchestration
copy_tree_conflict_safe scripts

copy_one "$SOURCE/.mcp.example.json" .mcp.example.json
copy_one "$SOURCE/AGENTS.md" AGENTS.md
copy_one "$SOURCE/.claude/CLAUDE.md" .claude/CLAUDE.md
copy_one "$SOURCE/.codex/config.toml" .codex/config.toml

mkdir -p "$TARGET/docs/peer"
chmod +x "$TARGET"/scripts/*.sh "$TARGET"/scripts/*.py 2>/dev/null || true

echo "installed orchestration overlay into $TARGET"
if find "$MR" -type f -print -quit | grep -q .; then
  echo
  echo "ACTION REQUIRED: merge conflicts before bootstrap:"
  find "$MR" -type f -print
  echo "After merging, delete the corresponding files under $MR (or the directory when empty)."
else
  rmdir "$MR" 2>/dev/null || true
  echo "no overlay conflicts"
fi
echo "next: cd '$TARGET' && ./scripts/bootstrap.sh"
