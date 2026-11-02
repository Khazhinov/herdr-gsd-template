# Эксплуатация

## 1. Команды

| Команда | Назначение |
|---|---|
| `orch.py quota [--refresh]` | квоты всех агентов с источником и достоверностью |
| `orch.py route <role> [--heavy\|--light]` | пробный выбор агента с причиной |
| `orch.py prefer <role> <agent\|->` | ручное переопределение следующего выбора (снимается `-`) |
| `orch.py dispatch <task.md> --role <r> --id <id>` | запуск воркера; `execute` получает worktree |
| `orch.py wait [--timeout S]` | ожидание события воркеров |
| `orch.py collect <id> [--keep-worker]` | проверка доказательств, коммит worktree, остановка воркера |
| `orch.py worktree merge\|remove\|path <id>` | слияние или отказ от ветки `orch/<id>` |
| `orch.py status [--json]` | снимок состояния |
| `orch.py hub start\|stop` | публикатор для Herdr App в отдельном терминале |
| `orch.py watch` | тот же публикатор с выводом дашборда в текущий терминал |
| `orch.py tools`, `orch.py tool-ask <module> "<запрос>"` | tool-агенты хаба |

## 2. Локальные переопределения

`.orchestration/agents.local.toml` и `.orchestration/routing.local.toml` не коммитятся и сливаются поверх
основных файлов. Пример: модель и уровень рассуждения Codex, статический бюджет агента без зонда квоты.

```toml
[agents.codex]
command = ["codex", "--no-daemon", "-m", "<model>", "-c", "model_reasoning_effort=high"]

[agents.kimi]
stability = "supported"          # после smoke-теста
quota = "static"
quota_static = {remaining_percent = 100}
```

## 3. Воркер ждёт человека

`dispatch` сообщает `startup.ok: false`, если агент не сообщил статус за 25 с. Типичные причины:
диалог доверия к корню проекта (первый запуск агента в проекте), вход в учётную запись.
Ответ даёт человек в Herdr App или через `hc attach w-<id>`. Владелец не нажимает клавиши за человека.

Статус `blocked` во время работы означает запрос разрешения. Он виден в App, дашборде и в ответе `orch.py wait`.

## 4. Восстановление после перезапуска

- Сессия владельца: `orch.py status` показывает незавершённые задачи; `collect` по каждой.
- Перезагрузка машины или ядра: herdr-core не возобновляет агентов. Задача без живого терминала и без
  отчёта получает `incomplete` в `collect`; worktree и ветка остаются для ручного разбора.
- `hub` перезапускается командой `orch.py hub start`.

## 5. Передача роли владельца

1. Безопасная граница: всё закоммичено, решения по ревью записаны, нет задач в состоянии `running`.
2. Установить GSD для нового владельца официальным установщиком (`npx @opengsd/gsd-core@<pin> --<runtime> --local`).
3. Пересмотреть защитный блок `.codex/config.toml`, если владельцем становится Codex.
4. Изменить `owner` в `routing.toml` отдельным коммитом.
5. Новый владелец восстанавливается по `.planning/`, `docs/orch/`, Git.

Возможность быть владельцем подтверждается тестом в целевой среде, а не предполагается.

## 6. Внешние ресурсы worktree

Скопировать `.orchestration/hooks/worktree-env.example` в `.orchestration/hooks/worktree-env`, сделать исполняемым
и настроить изоляцию БД, портов и кэшей. Хук вызывается после создания каждого worktree.
