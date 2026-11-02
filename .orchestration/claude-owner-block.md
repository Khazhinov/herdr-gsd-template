<!-- GSD-HERDR-STARTER:BEGIN -->
## GSD + herdr-core owner protocol

The orchestration owner is `owner` in `.orchestration/routing.toml`; never infer it from GSD runtime/model settings.
Before GSD work read `.agents/skills/gsd-context-discipline/SKILL.md` and `.agents/skills/orch-workers/SKILL.md`.
Only the owner writes canonical `.planning/`; workers return reports under `docs/orch/` and code in their worktree.
Route external work only through `python3 scripts/orch.py` (route, dispatch, wait, collect); it applies quota, reserves, independence and records the reason.
Gates: post-discuss and post-plan review, bounded execution, post-implementation code review (skill, section "GSD gates").
GSD subagents never start workers; only this top-level owner does.
Worker status is not task success: `orch.py collect` judges the report sentinel and Git evidence.
Recover new sessions from `.planning/`, `docs/orch/`, `.orchestration/runtime/tasks/` and Git, not chat history.
<!-- GSD-HERDR-STARTER:END -->
