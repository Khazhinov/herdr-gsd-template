# Совместимость - 2026-11-02

[English](COMPATIBILITY.md) | Русский

| Компонент | Версия в проверке | Требование шаблона | Примечание |
|---|---|---|---|
| GSD Core | 1.19.0 | pin `1.19.0` | установщик `--claude --local`; ключи overlay проверяются тестом |
| herdr-core | 0.1.16 | `>= 0.1.16` | `hc run/wait/get/ls/label/kill/rm/connect`, документы, события |
| Herdr App | 0.1.11 (Windows) | необязателен | мод Mission Control и раскладка; ядро в WSL как SSH-машина |
| Claude Code | 2.1.316 | `>= 2.1.316` | statusline `rate_limits`, наследование доверия папки |
| Codex CLI | 0.165.0 | `>= 0.165.0` | `--no-daemon`, `app-server` RPC квот, `-c projects.<path>.trust_level` |
| Node.js | 22.22.0 (среда проверки) | `>= 24` (требование GSD) | GSD 1.19 работает на 22 без проверки движка в рантайме; требование upstream сохранено |
| Python | 3.12.3 | `>= 3.11` | `tomllib`, `datetime.UTC` |
| Kimi Code | установлен в `~/.kimi-code/bin`, подписка не оплачена | `candidate` | TUI без начального промпта (`prompt = "send"`); smoke-тест не выполнен |
| OpenCode | 1.19.5 | `candidate` | `--prompt` для начального промпта; smoke-тест воркера пройден на `opencode/deepseek-v4.1-flash-free`; статус herdr-core требует плагина `.orchestration/adapters/opencode/herdr-core-status.js` (OSC 7501), штатный плагин herdr говорит с сокетом прежнего Herdr TUI |
| ZCode | не установлен | `experimental` | адаптер описан, smoke-тест не выполнен |

## Пути

| Путь | Состояние |
|---|---|
| Windows Herdr App -> WSL2 (SSH-машина) | проверен: PoC, воркеры, мод, раскладка |
| Linux без App | проверен частично: `orch.py watch` как терминальный дашборд, офлайн-тесты |
| macOS | не проверен |
