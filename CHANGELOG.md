# Changelog

## 0.2.0 - 2026-11-02

- Owner advice (`orch.py advice`, Mission Control): context size with compact/clear hints, owner switch
  suggestion when the owner vendor runs low, template update check (`.orchestration/template.toml`).
- `orch.py owner set <agent> [--launch]`: owner handoff on top of GSD pause-work/resume-work.
- OpenCode adapter (candidate): worker smoke test passed; herdr-core status plugin in `.orchestration/adapters/opencode`.

- Account-wide admission ledger with locked dispatch, per-window quota projections and cost samples,
  owner reserve, vendor denial handling, and unknown post-reset windows.
- Collect stops workers before committing; merge preflights conflicts and protects `.planning/`.
  Duplicate task ids require `--replace`; `dispatch --of` routes reviews away from the author account.
- Quota-aware admission: the reserve is checked against the projection after the task
  (measured per-task spend, spend still ahead of running tasks on the same account).
  `collect` records `quota_burn`; Mission Control shows the per-task cost under Limits.
- Task contract gains "Quota discipline": one long call instead of polling `ps`/`tail`.

- Execution substrate moved from the legacy Herdr TUI to herdr-core (`hc`); Herdr App is the optional UI.
- Agent registry (`.orchestration/agents.toml`) and routing policy (`routing.toml`) replace hard-coded Claude/Codex peers.
- Deterministic scheduler with recorded reasons: capability, live quota, reserves, review independence,
  stability gate, per-agent parallelism, manual override; strategies `ordered`, `cheapest`, `use-or-lose`.
- Live quotas: Codex app-server RPC (`account/rateLimits/read`), Claude statusline `rate_limits` tap;
  unknown or stale quota fails closed for heavy work.
- Disposable workers per task (`orch.py dispatch/wait/collect`), worktrees inside the repository,
  owner-side commit, guard against removing a worktree with a live terminal.
- GSD Mission Control: Herdr App mod and layout, reactive through hub terminal labels; terminal dashboard `orch.py watch`.
- GSD 1.19.0: overlay validated by GSD's own key validator, `cross_ai_command` bridge, native reviewer lanes for the strict profile.
- Tool-agent hub integration (`orch.py tools`, `orch.py tool-ask`).
- Removed v0.1 peer scripts, `owner.env`, `config.env`, `codex-limits.py`, skill `herdr-peer`.

## 0.1.0 - 2026-10-16

Initial public template.

- Updated compatibility baseline to GSD Core 1.17.0, Herdr 0.9.3, Claude Code 2.1.301 and Codex 0.163.0.
- Raised GSD runtime requirement to Node.js 24 / npm 10.
- Decoupled orchestration ownership from GSD runtime/model settings.
- Added public README, upstream links, talk/channel references and MIT license.
- Removed per-process Codex reasoning-effort CLI overrides.
- Disabled recursive Codex native subagents for default peer roles.
- Extended quota estimator to primary + secondary visible windows.
- Clarified the Codex-first quota strategy in README: consume Codex capacity first, fall back to Claude for new heavy tasks near the reserve threshold.
- Added `doctor.sh`, explicit version compatibility checks, fail-closed overlay conflict handling and credential-free GitHub Actions regression tests, including a pinned GSD installer smoke-test.
- Revalidated worktree root-before-remove lifecycle and overlay installation; fixed machine-readable worktree path output.
