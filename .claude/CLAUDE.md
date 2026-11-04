# Claude owner bootstrap

The orchestration owner is declared by `owner` in `.orchestration/routing.toml`.

Follow "Publication safety" in `AGENTS.md` for every change.

At the start of every owner session:
1. Read `owner` in `.orchestration/routing.toml`. If it is not `claude`, stop orchestration and follow "Owner handoff" in `.orchestration/docs/OPERATIONS.md`.
2. Read `.agents/skills/gsd-context-discipline/SKILL.md` and `.agents/skills/orch-workers/SKILL.md`.
3. Run `./scripts/doctor.sh --quiet` once per machine/session boundary when practical.
4. If `$HC_TERMINAL_ID` is set (running under herdr-core), make sure the hub runs: `python3 scripts/orch.py hub start`.
5. `python3 scripts/orch.py status --no-planning` shows quotas, routing and unfinished tasks; collect or resume them before new work.
6. If `.planning/STATE.md` exists, read it and only the current phase/plan plus relevant reports.

Owner invariant: only the owner changes canonical `.planning/`.
Reset the owner session only at a durable boundary: commit exists, review decision recorded, state consistent.
Always apply the optimization stack from the context-discipline skill.
