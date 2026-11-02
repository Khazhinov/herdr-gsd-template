---
name: gsd-context-discipline
description: Context, ownership, concurrency, resource routing and verification rules for GSD + herdr-core with any set of coding agents.
---

# GSD context discipline

## Retrieval / token optimization stack

1. Search before reading broadly: repository graph/semantic MCP if connected; otherwise `rg`, `git grep`, symbols and Git history.
2. Pass paths, headings, requirement IDs and commit ranges instead of copying whole documents.
3. Read targeted ranges only after discovery; avoid unjustified full-tree scans.
4. Do not reread unchanged files in the same task.
5. For rereview, load prior findings + correction diff, not the entire original context.
6. Batch deterministic checks into one shell chain where possible; quiet happy path, targeted failure tail.
7. If an exit code or deterministic parser can decide it, do not spend reasoning tokens on the decision.
8. If the task prompt already contains the complete executable contract, do not reread generic methodology/TDD/execute docs unless blocked.
9. Keep large generated logs, test output and search results out of persistent conversational context; save artifacts and pass paths.
10. Prefer a fresh bounded worker (one task, one process) over accumulating unrelated tasks in one session.

## State ownership

1. Exactly one top-level runtime owns canonical `.planning/`.
2. Ownership is declared by `owner` in `.orchestration/routing.toml`, not inferred from GSD model/runtime configuration.
3. Only owner runs GSD orchestrators and mutates canonical planning state.
4. Workers write reports under `docs/orch/` and code only in their assigned worktree.
5. Owner accepts/rejects worker findings and performs state transitions.
6. Ownership transfer requires a committed safe boundary and explicit marker change; never reconstruct from chat history.

## Parallelism

1. External concurrency is bounded per agent by `max_parallel` in `.orchestration/agents.toml`.
2. Add a second concurrent writer only with explicit non-overlapping contracts.
3. Same-wave write scopes must not overlap.
4. Shared migrations/schema/manifests/global generated files are serialized unless explicitly partitioned.
5. One plan per worktree/branch (`orch/<id>`).
6. Worktree does not isolate DB/ports/cache/queues/external APIs; use the project-specific worktree hook.
7. If independence is uncertain, execute sequentially.
8. A worker must not spawn other agents.

## Model/resource routing

1. Strong reasoning tier for architecture/planning/difficult independent review.
2. Workhorse tier for bounded execution/verification.
3. `scripts/orch.py route` / `dispatch` apply live quotas and reserves; do not hand-pick agents against them.
4. At or below a reserve an agent gets only light work; heavy work goes down the chain.
5. Unknown or stale quota means no automatic heavy routing (fail closed).
6. Quota readings are provider telemetry, not a billing API; the decision record says which source was used.
7. Switch workers only between durable tasks, never half-turn.

## Verification

1. Required tests/lint/typecheck/acceptance stay mandatory.
2. One independent review, one owner correction; rereview only major changed areas.
3. Repair loops are bounded.
4. Code review != GSD verifier: diff/code quality vs goal/requirements evidence.
5. Worker status (`working/blocked/done/idle`) != project task success.
6. Task completion = report sentinel + expected Git/check evidence (`orch.py collect`).

## Session boundaries

Reset only after durable commit + recorded review decision + consistent state.
Recover from files and Git, not transcript.
