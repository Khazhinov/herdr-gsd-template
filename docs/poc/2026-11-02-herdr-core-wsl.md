# PoC: Herdr App (Windows) -> WSL2 -> herdr-core -> Claude владелец -> Codex воркер

Дата: 2026-11-02. Среда: Windows 11, Herdr App 0.1.11, WSL2 Ubuntu 24.04.1, hc 0.1.16,
Claude Code 2.1.316, Codex 0.165.0.

## 1. Результаты

| # | Проверка (пакет миграции, раздел 19) | Результат |
|---|---|---|
| 1 | Herdr App открывает репозиторий в WSL через SSH-машину | выполнено: пространство на машине `herdr-wsl`, Claude владелец в терминале `t1` |
| 2 | Владелец запускает Codex через `hc`, задача только на чтение, ответ без изменений файлов | выполнено: `orch.py dispatch --role review`, отчёт с маркером, `collect` = complete |
| 2a | Воркер виден в Herdr App | выполнено: метка `herdr.space` -> вкладка в пространстве владельца |
| 3 | Воркер в worktree через `--cwd`, коммит изолирован, main не затронут | выполнено после доработки (раздел 2) |
| 3a | Воркер завершается, worktree удаляется только после выхода | выполнено: удаление при живом терминале отклонено, после `collect` слияние прошло |
| 3b | Сообщение родителю через `hc send` | доставлено как `<hc from="t7 w-poc-exec-1">`, но из песочницы Codex требует подтверждения |
| 4 | Закрытие и повторное открытие App не останавливает воркера | не проверялось автоматически: требует действия человека; ядро в WSL независимо от окна по документации |
| 5 | Квоты | Codex: живой RPC `account/rateLimits/read`; журналы сессий тоже читаются. Claude: statusline `rate_limits` |

## 2. Отклонения и решения

| Наблюдение | Решение |
|---|---|
| `hc run claude` -> `spawn_failed`: ядро запущено с системным PATH без `~/.local/bin` | argv воркера: `env PATH=... <agent>` с переменными из `pass_env` |
| Codex в новом worktree показывает диалог доверия | `-c projects."<worktree>".trust_level="trusted"` для worktree, созданных оркестратором |
| Claude в подпапке доверенного проекта диалог не показывает | worktree внутри репозитория: `.orchestration/worktrees/<id>` |
| Codex не может писать в `.git/worktrees/<id>` даже с `--add-dir` | воркер не коммитит; коммит в `orch.py collect` |
| `hc send` из песочницы Codex не достигает сокета ядра без подтверждения | завершение по `hc wait --children` и отчёту |
| Копия отчёта в корне мешала слиянию ветки | копия уходит в `.orchestration/runtime/reports/` |
| Публикация состояния будила наблюдатель собственным событием `doc` | наблюдатель реагирует только на события терминалов, кроме собственного |
| `rate_limits` нет во входе statusline до первого ответа API | квота Claude `unknown` до первого ответа владельца |

## 3. Команды

```bash
python3 scripts/orch.py quota
python3 scripts/orch.py dispatch .orchestration/runtime/poc-review.md --role review --id poc-review-1
python3 scripts/orch.py wait
python3 scripts/orch.py collect poc-review-1
python3 scripts/orch.py dispatch .orchestration/runtime/poc-exec.md --role execute --id poc-exec-1
python3 scripts/orch.py worktree remove poc-exec-1     # отказ: живой терминал внутри
python3 scripts/orch.py collect poc-exec-1
python3 scripts/orch.py worktree merge poc-exec-1
python3 scripts/orch.py hub start
./scripts/herdr-app-install.sh
```
