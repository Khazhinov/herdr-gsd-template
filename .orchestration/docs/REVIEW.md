# Publication review — 2026-10-16

This file records the third large review cycle before publishing the template.

## Pass 1 — current upstream contracts

Status: PASS after changes.

Verified against current upstream release/docs:
- GSD Core updated to 1.17.0.
- GSD 1.17.0 runtime requirement updated to Node.js >=24 / npm >=10.
- Herdr baseline updated to 0.9.3.
- Claude Code baseline updated to 2.1.301.
- Codex baseline updated to 0.163.0.
- Herdr automation uses agent-aware APIs, not raw pane text for normal tasks.
- Herdr lifecycle is not used as work-item completion.
- Codex current concurrency naming is used; V2 semantics are handled explicitly.
- per-start `-c model_reasoning_effort=...` overrides removed from Herdr-managed Codex startup.
- orchestration ownership moved to `.orchestration/owner.env`.
- GSD runtime remains only GSD runtime/model-resolution configuration.
- GSD plan/code review responsibilities remain reassigned to external Codex peers while verifier stays enabled.
- public template has no permissive sandbox/approval defaults.
- README links all upstream projects and the originating talk/channel.

## Pass 2 — protocol and failure-mode review

Status: PASS after fixes.

Verified:
- one canonical `.planning/` writer;
- peer cannot recursively create its own swarm under project config/instructions;
- task contract is explicit;
- fresh peer chat via `/clear`;
- cwd relocation uses process restart, not `/clear`;
- dispatch submits exactly once and never blind-retries;
- task completion requires durable report + sentinel + Git/check evidence;
- blocked states require deliberate intervention;
- quota telemetry fails closed for automatic heavy execution when unavailable;
- both visible primary and secondary rate-limit windows constrain scheduling;
- running tasks are never migrated half-turn;
- worktree removal returns peer to repo root first;
- worktree does not pretend to isolate external resources;
- overlay install remains conflict-safe;
- GSD installer reconciliation is idempotent;
- optimization/context discipline is mandatory in both owner and peer instructions.

## Pass 3 — operational/static simulation

Status: PASS in the generated artifact.

Executed:
- shell syntax validation;
- Python compile/tests;
- JSON/TOML parse;
- version/pin consistency checks;
- legacy-version and unsafe-setting grep;
- privacy/domain leakage scan;
- overlay simulation into a Git repository with existing instructions;
- reconcile idempotence;
- mocked Herdr worktree lifecycle: create → peer relocation → commit → root restart → merge → remove/prune.

## Environment-dependent smoke tests

Still require the user's authenticated machine:
1. Herdr 0.9.3+ recognizes installed Claude/Codex and lifecycle states.
2. Codex 0.163.0 accepts `/clear` through `herdr agent prompt`.
3. Local rollout telemetry still contains usable rate-limit windows.
4. Project-specific worktree resource hook correctly isolates DB/ports/cache/etc.
5. Any optional role-specific model names exist on the user's plan.
6. GSD installer output on the user's platform remains compatible with the reconciliation block.

These are deliberately not claimed as locally authenticated in this artifact.
