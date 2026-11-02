# Worker instructions (any coding agent)

The orchestration owner is `owner` in `.orchestration/routing.toml`.
Do not infer ownership from `.planning/config.json`.

When you were started by `scripts/orch.py dispatch`, you are a **worker**:
1. Your instructions are the task contract file named in your first message, including its appended protocol.
2. Do not modify canonical `.planning/` and do not run GSD orchestration commands.
3. Work only in your working directory and the allowed scope of the contract.
4. In a worktree, do not commit: leave changes in the tree; the owner commits after reading your report.
5. Write the report to the path in the contract; its last line is exactly one sentinel
   (`Result: complete`, `Result: incomplete`, `Major issue: yes`, `Major issue: no`).
6. Do not start other agents. Never approve permission dialogs on your own.
7. If a missing decision blocks you, stop with `Result: incomplete` and say what is missing.
8. Apply `.agents/skills/gsd-context-discipline/SKILL.md`: targeted reads, no rereads, diff-only rereview, batched checks.

If you are the owner (routing.toml says so), follow `.claude/CLAUDE.md` with your runtime in place of Claude
and `.agents/skills/orch-workers/SKILL.md`.
