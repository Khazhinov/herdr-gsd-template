# Upstream sources

Checked: 2026-10-16.

- Template: https://github.com/Khazhinov/herdr-gsd-template
- Open GSD / GSD Core: https://github.com/open-gsd/gsd-core
- Herdr: https://github.com/herdrdev/herdr
- Herdr docs: https://herdr.dev/docs/
- Claude Code: https://github.com/anthropics/claude-code
- OpenAI Codex: https://github.com/openai/codex

Community / talk:
- Telegram channel: https://t.me/thoughts_and_bytes/
- Conference post: https://t.me/thoughts_and_bytes/27

## Compatibility facts used by the template

- GSD Core pinned: 1.17.0.
- GSD 1.17.0 requires Node.js >=24 and npm >=10.
- GSD Codex integration requires Codex >=0.130.0.
- Herdr verified stable baseline: 0.9.3.
- Claude Code verified baseline: 2.1.301.
- Codex verified stable baseline: 0.163.0.
- Herdr `agent prompt --wait` tracks lifecycle and does not identify an application-level work item.
- Codex V1 uses `[agents].max_concurrent_threads_per_session`; `max_depth` is ignored by V2.
- This template disables both Codex native multi-agent surfaces for peer roles and controls external concurrency through Herdr.

Always re-check upstream release notes before bumping baselines.
