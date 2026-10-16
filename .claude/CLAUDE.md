# Claude owner bootstrap

Default orchestration ownership is declared in `.orchestration/owner.env`.

At the start of every owner session:
1. Read `.orchestration/owner.env`.
2. If `ORCHESTRATION_OWNER` is not `claude`, stop orchestration and follow the explicit handoff procedure.
3. Read `.agents/skills/gsd-context-discipline/SKILL.md`.
4. Read `.agents/skills/herdr-peer/SKILL.md`.
5. Run `./scripts/doctor.sh --quiet` once per machine/session boundary when practical.
6. If `HERDR_ENV=1`, run `./scripts/herdr-ensure-peers.sh`.
7. If `.planning/STATE.md` exists, read it and only the current phase/plan plus relevant peer reports.
8. Before heavy Codex execution run `./scripts/codex-limits.py --json`.

Owner invariant: only the runtime named by `.orchestration/owner.env` changes canonical `.planning/`.

Mandatory external peer gates in the default policy:
- post-discuss/context -> `peer-review`;
- post-plan -> `peer-review`;
- bounded execution -> prefer `peer-exec` while quota policy permits;
- post-implementation -> `peer-code`;
- then GSD verifier / human acceptance as appropriate.

GSD subagents do not call Herdr. Only this top-level owner routes external peer work.

Before removing/merging a peer worktree, ensure `peer-exec` is restarted from repository root.
`peer-worktree.sh merge` and `remove` enforce this.

Reset/new owner session only on a durable safe boundary:
atomic operation complete, commit exists, review decision recorded, state consistent.
Recover from `.planning/`, `docs/peer/` and Git, not chat transcript.

Always apply the optimization stack from the context-discipline skill.
