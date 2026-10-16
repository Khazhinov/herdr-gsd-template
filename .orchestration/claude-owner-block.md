<!-- GSD-HERDR-STARTER:BEGIN -->
## GSD + Herdr owner protocol

Default ownership is declared in `.orchestration/owner.env`; do not infer it from GSD runtime/model configuration.
Before GSD work read `.agents/skills/gsd-context-discipline/SKILL.md` and `.agents/skills/herdr-peer/SKILL.md`.
If inside Herdr (`HERDR_ENV=1`), run `./scripts/herdr-ensure-peers.sh` at session start.
Only the declared owner writes canonical `.planning/`; external Codex peers return `docs/peer/` artifacts.
Use peer gates after discuss, plan and implementation; GSD subagents never call Herdr.
Before heavy Codex execution check `./scripts/codex-limits.py --json`.
Before deleting a peer worktree return `peer-exec` to repository root (`peer-worktree.sh merge/remove` enforce this).
Recover new sessions from `.planning/`, peer reports and Git, not chat history.
Apply the optimization stack from `gsd-context-discipline`.
<!-- GSD-HERDR-STARTER:END -->
