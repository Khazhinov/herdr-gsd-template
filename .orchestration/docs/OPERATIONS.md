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
| `orch.py owner set <agent> [--launch] [--force]` | owner handoff (section 5) |

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

A `blocked` status during work means a permission request. It is visible in the App, the dashboard and the `orch.py wait` output.

## 4. Recovery after a restart

- Owner session: `orch.py status` shows unfinished tasks; run `collect` for each.
- Machine or core reboot: herdr-core does not resume agents. A task with no live terminal and no
  report gets `incomplete` in `collect`; the worktree and branch stay for manual review.
- The hub restarts with `orch.py hub start`.

## 5. Owner handoff

Reasons: the owner runs out of its vendor quota (`orch.py advice` suggests a switch when the remaining quota drops below `advice.owner_switch_percent`, 10% by default, and names the project agent with the `owner` capability and the largest remaining quota), or a human decision.

1. Safe boundary: tasks are collected or can keep running (the new owner collects them), review decisions are recorded.
2. The current owner runs `/gsd-pause-work`: GSD writes `.planning/HANDOFF.json` and `.continue-here.md` and commits them.
3. GSD for the new owner is installed with the official installer (`npx @opengsd/gsd-core@<pin> --<runtime> --local`); for Codex the guard block of `.codex/config.toml` is reviewed.
4. `orch.py owner set <agent> --launch` checks the `owner` capability and the freshness of `HANDOFF.json` (no older than `advice.handoff_max_age_minutes`), changes `owner` in `routing.toml` and starts the new owner as a tab in the space of the calling terminal. `--force` skips the check if the previous owner is unavailable.
5. The new owner runs `/gsd-resume-work` and `orch.py status`; the `routing.toml` change is committed with the handoff.

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
