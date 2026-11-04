# Worker instructions (any coding agent)

## Publication safety (mandatory, read first)

This template is public, and a project made from it may be public too. Every agent working here, including one that only installs or configures something, keeps
the machine out of git:

1. Machine-specific data stays in git-ignored places (`.orchestration/*.local.toml`, `.orchestration/runtime/`, `.mcp.json`). Never copy it into tracked files,
   commit messages, tags, release notes, pull requests or issues.
2. Tracked files never contain absolute home or mount paths, user, host, company or project names,
   private service addresses, tokens, keys, `.env` values, filled MCP configs or session logs. Use
   placeholders (`<home>`, `/absolute/path/to/...`, `example.com`).
3. A new tool, installer or config may write files into the working tree. Before the first commit
   add such paths to `.gitignore` and check `git status --short --ignored`.
4. Before a commit read `git diff --cached` and run `./scripts/self-check.sh` (template) or the project's own checks. Commit only with the author identity
   the person set for this repository. Push and publish only when the person asks.
5. In doubt whether something is private, do not commit it: ask the person.

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
