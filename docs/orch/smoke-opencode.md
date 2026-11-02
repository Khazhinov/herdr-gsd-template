# Отчёт smoke-opencode: проверка адаптера воркера OpenCode

## Метод

Каталог `scripts/orchlib/` содержит 8 модулей Python (служебный `__pycache__` не учитывается). Для каждого модуля прочитаны только докстринг (первые 15 строк) и имена функций/классов верхнего уровня, как требует контракт.

## Модули

| Файл | Назначение | Функции и классы верхнего уровня |
| --- | --- | --- |
| `__init__.py` | Пустой файл, оформляет `scripts/orchlib` как пакет Python. | отсутствуют |
| `advice.py` | Формирует рекомендации для человека, ведущего роль owner: когда компактизировать или очищать контекст owner, когда передать роль другому агенту, когда доступен новый релиз шаблона. Только чтение: модуль предлагает, решение принимает человек. | `settings`, `record_session`, `transcript_tokens`, `claude_context`, `codex_context`, `owner_context`, `handoff`, `template_info`, `latest_release`, `update`, `compute` |
| `config.py` | Загружает и валидирует реестр агентов и политику маршрутизации. | `ConfigError`, `merge`, `load`, `validate`, `reserve`, `project_name` |
| `hc.py` | Тонкий доступ к herdr-core: CLI `hc` для команд и `hc connect` для JSON-RPC (документы, подписка на события); `ORCH_HC` подменяет бинарник в тестах. | `HCError`, `binary`, `call`, `ls`, `get`, `run`, `send`, `wait`, `label`, `kill`, `rm`, `read`, `RPC`, `doc_put_once` |
| `quota.py` | Пробы квот: каждая проба возвращает нормализованный словарь (доступность, достоверность, источник, окна, эффективный остаток); пробы не угадывают, при отсутствии данных доступность ложна, достоверность `unknown`. | `unknown`, `window`, `label`, `finish`, `codex_rpc`, `codex_from_rpc`, `codex_from_rollouts`, `probe_codex`, `probe_claude`, `probe_static`, `account`, `probe`, `gate`, `all_quotas`, `known`, `headroom` |
| `route.py` | Детерминированный выбор воркера: чистая функция, идентификаторы агентов отсутствуют в коде и приходят из `agents.toml`, `routing.toml` и нормализованных квот. | `cost`, `decide` |
| `state.py` | Единый машиночитаемый снимок для дашбордов: маршрутизация, квоты, задачи, GSD; публикуется в `state.json`, документ herdr-core и метки терминала наблюдения. | `gsd_tools`, `stopped_at`, `gsd_query`, `planning`, `summarize`, `providers`, `compose`, `publish` |
| `tasks.py` | Жизненный цикл задачи на herdr-core: route -> worktree -> hc run -> report -> collect; воркер считается завершённым только при report с sentinel, а для исполнения ещё и при коммитах в ветке на чистом дереве. | `runtime`, `git`, `write_json`, `task_path`, `load_task`, `save_task`, `all_tasks`, `log_decision`, `override_get`, `override_set`, `installed`, `admission`, `ledger`, `save_ledger`, `ledger_drop`, `running_counts`, `costs`, `pending`, `decide`, `preview`, `wt_paths`, `wt_create`, `terminals_inside`, `wt_guard`, `wt_remove`, `wt_merge`, `planning_guard`, `dispatch`, `quota_mark`, `quota_burn`, `overlapped`, `startup_check`, `report_sentinel`, `evidence`, `verdict`, `collect`, `refresh` |

## Замечания

- Ограничения контракта соблюдены: полные файлы не читались, изменён только этот отчёт.
- Модуль `route.py` не содержит идентификаторов агентов, что согласуется с заявленной детерминированностью и конфигурируемостью через TOML.
- В `tasks.py` функция `dispatch` и `collect` обслуживают основной конвейер задачи; вокруг них сосредоточены защита worktree (`wt_guard`, `wt_merge`), учёт квот (`quota_mark`, `quota_burn`) и проверка отчёта (`report_sentinel`, `verdict`).

Result: complete
