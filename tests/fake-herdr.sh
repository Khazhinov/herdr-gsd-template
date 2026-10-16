#!/usr/bin/env bash
set -euo pipefail
STATE=${MOCK_HERDR_STATE:?}
mkdir -p "$STATE/agents" "$STATE/panes"

agent_json() {
  local name=$1
  local file="$STATE/agents/$name"
  [[ -f "$file" ]] || exit 1
  # shellcheck disable=SC1090
  source "$file"
  printf '{"result":{"agent":{"name":"%s","status":"%s","pane_id":"%s"}}}\n' "$name" "$status" "$pane"
}

[[ $# -ge 1 ]] || exit 2
case "$1" in
  --version)
    echo "herdr 0.9.3";;
  agent)
    sub=${2:?}; shift 2
    case "$sub" in
      get)
        agent_json "${1:?}";;
      prompt)
        name=${1:?}; prompt=${2:-}
        agent_json "$name" >/dev/null
        if [[ "$prompt" == "/exit" ]]; then
          rm -f "$STATE/agents/$name"
        fi
        agent_json "$name" 2>/dev/null || printf '{"result":{"ok":true}}\n'
        ;;
      start)
        name=${1:?}; shift
        pane=""
        while (($#)); do
          case "$1" in
            --pane) pane=${2:?}; shift 2;;
            --) break;;
            *) shift;;
          esac
        done
        [[ -n "$pane" ]] || exit 2
        cwd=$(cat "$STATE/panes/$pane.cwd" 2>/dev/null || pwd)
        printf 'status=idle\npane=%q\ncwd=%q\n' "$pane" "$cwd" >"$STATE/agents/$name"
        agent_json "$name"
        ;;
      wait)
        agent_json "${1:?}";;
      read)
        echo "mock agent output";;
      *)
        echo "unsupported fake herdr agent subcommand: $sub" >&2; exit 2;;
    esac
    ;;
  pane)
    sub=${2:?}; shift 2
    case "$sub" in
      run)
        pane=${1:?}; cmd=${2:?}
        if [[ "$cmd" == cd\ * ]]; then
          raw=${cmd#cd }
          # The production helper uses printf %q, so eval reconstructs one shell word.
          eval "set -- $raw"
          printf '%s\n' "$1" >"$STATE/panes/$pane.cwd"
        fi
        printf '{"result":{"pane_id":"%s"}}\n' "$pane"
        ;;
      split)
        pane="mock-pane-$RANDOM"
        cwd=$(pwd)
        while (($#)); do
          case "$1" in
            --cwd) cwd=${2:?}; shift 2;;
            *) shift;;
          esac
        done
        printf '%s\n' "$cwd" >"$STATE/panes/$pane.cwd"
        printf '{"result":{"pane":{"pane_id":"%s"}}}\n' "$pane"
        ;;
      *)
        echo "unsupported fake herdr pane subcommand: $sub" >&2; exit 2;;
    esac
    ;;
  *)
    echo "unsupported fake herdr command: $*" >&2; exit 2;;
esac
