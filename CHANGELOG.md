# Changelog

## 0.2.9 - 2026-11-09

- Documentation: a quick start for a person and for the owner agent in both READMEs (what to install,
  first command, where worker tabs appear, how to wait and collect); the general launch scheme
  through `hc` is referenced in herdr-agent-kit (`concepts/herdr-launch.md`), not repeated.
- Documentation: the old Herdr multiplexer (`herdr agent|pane|tab|workspace`) is marked removed;
  OPERATIONS and orch-workers describe `foreground.cwd` versus `cwd`, the tab name and `where`
  caption, the manual start check (`state`, `status.state`, `herdr.space`, `first_message.sent`) and
  waiting only through `hc wait --children any`; SOURCES lists these facts.

## 0.2.8 - 2026-11-04

- Mission Control hides its per-window limits while herdr-agent-kit's `agent-limits` mod is shown
  in the layout (no duplicate); the per-task quota cost stays.
- Claude quota also merges the per-session taps of herdr-agent-kit's global statusLine wrapper
  (`~/.cache/herdr-agent-kit/limits/claude/`, `HERDR_AGENT_KIT_CACHE`), so sessions outside GSD
  projects count too. Tests isolate that folder.

## 0.2.7 - 2026-11-04

- `herdr-app-install.sh` keeps sidebar blocks of `gsd-mission-control` that other installers changed
  or added (herdr-agent-kit's `space-groups` and `agent-limits`) when it regenerates the layout from
  `main`; before, a reinstall dropped them.

## 0.2.6 - 2026-11-04

- Workers and a launched owner are always shown in Herdr App. `[workers] space = "caller"` (default)
  keeps the owner's space and falls back to the project's space when the owner terminal is not in
  the App, where workers used to stay hidden; `"project"` uses the space whose tabs work inside the
  repository (matched by the live folder of its terminals, as Mission Control does) and creates one
  when none exists. `orch.py owner set --launch --space caller|project`.

## 0.2.5 - 2026-11-04

- The tool hub is renamed herdr-agent-kit: `HERDR_AGENT_KIT` names its folder (the old
  `HERDR_TOOL_AGENTS` is still read and passed to workers); the owner skill describes linked service
  repositories and the per-module files under `.agent-tools/`.

## 0.2.4 - 2026-11-04

- `orch tools-link <module>...` links modules of the herdr-tool-agents MCP registry to the project:
  git-ignored `.agent-tools/TOOLS.md` plus a pointer line in `AGENTS.md`; the owner skill describes
  picking modules, calling them and that the hub keeps `TOOLS.md` current.
- `AGENTS.md` and `.claude/CLAUDE.md` start with mandatory publication safety rules.

## 0.2.3 - 2026-11-03

- `doctor.sh` checks that the Codex sandbox can run a command (`codex sandbox -- /bin/true`) when the
  registry has a Codex agent; OPERATIONS, section 3.1 explains `bwrap: execvp .../codex` and its fix.
- README links the machine-wide optimization stack repository.

## 0.2.2 - 2026-11-02

- The hub exits on its own when the project folder is gone or no live terminal works inside the project
  for `watch.idle_exit_minutes` (60 by default).

- Mission Control offers a hub restart button.
- Advice commands copy to the clipboard on click.
- Documentation is in English; Russian copies live next to it as `*.ru.md`.
- Mission Control no longer lists phases below 10 twice (GSD pads phase dirs, ROADMAP does not).
- The template update hint is a command that runs as copied (temporary clone of the release tag).
- Owner handoff advice shows a conditional warning when the last low quota reading is stale but its window has not reset.
- Offline lifecycle tests no longer depend on Claude or Codex CLI being installed on the runner.

## 0.2.1 - 2026-11-02

- Mission Control wraps long advice and displays the full command in a compact panel.
- Script execute modes are recorded in Git and checked by the offline suite.
- Template update advice refreshes at hub startup, phase changes and explicit `orch.py advice` calls.

## 0.2.0 - 2026-11-02

Known limitations: the hub, its herdr-core document and the `orch.project` label derive from the
project folder name, so two checkouts with the same folder name on one machine share them (review C17).
Kimi Code and ZCode are not smoke-tested; OpenCode is verified for `research` only.

- Owner advice (`orch.py advice`, Mission Control): context size with compact/clear hints, owner switch
  suggestion when the owner vendor runs low, template update check (`.orchestration/template.toml`).
- `orch.py owner set <agent> [--launch]`: owner handoff on top of GSD pause-work/resume-work.
- OpenCode adapter (candidate): research smoke test passed; herdr-core status plugin in `.orchestration/adapters/opencode`.

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
