# Runtime compatibility

[Русский](compatibility.ru.md)

Versions checked on 2026-11-24. The template's supported minimums and GSD pin are in [versions.env](../.orchestration/versions.env).

| Component | Current upstream versions |
| --- | --- |
| Open GSD Core | [1.23.0](https://github.com/open-gsd/gsd-core/releases/tag/v1.23.0) |
| Herdr | [Core 0.1.22](https://releases.herdr.dev/core/latest.json), [App 0.1.17](https://releases.herdr.dev/app/latest.json) |
| Claude Code | [Latest 2.1.331](https://github.com/anthropics/claude-code/releases/tag/v2.1.331), [npm stable 2.1.325](https://registry.npmjs.org/@anthropic-ai%2Fclaude-code) |
| Codex CLI | [0.172.0](https://github.com/openai/codex/releases/tag/rust-v0.172.0) |
| Node.js and npm | [24.22.3 LTS](https://nodejs.org/en/blog/release/v24.22.3) on the CI major, [26.13.1 LTS](https://nodejs.org/en/blog/release/v26.13.1) on the newest LTS major, [npm 12.2.3](https://github.com/npm/cli/releases/tag/v12.2.3) |
| Python | [3.15.2](https://www.python.org/downloads/release/python-3152/). CI uses 3.11. |
| OpenCode | [1.19.6](https://github.com/anomalyco/opencode/releases/tag/v1.19.6) and [2.4.1](https://github.com/anomalyco/opencode/releases/tag/v2.4.1) |
| Kimi Code and ZCode | [Kimi Code 2.7.3](https://registry.npmjs.org/@moonshot-ai%2Fkimi-code/2.7.3), [ZCode Desktop 4.0.0](https://github.com/zai-org/ZCode/releases/tag/v4.0.0). The ZCode WSL CLI is unverified. |

## Bootstrap and GSD

Bootstrap installs `@opengsd/gsd-core` with `--claude --local`. Run `./scripts/version-check.py --strict` in the shell that will launch the coordinator and dashboard. Both use Node from that shell's PATH. Use Node.js 24 LTS and npm 10 or newer. GSD generates `.claude/settings.local.json` with local executable paths. Keep it out of version control.

GSD Core 1.19.0 and 1.23.0 passed isolated installs. An in-place upgrade to 1.23.0 passed, all 26 overlay keys were accepted, and a dashboard fixture returned the expected planning, roadmap and stopped-state data. The template remains pinned to 1.19.0 pending an interactive upgrade check.

GSD 1.23.0 can run opted-in plans in another runtime using GSD-managed worktrees. Before changing the pin, resume a disposable existing project, dispatch a worker through the template, and check worktree ownership, hook execution, dashboard updates and report collection. Exercise GSD's optional runtime routing separately so the two dispatch paths can be tested independently. [GSD 1.23.0 changes](https://github.com/open-gsd/gsd-core/releases/tag/v1.23.0)

## Herdr and other workers

- The Core 0.1.22 binary started and its CLI help included `hc wait --children any`. App 0.1.17 accepted the generated layout in a Linux check. Verify a live Core/App pair on Windows with WSL, including child states, report collection and dashboard reload, before raising the core minimum. [Core changes](https://github.com/herdrdev/herdr-core/blob/v0.1.22/CHANGELOG.md) · [App changes](https://github.com/herdrdev/herdr-app/blob/v0.1.17/CHANGELOG.md)
- The worker adapter was tested on OpenCode 1.19.5. OpenCode 2 needs an adapter port because it changed the plugin API. Verify its working, blocked and idle status transitions before using it for orchestration. [OpenCode migration guide](https://opencode.ai/docs/migrate-v1/)
