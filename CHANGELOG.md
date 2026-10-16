# Changelog

## 0.1.0 — 2026-10-16

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
