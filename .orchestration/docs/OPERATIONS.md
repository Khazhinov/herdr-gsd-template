# Operations

## Start

```bash
cd <repo>
./scripts/doctor.sh
herdr
```

In the first/root pane:

```bash
claude
```

Recommended first prompt:

```text
Initialize this repository according to .claude/CLAUDE.md.
Verify versions, ensure Codex peer-review/peer-code/peer-exec exist,
show peer states and Codex quota estimate, then stop and wait for my GSD command.
```

## Ensure peers

```bash
./scripts/herdr-ensure-peers.sh
./scripts/peer-status.sh
```

## Dispatch

```bash
cp .orchestration/templates/peer-task.md /tmp/task.md
# edit task contract
./scripts/peer-dispatch.sh peer-review /tmp/task.md
./scripts/peer-watch.sh peer-review docs/peer/review.md
```

Do not blindly resend after a timeout/stalled lifecycle signal.
Inspect:

```bash
herdr agent get peer-review
herdr agent read peer-review --source recent-unwrapped --lines 120
```

## Heavy execution eligibility

```bash
./scripts/codex-limits.py --threshold "${CODEX_HEAVY_THRESHOLD:-30}"
```

Exit:
- `0`: heavy scheduling allowed;
- `1`: short work only;
- `2`: telemetry unavailable; automatic heavy routing disabled.

## Worktree

```bash
wt=$(./scripts/peer-worktree.sh create 01-02)
./scripts/peer-worktree.sh enter 01-02
# dispatch execution contract with $wt
./scripts/peer-worktree.sh merge 01-02
```

`merge/remove` return `peer-exec` to root before worktree deletion.

## Blocked peer

```bash
herdr agent get peer-exec
herdr agent read peer-exec --source recent-unwrapped --lines 120
```

Never auto-answer approval/security dialogs.

## GSD upgrade

```bash
# edit .orchestration/versions.env first
./scripts/bootstrap.sh
./scripts/self-check.sh --offline
./scripts/doctor.sh
```

Then run a real Herdr peer smoke test and worktree lifecycle before publishing the bump.
