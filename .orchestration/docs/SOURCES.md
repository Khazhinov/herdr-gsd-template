# Sources

English | [Русский](SOURCES.ru.md)

Checked: 2026-11-02.

- Template: https://github.com/Khazhinov/herdr-gsd-template
- Open GSD / GSD Core: https://github.com/open-gsd/gsd-core (npm `@opengsd/gsd-core`, latest `1.19.0`)
- herdr-core: https://github.com/herdrdev/herdr-core (`hc --skill`, `hc schema`)
- Herdr App: https://github.com/herdrdev/herdr-app, https://herdr.dev/ (`herdr-app --skill`, `~/.config/herdr-app/AGENTS.md`, `herdr.d.ts`)
- Claude Code: https://github.com/anthropics/claude-code
- OpenAI Codex: https://github.com/openai/codex
- Kimi Code: https://github.com/MoonshotAI/kimi-code
- ZCode: https://github.com/zai-org/ZCode

Community (in Russian):
- Telegram channel: https://t.me/thoughts_and_bytes/
- Conference post: https://t.me/thoughts_and_bytes/27

## Facts the template relies on

| Fact | Where checked |
|---|---|
| GSD 1.19 requires Node >= 24, npm >= 10 | package `engines` in `package.json` |
| GSD 1.19: `workflow.cross_ai_command` gets the prompt on stdin, expects SUMMARY on stdout, timeout `cross_ai_timeout` | `workflows/execute-phase/detail/elaboration.md` |
| GSD 1.19: `planning.inspect` schema v1, read-only, a response > 50 KB arrives as `@file:<path>` | `bin/lib/planning-inspect.cjs` |
| GSD 1.19: configuration key check `isValidConfigKey` | `bin/lib/config-schema.cjs` |
| hc: Codex must run with `--no-daemon` | `hc --skill` |
| hc: terminals get the core's environment; children exit with the parent without `--outlive-parent` | `hc --skill`, `hc run --help`, observation |
| hc: `hc run` from inside a terminal makes the caller the parent; `hc wait --children any` returns on the next child event | `hc --skill`, `hc run --help` |
| hc: the live folder of a terminal is `foreground.cwd` of `hc get`; the `cwd` field is the start folder | `hc --skill`, observation |
| hc: the old Herdr multiplexer (`herdr agent\|pane\|tab\|workspace`) is not part of herdr-core | `hc --skill`, observation 2026-11-09 |
| hc: `doc.get/doc.set`, `events.subscribe` (including `doc`, `labels`, `status` events) | `hc schema` |
| Herdr App: mods redraw when `terminals()` changes; `readTextFile({on})`, `exec({on})` | `herdr.d.ts`, the app's `AGENTS.md` |
| Herdr App: the mod API has no clipboard call | `herdr.d.ts` |
| Herdr App: a terminal labeled `herdr.space` appears as a tab of that space | `herdr-app --skill` |
| Codex 0.165: `account/rateLimits/read` in `codex app-server` | observation (JSON-RPC) |
| Claude Code 2.1.316: `rate_limits.five_hour/seven_day` in the statusline input after the first API response | observation |
| Codex: the workspace-write sandbox cannot write to `.git` of a linked worktree even with `--add-dir` | observation (PoC) |

Recheck release pages and breaking changes before raising the baseline.
