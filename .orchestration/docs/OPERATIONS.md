# Operations

English | [Русский](OPERATIONS.ru.md)

## 1. Commands

| Command | Purpose |
|---|---|
| `orch.py quota [--refresh]` | quotas of all agents with source and confidence |
| `orch.py route <role> [--heavy\|--light]` | dry-run agent selection with the reason |
| `orch.py prefer <role> <agent\|->` | manual override of the next selection (`-` clears it) |
| `orch.py dispatch <task.md> --role <r> --id <id>` | starts a worker; `execute` gets a worktree |
| `orch.py wait [--timeout S]` | waits for a worker event |
| `orch.py collect <id> [--keep-worker]` | checks evidence, commits the worktree, stops the worker |
| `orch.py worktree merge\|remove\|path <id>` | merges or drops the `orch/<id>` branch |
| `orch.py status [--json]` | state snapshot |
| `orch.py hub start\|stop\|restart` | publisher for Herdr App in its own terminal |
| `orch.py watch` | the same publisher, printing the dashboard to the current terminal |
| `orch.py tools`, `orch.py tool-ask <module> "<request>"` | hub tool agents |
| `orch.py advice [--json]` | owner hints: compact or clear context, owner handoff, template update |
| `orch.py owner set <agent> [--launch] [--space caller\|project] [--force]` | owner handoff (section 5) |

## 2. Local overrides

`.orchestration/agents.local.toml` and `.orchestration/routing.local.toml` are not committed and are merged over
the main files. Example: Codex model and reasoning effort, a static budget for an agent without a quota probe.

```toml
[agents.codex]
command = ["codex", "--no-daemon", "-m", "<model>", "-c", "model_reasoning_effort=high"]

[agents.codex-review]                # model variant on the same account
command = ["codex", "--no-daemon", "-m", "<review-model>"]
capabilities = ["review"]
cost_tier = "premium"
quota = "codex"                      # shares the quota reading with [agents.codex]
quota_windows = ["5h"]               # the weekly window is visible but does not limit
stability = "supported"

[agents.kimi]
stability = "supported"          # after the smoke test
quota = "static"
quota_static = {remaining_percent = 100}
```

## 3. A worker waits for a human

`dispatch` reports `startup.ok: false` if the agent has not reported a status within 25 s. Typical causes:
the project root trust dialog (first agent start in the project), account login.
A human answers in Herdr App or with `hc attach w-<id>`. The owner never presses keys for the human.

Manual check of a started worker: `hc get w-<id>` shows `state = live`, a `status.state` value (the agent reports it
over OSC 7501 once its interface is up) and the `herdr.space` label (the tab exists in the App). For a direct
`hc run` the JSON output also has `first_message.sent`; `dispatch` passes the first message as an argument, so
it is not lost while the agent loads.

A `blocked` status during work means a permission request. It is visible in the App, the dashboard and the `orch.py wait` output.

## 3.1. Codex worker fails with `bwrap: execvp .../codex`

Codex runs shell commands by starting its own binary inside a bwrap sandbox. If the active permission
profile (`default_permissions` in `~/.codex/config.toml`) denies `":root"` and does not let the sandbox
read the Codex installation (for the standalone installer: `~/.codex/packages`), every command fails
before it starts and the worker stops without a report. `codex exec` with an explicit `-s` hides the problem,
because the legacy sandbox mode replaces the profile and opens the whole file system for reading.

Fix the profile, not the worker command: drop the `":root"` deny and deny only the secret paths
(`"~/.config/secrets" = "deny"`), or allow reading the Codex installation. Check with
`codex sandbox -- /bin/true`; `./scripts/doctor.sh` runs this check when the registry has a Codex agent.

## 3.2. Worker tabs in Herdr App

With `[workers] show_in_app = true` every worker and a launched owner get a tab; none stays hidden.
`[workers] space` picks the space:

