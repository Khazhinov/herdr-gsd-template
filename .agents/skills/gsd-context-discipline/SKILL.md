---
name: gsd-context-discipline
description: Context, ownership, concurrency, resource routing and verification rules for GSD + Herdr + Claude/Codex.
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
10. Prefer fresh bounded peer context over accumulating unrelated tasks in one session.

## State ownership

1. Exactly one top-level runtime owns canonical `.planning/`.
2. Ownership is declared in `.orchestration/owner.env`, not inferred from GSD model/runtime configuration.
3. Only owner runs GSD orchestrators and mutates canonical planning state.
4. Peer writes `docs/peer/` evidence and code only in assigned worktree.
5. Owner accepts/rejects peer findings and performs state transitions.
6. Ownership transfer requires a committed safe boundary and explicit marker change; never reconstruct from chat history.

## Parallelism

1. External coding concurrency is bounded by `.orchestration/owner.env`.
2. Default topology permits only one `peer-exec`; add a second writer only with explicit non-overlapping contracts.
3. Same-wave write scopes must not overlap.
4. Shared migrations/schema/manifests/global generated files are serialized unless explicitly partitioned.
5. One peer plan per worktree/branch.
6. Worktree does not isolate DB/ports/cache/queues/external APIs; use the project-specific worktree hook.
7. If independence is uncertain, execute sequentially.
8. Peer must not spawn another swarm.

## Model/resource routing

1. Strong reasoning tier for architecture/planning/difficult independent review.
2. Workhorse tier for bounded execution/verification.
3. Check `scripts/codex-limits.py` before heavy execution and periodically while running.
4. At/below threshold: only short peer work; heavy execution falls back.
5. Missing telemetry means no automatic heavy routing.
6. Quota telemetry is advisory/best-effort, not a billing API.
7. Switch workers only between durable tasks, never half-turn.

## Verification

1. Required tests/lint/typecheck/acceptance stay mandatory.
2. One independent review, one owner correction; rereview only major changed areas.
3. Repair loops are bounded.
4. Code review != GSD verifier: diff/code quality vs goal/requirements evidence.
5. Herdr lifecycle != project task success.
6. Task completion = report/sentinel + expected Git/check evidence.

## Session boundaries

Reset only after durable commit + recorded review decision + consistent state.
Recover from files and Git, not transcript.
