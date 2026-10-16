# Compatibility snapshot — 2026-10-16

## GSD Core

Pinned by bootstrap: `@opengsd/gsd-core@1.17.0`.

Official project-local installer:
```bash
npx --yes @opengsd/gsd-core@1.17.0 --claude --local
```

Codex is peer-only by default, so bootstrap does not install GSD into Codex.
For an intentional owner handoff, run the official Codex installer as a separate migration step and revisit the project-local peer-lockdown config.

GSD v1.17.0 declares Node.js >=24.0.0 and npm >=10.0.0.
GSD documentation requires Codex CLI >=0.130.0 for full Codex integration.

The template uses its own `.orchestration/owner.env` for canonical state ownership.
GSD `runtime: claude` in the policy is model/runtime-resolution configuration, not an ownership lock.

## Herdr

Verified baseline: `v0.9.3`.

Used APIs:
- `pane split --cwd ... --no-focus`;
- `pane run`;
- `agent start/get/read/prompt/wait`.

Herdr lifecycle is scheduling/process state.
Logical task completion remains report/sentinel + Git/check evidence.

## Claude Code

Verified baseline: `v2.1.301`.

Claude is the default top-level owner. This repository does not install Claude Code itself.

## Codex

Verified baseline: `0.163.0`.

Project config disables native peer fan-out:
- `[agents].enabled = false`;
- `[features.multi_agent_v2].enabled = false`.

The canonical V1 concurrency key is `max_concurrent_threads_per_session`;
`max_depth` only applies to V1. The protocol rule remains authoritative regardless of backend.

Codex `/clear` is used to start a fresh peer chat.
Model names are not hard-coded; optional `CODEX_*_MODEL` values are passed with native `-m`.

No `-c model_reasoning_effort=...` startup override is used by the Herdr wrapper.

## Version policy

GSD is pinned for reproducibility because its installer writes project/runtime artifacts.
Herdr, Claude and Codex are native authenticated user tools: the template records a verified minimum baseline and accepts newer compatible releases.

Run:
```bash
./scripts/version-check.py --strict
./scripts/doctor.sh
```