| Value | Space |
|---|---|
| `caller` (default) | the space of the terminal that ran `dispatch` (the owner's); when that terminal is not in the App (started by `hc run`, outside Herdr App), the project's space |
| `project` | the space whose tabs work inside this repository now (live folder of its terminals, as Mission Control decides); created with one tab when none exists |

The App stores its layout in the core document `herdr-app`; a terminal labelled `herdr.space=<id>`
gets a tab there. The stored `folder` of a space is where it was created and does not follow `cd`,
so it is only a fallback. The live folder of a terminal is `foreground.cwd` from `hc get` (the folder of the
program running in it); the `cwd` field is the folder the terminal was started in. The tab name comes from
`--name` (`w-<id>`); a `where` label, when set, gives the tab caption. Closing a worker's tab ends the worker; its task stays and `collect`
reports it.

## 3.3. Owner handoff: command access and runtime

`HC_TERMINAL_ID` proves inherited terminal identity, not access to the Herdr core.
A Codex TUI can be visible in Herdr while its shell tool cannot connect to the core Unix socket.
`--no-daemon` keeps execution in the terminal; it does not grant socket, cache or Git permissions.
Test `hc get "$HC_TERMINAL_ID"` through the new agent's own command tool, not only in the launching
shell. An `EPERM` socket connection followed by a systemd startup error is not proof the core is down.
Do not restart the core or replace GSD workers with inline execution to work around this error.

Before transfer, configure the target agent's explicit `gsd_runtime` in `agents.toml` or the local
override (custom owner ids need it too). `owner set` updates GSD `config.json.runtime` along with
`routing.toml`; other GSD settings are retained. `--launch` checks caller core access first and
restores both files if `hc run` fails. `--force` skips only handoff freshness, not permissions.
A launched terminal is not yet a verified owner environment. In that terminal, run the core probe,
`orch.py hub start`, and `orch.py status --no-planning` before dispatch. Check that its Herdr tab,
space, parent and Mission Control are visible, then verify a harmless worker start/report/collect.
An explicit command without `--launch` only updates configuration; it cannot validate a new session.

Cause and fix of `EPERM`: the agent's sandbox has the network off, and local Unix sockets are blocked
with it. For Codex turn the network on in the active permission profile
(`[permissions.<profile>.network] enabled = true`); an allow rule for the socket alone
(`network.unix_sockets`) is not enough (checked with Codex 0.167 on Linux). Restart the agent: a running
session keeps its old profile. `scripts/doctor.sh` checks `codex sandbox -- hc ls`. Have the person approve
the change; keep machine paths in ignored local config. Environment variables and an escalation request
are not proof of access: only the probe is.

A plain `codex` attaches to the shared app-server daemon when one runs. The daemon executes commands
with the environment of the terminal that started it: another project's `HC_TERMINAL_ID`, its sandbox,
its `PATH`; a nested `codex sandbox` then fails with `app-server socket directory must be a user-owned
directory with mode 0700`. `orch.py` and `doctor.sh` detect the daemon among parent processes and stop
with exit code 6. Fix: `[features] daemon_auto_start = false` in `~/.codex/config.toml`, stop the
daemon once, restart Codex; `codex --no-daemon` does the same for one session.

Codex owner commands write quota ledgers and locks to `~/.cache/herdr-orch` (`ORCH_CACHE_DIR`).
A profile that allows writes only in the workspace makes them fail with `Read-only file system`.
Allow writes to that folder (and to `~/.cache/herdr-agent-kit` for `tool-ask`) in the active profile
(`"~/.cache/herdr-orch" = "write"` under `[permissions.<profile>.filesystem]`). `doctor.sh` checks the
write from the current command tool and, outside Codex, through `codex sandbox`; inside a Codex session
it skips the nested `codex sandbox` checks.

Quota admission remains a separate check: `orch.py route execute` may refuse work after access is
repaired because predicted worker spend plus the new owner's shared-account reserve is too high.
Do not lower reserves as part of environment repair. Failed dispatch records must remain readable
by `status`; a task left without a worker is failed, not running or complete.

## 4. Recovery after a restart

- Owner session: `orch.py status` shows unfinished tasks; run `collect` for each.
- Machine or core reboot: herdr-core does not resume agents. A task with no live terminal and no
  report gets `incomplete` in `collect`; the worktree and branch stay for manual review.
- The hub restarts with `orch.py hub start` (the owner's session start does it). The hub exits on its own when the project folder is gone or no live terminal (App pane, owner, worker) works inside the project for `[watch] idle_exit_minutes` (60 by default, 0 disables).

## 5. Owner handoff

Reasons: the owner runs out of its vendor quota (`orch.py advice` suggests a switch when the remaining quota drops below `advice.owner_switch_percent`, 10% by default, and names the project agent with the `owner` capability and the largest remaining quota), or a human decision.

1. Safe boundary: tasks are collected or can keep running (the new owner collects them), review decisions are recorded.
2. The current owner runs `/gsd-pause-work`: GSD writes `.planning/HANDOFF.json` and `.continue-here.md` and commits them.
3. GSD for the new owner is installed with the official installer (`npx @opengsd/gsd-core@<pin> --<runtime> --local`); for Codex the guard block of `.codex/config.toml` is reviewed.
4. `orch.py owner set <agent> --launch` checks the `owner` capability and the freshness of `HANDOFF.json` (no older than `advice.handoff_max_age_minutes`), changes `owner` in `routing.toml` and GSD `runtime` in `config.json`, and starts the new owner as a tab in the space of the calling terminal (`--space project`: the project's space, see below). `--force` skips the check if the previous owner is unavailable.
   Without `--launch` the command only changes both files; the person then starts the new owner with a plain `claude` or `codex` in a project terminal, and its bootstrap does the rest. An agent started while it is not the owner only reports the current owner and changes nothing.
5. The new owner runs `orch.py hub start` (it restarts a hub whose configuration or code changed since its start), `/gsd-resume-work` and `orch.py status`; both configuration changes are committed with the handoff.

## 5.1. Owner context hygiene

Every owner request resends the whole context, so the request cost grows with the context size. `orch.py advice` and the Advice block in Mission Control report the owner context size (Claude: statusline via `statusline-tap`; Codex: session log) and suggest the agent's `compact_command` after `advice.compact_tokens` (100k by default) and `/gsd-pause-work` with `clear_command` after `advice.clear_tokens` (160k). A good point: no workers running or tasks just collected; mid-phase is fine at such a point. Compact and clear commands are set per runtime in `agents.toml`.

If the last low reading of the owner quota is stale but its window has not reset yet, Advice shows a conditional handoff hint. Confirm the current quota before `/gsd-pause-work`; automatic routing never uses the stale value. Click a command in Advice to copy it to the clipboard (Windows App). The restart button in the Mission Control header runs `orch.py hub restart` and refreshes the state publisher.

## 5.2. Template update

`.orchestration/template.toml` holds the project's template version and the repository address. Every `advice.update_check_hours` (24 h), at start and at a phase change, the hub compares it with the newest `vX.Y.Z` tag (`git ls-remote --tags`) and shows a hint when a newer release exists. `orch.py advice` checks the tag again as well. A human updates with `scripts/install-into-repo.sh` of the new release.

The ability to act as owner is confirmed by a test in the target runtime, not assumed.

## 6. External worktree resources

Copy `.orchestration/hooks/worktree-env.example` to `.orchestration/hooks/worktree-env`, make it executable
and configure isolation of databases, ports and caches. The hook runs after each worktree is created.

## 7. Dependency upgrades

Versions do not change only because a new release is out.

1. Edit `.orchestration/versions.env`.
2. Read the release notes of every component being upgraded.
3. `./scripts/version-check.py --strict`.
4. Reinstall GSD with the official installer.
5. `./scripts/reconcile-runtime-config.py`.
6. `./scripts/self-check.sh --offline`.
7. Worker smoke test through herdr-core: `orch.py dispatch` a `research` task, then `execute` in a worktree, `collect`, `worktree merge`.
8. Update `.orchestration/docs/COMPATIBILITY.md` and `REVIEW.md`.
