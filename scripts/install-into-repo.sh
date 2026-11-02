#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: install-into-repo.sh /path/to/repo}
SOURCE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
TARGET=$(cd "$TARGET" && pwd)

git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || { echo "target is not a git repo" >&2; exit 2; }

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
    case "$sub" in merge-required/*|runtime/*|worktrees/*|template-repo|*.local.toml|*__pycache__*|*.pyc|test-template.sh|install-into-repo.sh) continue;; esac
    copy_one "$src" "$rel/$sub"
  done < <(find "$srcroot" -type f -print0)
}

copy_tree_conflict_safe .agents
copy_tree_conflict_safe .orchestration
copy_tree_conflict_safe scripts
copy_tree_conflict_safe herdr-app

copy_one "$SOURCE/.mcp.example.json" .mcp.example.json
copy_one "$SOURCE/AGENTS.md" AGENTS.md
copy_one "$SOURCE/.claude/CLAUDE.md" .claude/CLAUDE.md
copy_one "$SOURCE/.codex/config.toml" .codex/config.toml

mkdir -p "$TARGET/docs/orch"
chmod +x "$TARGET"/scripts/*.sh "$TARGET"/scripts/*.py 2>/dev/null || true

# Runtime state and worker worktrees never belong in git.
touch "$TARGET/.gitignore"
for line in .orchestration/runtime/ .orchestration/merge-required/ .orchestration/worktrees/ \
            .orchestration/agents.local.toml .orchestration/routing.local.toml; do
  grep -qxF "$line" "$TARGET/.gitignore" || echo "$line" >> "$TARGET/.gitignore"
done

# v0.1 leftovers: legacy Herdr TUI peers. Listed, never deleted automatically.
legacy=()
for f in scripts/peer-dispatch.sh scripts/peer-watch.sh scripts/peer-worktree.sh scripts/peer-reset.sh \
         scripts/peer-restart-in.sh scripts/peer-root.sh scripts/peer-status.sh scripts/herdr-ensure-peers.sh \
         scripts/codex-limits.py .orchestration/owner.env .orchestration/config.env .agents/skills/herdr-peer; do
  [[ -e "$TARGET/$f" ]] && legacy+=("$f")
done
if ((${#legacy[@]})); then
  echo "v0.1 files found (see .orchestration/docs/MIGRATION.md before removing):"
  printf '  %s\n' "${legacy[@]}"
fi

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
