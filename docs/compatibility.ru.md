# Совместимость сред

[English](compatibility.md)

Версии проверены 24 ноября 2026 года. Минимальные версии и закреплённая версия GSD указаны в [versions.env](../.orchestration/versions.env).

| Компонент | Актуальные версии |
| --- | --- |
| Open GSD Core | [1.23.0](https://github.com/open-gsd/gsd-core/releases/tag/v1.23.0) |
| Herdr | [Core 0.1.22](https://releases.herdr.dev/core/latest.json), [App 0.1.17](https://releases.herdr.dev/app/latest.json) |
| Claude Code | [Latest 2.1.331](https://github.com/anthropics/claude-code/releases/tag/v2.1.331), [npm stable 2.1.325](https://registry.npmjs.org/@anthropic-ai%2Fclaude-code) |
| Codex CLI | [0.172.0](https://github.com/openai/codex/releases/tag/rust-v0.172.0) |
| Node.js и npm | [24.22.3 LTS](https://nodejs.org/en/blog/release/v24.22.3) на ветке CI, [26.13.1 LTS](https://nodejs.org/en/blog/release/v26.13.1) на новейшей LTS-ветке, [npm 12.2.3](https://github.com/npm/cli/releases/tag/v12.2.3) |
| Python | [3.15.2](https://www.python.org/downloads/release/python-3152/). В CI используется 3.11. |
| OpenCode | [1.19.6](https://github.com/anomalyco/opencode/releases/tag/v1.19.6) и [2.4.1](https://github.com/anomalyco/opencode/releases/tag/v2.4.1) |
| Kimi Code и ZCode | [Kimi Code 2.7.3](https://registry.npmjs.org/@moonshot-ai%2Fkimi-code/2.7.3), [ZCode Desktop 4.0.0](https://github.com/zai-org/ZCode/releases/tag/v4.0.0). CLI ZCode в WSL не проверен. |

## Установка и GSD

Установщик запускает `@opengsd/gsd-core` с флагами `--claude --local`. Выполните `./scripts/version-check.py --strict` в оболочке, из которой запускаете координатор и панель. Оба берут Node из её PATH. Используйте Node.js 24 LTS и npm версии 10 или новее. GSD генерирует `.claude/settings.local.json` с локальными путями к исполняемым файлам. Этот файл следует держать вне Git.

GSD Core 1.19.0 и 1.23.0 прошли изолированную установку. Проверка обновления поверх старой версии прошла, конфигурация приняла все 26 ключей, тест панели вернул ожидаемые данные плана, дорожной карты и остановленной сессии. В шаблоне закреплена 1.19.0 до проверки интерактивного сценария обновления.

GSD 1.23.0 умеет выполнять планы с явно выбранной средой в собственных worktree. Перед сменой закреплённой версии возобновите тестовый проект, запустите исполнителя через шаблон и проверьте владение worktree, хуки, обновление панели и сбор отчёта. Отдельно проверьте новую маршрутизацию GSD, чтобы испытать оба способа запуска независимо. [Изменения GSD 1.23.0](https://github.com/open-gsd/gsd-core/releases/tag/v1.23.0)

## Herdr и другие среды

- Двоичный файл Core 0.1.22 запустился, в справке есть `hc wait --children any`. App 0.1.17 принял сгенерированную раскладку при проверке в Linux. Перед повышением минимальной версии core проверьте связку Core/App на Windows с WSL, включая состояния дочерних процессов, сбор отчётов и перезагрузку панели. [Изменения Core](https://github.com/herdrdev/herdr-core/blob/v0.1.22/CHANGELOG.md) · [Изменения App](https://github.com/herdrdev/herdr-app/blob/v0.1.17/CHANGELOG.md)
- Адаптер исполнителя проверен на OpenCode 1.19.5. В OpenCode 2 изменился API плагинов, поэтому адаптер надо портировать. Перед использованием в оркестрации проверьте переходы между статусами working, blocked и idle. [Руководство по миграции OpenCode](https://opencode.ai/docs/migrate-v1/)
