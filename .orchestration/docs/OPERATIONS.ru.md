# Эксплуатация

[English](OPERATIONS.md) | Русский

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
| `orch.py hub start\|stop\|restart` | публикатор для Herdr App в отдельном терминале |
| `orch.py watch` | тот же публикатор с выводом дашборда в текущий терминал |
| `orch.py tools`, `orch.py tool-ask <module> "<запрос>"` | tool-агенты хаба |
| `orch.py advice [--json]` | подсказки владельцу: сжатие или очистка контекста, смена владельца, обновление шаблона |
| `orch.py owner set <agent> [--launch] [--force]` | передача роли владельца (раздел 5) |

## 2. Локальные переопределения

`.orchestration/agents.local.toml` и `.orchestration/routing.local.toml` не коммитятся и сливаются поверх
основных файлов. Пример: модель и уровень рассуждения Codex, статический бюджет агента без зонда квоты.

```toml
[agents.codex]
command = ["codex", "--no-daemon", "-m", "<model>", "-c", "model_reasoning_effort=high"]

[agents.codex-review]                # вариант модели на той же учётной записи
command = ["codex", "--no-daemon", "-m", "<review-model>"]
capabilities = ["review"]
cost_tier = "premium"
quota = "codex"                      # общий замер квоты с [agents.codex]
quota_windows = ["5h"]               # недельное окно видно, но не ограничивает
stability = "supported"

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

Поводы: владелец исчерпывает квоту своего вендора (`orch.py advice` предлагает смену при остатке ниже `advice.owner_switch_percent`, по умолчанию 10%, и называет агента проекта с возможностью `owner` и наибольшим остатком) или решение человека.

1. Безопасная граница: задачи собраны или их можно оставить идущими (новый владелец соберёт их), решения по ревью записаны.
2. Текущий владелец выполняет `/gsd-pause-work`: GSD записывает `.planning/HANDOFF.json` и `.continue-here.md` и коммитит их.
3. GSD для нового владельца установлен официальным установщиком (`npx @opengsd/gsd-core@<pin> --<runtime> --local`); для Codex пересмотрен защитный блок `.codex/config.toml`.
4. `orch.py owner set <agent> --launch` проверяет возможность `owner` и свежесть `HANDOFF.json` (не старше `advice.handoff_max_age_minutes`), меняет `owner` в `routing.toml` и запускает нового владельца вкладкой в пространстве вызывающего терминала. `--force` пропускает проверку, если прежний владелец недоступен.
5. Новый владелец выполняет `/gsd-resume-work` и `orch.py status`; изменение `routing.toml` коммитится вместе с передачей.

## 5.1. Гигиена контекста владельца

Каждый запрос владельца повторно отправляет весь контекст, поэтому стоимость запроса растёт с размером контекста. `orch.py advice` и блок Advice в Mission Control сообщают размер контекста владельца (Claude: statusline через `statusline-tap`; Codex: журнал сессии) и предлагают `compact_command` агента после `advice.compact_tokens` (по умолчанию 100 тыс.) и `/gsd-pause-work` с `clear_command` после `advice.clear_tokens` (160 тыс.). Подходящая точка: нет идущих воркеров или задачи только что собраны; посреди фазы допустимо на такой точке. Команды сжатия и очистки задаются в `agents.toml` для каждой среды.

Если последнее низкое значение квоты владельца устарело, но его окно ещё не сбросилось, Advice показывает условный совет о передаче роли. Перед `/gsd-pause-work` нужно подтвердить текущую квоту; автоматическая маршрутизация по устаревшему значению не выполняется. Щелчок по команде в Advice копирует её в буфер обмена (App в Windows). Кнопка перезапуска в заголовке Mission Control запускает `orch.py hub restart` и обновляет публикатор состояния.

## 5.2. Обновление шаблона

`.orchestration/template.toml` хранит версию шаблона проекта и адрес репозитория. Hub раз в `advice.update_check_hours` (24 ч), при запуске и при смене фазы сравнивает её с последним тегом `vX.Y.Z` (`git ls-remote --tags`) и при новой версии показывает подсказку. `orch.py advice` тоже проверяет тег заново. Обновление выполняет человек через `scripts/install-into-repo.sh` нового выпуска.

Возможность быть владельцем подтверждается тестом в целевой среде, а не предполагается.

## 6. Внешние ресурсы worktree

Скопировать `.orchestration/hooks/worktree-env.example` в `.orchestration/hooks/worktree-env`, сделать исполняемым
и настроить изоляцию БД, портов и кэшей. Хук вызывается после создания каждого worktree.

## 7. Обновление зависимостей

Версии не меняются только потому, что вышел новый выпуск.

1. Изменить `.orchestration/versions.env`.
2. Прочитать примечания к выпуску каждого обновляемого компонента.
3. `./scripts/version-check.py --strict`.
4. Переустановить GSD официальным установщиком.
5. `./scripts/reconcile-runtime-config.py`.
6. `./scripts/self-check.sh --offline`.
7. Smoke-тест воркера через herdr-core: `orch.py dispatch` задачи `research`, затем `execute` в worktree, `collect`, `worktree merge`.
8. Обновить `.orchestration/docs/COMPATIBILITY.md` и `REVIEW.md`.
