---
name: herdr-peer
description: Herdr protocol for a Claude GSD owner and independent Codex peer review/code/execution workers.
---

# Herdr peer protocol

## Topology

The human starts Herdr in the repository root and launches Claude in the first/root pane.
The owner runs `./scripts/herdr-ensure-peers.sh`, which creates named Codex agents:
`peer-review`, `peer-code`, `peer-exec`.

Use logical agent names, not predicted pane IDs.
GSD subagents do not call Herdr; external routing belongs to the top-level owner.

## Current Herdr primitives

Prefer `herdr agent start/get/read/prompt/wait/send-keys`.
Use raw pane input only for ordinary terminals or explicit low-level recovery.

`agent prompt --wait` observes agent lifecycle, not a unique logical work item.
A timeout or `agent_prompt_stalled` does not prove that input was not delivered.
Never blindly resend: inspect the agent/report first.

## Fresh context

Before each independent peer task, `peer-dispatch.sh` calls `peer-reset.sh`.
The reset submits Codex `/clear`, which starts a fresh chat while preserving the current process/cwd.

Changing cwd is a different operation:
`peer-restart-in.sh` exits the managed Codex process and starts a new one in an explicit directory.
Do not conflate context reset with worktree relocation.

## Completion

Use `peer-watch.sh`.

Success requires a durable report with the requested sentinel.
For execution, owner also verifies commits, write scope and required checks.

Herdr lifecycle states are scheduler/process signals only:
- `working`: activity observed;
- `blocked`: approval/question requires deliberate intervention;
- `idle` / `done`: ready for input;
- `unknown`: lifecycle cannot be classified confidently.

None of them is project-task success.

## GSD gates

Default policy:
- discuss/context -> `peer-review`;
- plan -> `peer-review`;
- approved bounded execution -> `peer-exec` when quota permits;
- post-implementation diff -> `peer-code`;
- difficult debug/research -> bounded review peer.

The GSD policy reassigns built-in plan/code review responsibilities to external peers while keeping GSD verifier enabled.

## Worktrees

Create:
`peer-worktree.sh create <plan-id>`

Move execution peer:
`peer-worktree.sh enter <plan-id>`

After execution:
`peer-worktree.sh merge <plan-id>`

Both merge/remove return `peer-exec` to repository root **before** deleting a worktree.

## Monitoring

Default lifecycle/report polling: 15 seconds.
Quota estimate refresh: 10 minutes.
Crossing the quota threshold never kills a running task; it only prevents new heavy dispatches.
