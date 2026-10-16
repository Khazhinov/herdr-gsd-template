#!/usr/bin/env bash
set -euo pipefail

CMD=${1:-}
ID=${2:-}
[[ -n "$CMD" && -n "$ID" ]] || {
  echo 'usage: peer-worktree.sh create|path|enter|merge|remove ID' >&2
  exit 2
}
[[ "$ID" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid worktree id: use only letters, digits, dot, underscore, hyphen" >&2
  exit 2
}

ROOT=$(git rev-parse --show-toplevel)
WT="$(dirname "$ROOT")/$(basename "$ROOT")-peer-$ID"
BRANCH="peer/$ID"

owner_clean() {
  git -C "$ROOT" diff --quiet && git -C "$ROOT" diff --cached --quiet
}

case "$CMD" in
  create)
    owner_clean || { echo 'owner tree must be clean' >&2; exit 3; }
    [[ ! -e "$WT" ]] || { echo "exists: $WT" >&2; exit 3; }

    # Keep stdout machine-readable: only the path is emitted there.
    if git -C "$ROOT" show-ref --verify --quiet "refs/heads/$BRANCH"; then
      git -C "$ROOT" worktree add "$WT" "$BRANCH" >&2
    else
      git -C "$ROOT" worktree add -b "$BRANCH" "$WT" >&2
    fi

    [[ -x "$ROOT/.orchestration/hooks/worktree-env" ]] &&
      "$ROOT/.orchestration/hooks/worktree-env" "$WT" "$ID"

    printf '%s\n' "$WT"
    ;;

  path)
    printf '%s\n' "$WT"
    ;;

  enter)
    [[ -d "$WT" ]] || { echo "missing $WT" >&2; exit 3; }
    "$ROOT/scripts/peer-restart-in.sh" peer-exec "$WT"
    ;;

  merge)
    [[ -d "$WT" ]] || { echo "missing $WT" >&2; exit 3; }
    git -C "$WT" diff --quiet && git -C "$WT" diff --cached --quiet ||
      { echo 'peer worktree dirty' >&2; exit 3; }
    owner_clean || { echo 'owner tree must be clean before merge' >&2; exit 3; }

    # Critical invariant: peer must leave the worktree before it can disappear.
    "$ROOT/scripts/peer-root.sh" peer-exec

    cd "$ROOT"
    git merge --no-ff "$BRANCH"
    git worktree remove "$WT"
    git worktree prune
    git branch -d "$BRANCH" >/dev/null

    # Start/confirm the peer from root again after merge/removal as a second guard.
    "$ROOT/scripts/peer-root.sh" peer-exec
    ;;

  remove)
    # Abandon worktree but preserve the branch for manual recovery.
    "$ROOT/scripts/peer-root.sh" peer-exec
    git -C "$ROOT" worktree remove "$WT"
    git -C "$ROOT" worktree prune
    ;;

  *)
    echo 'usage: peer-worktree.sh create|path|enter|merge|remove ID' >&2
    exit 2
    ;;
esac
