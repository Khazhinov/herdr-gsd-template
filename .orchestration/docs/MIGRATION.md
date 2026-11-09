# Moving from v0.1 to v0.2

English | [Русский](MIGRATION.ru.md)

## 1. What changes

| v0.1 | v0.2 |
|---|---|
| Herdr TUI, `herdr agent ...` (removed, every `herdr ...` command is obsolete) | herdr-core `hc`, Herdr App is optional |
| persistent `peer-review`, `peer-code`, `peer-exec` | one-shot worker `w-<id>` per task |
| `/clear` and restart to change cwd | a new process with `--cwd` |
| `scripts/codex-limits.py`, 30% threshold | `orch.py quota` for all agents, reserves in `routing.toml` |
| `.orchestration/owner.env`, `config.env` | `owner` and `[workers]` in `routing.toml`, agents in `agents.toml` |
| `peer-worktree.sh`, worktree next to the repository | `orch.py worktree`, `.orchestration/worktrees/<id>`, branch `orch/<id>` |
| reports in `docs/peer/` | reports in `docs/orch/` (old ones stay as history) |
| skill `herdr-peer` | skill `orch-workers` |
| GSD 1.17 | GSD 1.19 |

## 2. Procedure

1. Finish or accept all v0.1 tasks; commit the state.
2. `install-into-repo.sh <repo>`: new files are added, existing ones go to `.orchestration/merge-required/`;
   the installer lists the v0.1 files it found.
3. Merge the conflicts by hand. Move project rules from the old skills and `CLAUDE.md` into the new files.
4. Move project Codex parameters (model, reasoning effort, sandbox mode) to
   `.orchestration/agents.local.toml` (local) or to the project's `agents.toml` (a deliberate team decision).
5. Delete the v0.1 files from the installer's list.
6. `npx --yes @opengsd/gsd-core@1.19.0 --claude --local`, then `./scripts/reconcile-runtime-config.py`
   and `./scripts/apply-gsd-policy.py`.
7. Check: `./scripts/doctor.sh`, `orch.py route execute`, a trial read-only `review` task.
