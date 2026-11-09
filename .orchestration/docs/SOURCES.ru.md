# Источники

[English](SOURCES.md) | Русский

Проверено: 2026-11-02.

- Шаблон: https://github.com/Khazhinov/herdr-gsd-template
- Open GSD / GSD Core: https://github.com/open-gsd/gsd-core (npm `@opengsd/gsd-core`, latest `1.19.0`)
- herdr-core: https://github.com/herdrdev/herdr-core (`hc --skill`, `hc schema`)
- Herdr App: https://github.com/herdrdev/herdr-app, https://herdr.dev/ (`herdr-app --skill`, `~/.config/herdr-app/AGENTS.md`, `herdr.d.ts`)
- Claude Code: https://github.com/anthropics/claude-code
- OpenAI Codex: https://github.com/openai/codex
- Kimi Code: https://github.com/MoonshotAI/kimi-code
- ZCode: https://github.com/zai-org/ZCode

Сообщество:
- Telegram-канал: https://t.me/thoughts_and_bytes/
- Пост о конференции: https://t.me/thoughts_and_bytes/27

## Факты, на которые опирается шаблон

| Факт | Где проверено |
|---|---|
| GSD 1.19 требует Node >= 24, npm >= 10 | `package.json` пакета `engines` |
| GSD 1.19: `workflow.cross_ai_command` получает промпт на stdin, ожидает SUMMARY на stdout, таймаут `cross_ai_timeout` | `workflows/execute-phase/detail/elaboration.md` |
| GSD 1.19: `planning.inspect` schema v1, только чтение, ответ > 50 КБ приходит как `@file:<path>` | `bin/lib/planning-inspect.cjs` |
| GSD 1.19: проверка ключей конфигурации `isValidConfigKey` | `bin/lib/config-schema.cjs` |
| hc: Codex должен работать с `--no-daemon` | `hc --skill` |
| hc: терминалы получают окружение ядра; дети завершаются с родителем без `--outlive-parent` | `hc --skill`, `hc run --help`, наблюдение |
| hc: `hc run` изнутри терминала делает вызывающий терминал родителем; `hc wait --children any` возвращается на следующем событии потомка | `hc --skill`, `hc run --help` |
| hc: текущая папка терминала - `foreground.cwd` из `hc get`; поле `cwd` - папка запуска | `hc --skill`, наблюдение |
| hc: старый мультиплексор Herdr (`herdr agent\|pane\|tab\|workspace`) не входит в herdr-core | `hc --skill`, наблюдение 2026-11-09 |
| hc: `doc.get/doc.set`, `events.subscribe` (включая события `doc`, `labels`, `status`) | `hc schema` |
| Herdr App: моды перерисовываются при изменении `terminals()`; `readTextFile({on})`, `exec({on})` | `herdr.d.ts`, `AGENTS.md` приложения |
| Herdr App: в API модов нет функции буфера обмена | `herdr.d.ts` |
| Herdr App: терминал с меткой `herdr.space` появляется во вкладке пространства | `herdr-app --skill` |
| Codex 0.165: `account/rateLimits/read` в `codex app-server` | наблюдение (JSON-RPC) |
| Claude Code 2.1.316: `rate_limits.five_hour/seven_day` во входе statusline после первого ответа API | наблюдение |
| Codex: песочница workspace-write не даёт писать в `.git` linked worktree даже с `--add-dir` | наблюдение (PoC) |

Перед повышением baseline заново проверять страницы релизов и ломающие изменения.
