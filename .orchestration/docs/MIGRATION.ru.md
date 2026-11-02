# Переход с v0.1 на v0.2

[English](MIGRATION.md) | Русский

## 1. Что меняется

| v0.1 | v0.2 |
|---|---|
| Herdr TUI, `herdr agent ...` | herdr-core `hc`, Herdr App необязателен |
| постоянные `peer-review`, `peer-code`, `peer-exec` | одноразовый воркер `w-<id>` на задачу |
| `/clear` и перезапуск для смены cwd | новый процесс с `--cwd` |
| `scripts/codex-limits.py`, порог 30% | `orch.py quota` для всех агентов, резервы в `routing.toml` |
| `.orchestration/owner.env`, `config.env` | `owner` и `[workers]` в `routing.toml`, агенты в `agents.toml` |
| `peer-worktree.sh`, worktree рядом с репозиторием | `orch.py worktree`, `.orchestration/worktrees/<id>`, ветка `orch/<id>` |
| отчёты `docs/peer/` | отчёты `docs/orch/` (старые остаются как история) |
| навык `herdr-peer` | навык `orch-workers` |
| GSD 1.17 | GSD 1.19 |

## 2. Порядок

1. Завершить или принять все задачи v0.1; закоммитить состояние.
2. `install-into-repo.sh <repo>`: новые файлы добавляются, существующие идут в `.orchestration/merge-required/`;
   установщик перечисляет найденные файлы v0.1.
3. Слить конфликты вручную. Проектные правила из старых навыков и `CLAUDE.md` перенести в новые файлы.
4. Перенести проектные параметры Codex (модель, уровень рассуждения, режим песочницы) в
   `.orchestration/agents.local.toml` (локально) или в `agents.toml` проекта (осознанное решение команды).
5. Удалить файлы v0.1 из списка установщика.
6. `npx --yes @opengsd/gsd-core@1.19.0 --claude --local`, затем `./scripts/reconcile-runtime-config.py`
   и `./scripts/apply-gsd-policy.py`.
7. Проверка: `./scripts/doctor.sh`, `orch.py route execute`, пробная задача `review` только на чтение.
