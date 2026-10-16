# Codex peer instructions

This repository's default orchestration owner is declared in `.orchestration/owner.env`.
Do **not** infer ownership from `.planning/config.json`.

Read first:
- `.agents/skills/gsd-context-discipline/SKILL.md`
- `.agents/skills/herdr-peer/SKILL.md`

Unless `.orchestration/owner.env` explicitly assigns `ORCHESTRATION_OWNER=codex`,
Codex is a **peer**, not the GSD owner.

As peer:
1. Do not modify canonical `.planning/`.
2. Do not run GSD orchestration commands.
3. Work only from an explicit task contract.
4. Execution happens only in the supplied worktree and allowed scope.
5. Write the requested durable report and exact final sentinel.
6. Do not spawn child agents; top-level owner controls fan-out.
7. Do not broaden scope. If a missing decision blocks work, stop with `Result: incomplete`.
8. Apply the optimization stack: targeted reads, no unnecessary rereads, diff-only rereview, batched deterministic checks.
9. Treat Herdr `idle/done/blocked/working` only as process lifecycle. Logical completion requires report + sentinel + expected Git/check evidence.
10. Never approve security/permission dialogs automatically. Surface `blocked` to owner/human.

The project-local `.codex/config.toml` disables Codex-native subagent fan-out for the peer role.
If you intentionally promote Codex to orchestration owner, review that file as part of the handoff.
