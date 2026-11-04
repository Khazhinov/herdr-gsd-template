# Architecture v0.2

English | [Русский](ARCHITECTURE.ru.md)

## 1. Layers and responsibilities

| Layer | Responsibility | Does not |
|---|---|---|
| GSD Core | project lifecycle, `.planning/`, verifier, `planning.inspect` | pick a provider or track quotas |
| `scripts/orch.py` (scheduler) | agent registry, quotas, routing, task contract, worktrees, evidence | keep project state outside files and Git |
| herdr-core (`hc`) | processes in long-lived terminals, parent-child links, OSC 7501, events, documents, machines | judge task success |
| Herdr App | interface: spaces, worker tabs, Mission Control | hold routing business logic |
| Git | execution evidence | - |

## 2. Scheduler components

| Module | Purpose |
|---|---|
| `orchlib/config.py` | loads and validates `agents.toml`, `routing.toml` and the local `*.local.toml` overrides |
| `orchlib/quota.py` | normalized quotas: Codex RPC, Codex logs, Claude statusline snapshot, static budget, `unknown`; one shared cache per account (`~/.cache/herdr-orch/quotas.json`) |
| `orchlib/route.py` | pure deterministic selection function with a reason; contains no agent identifiers |
| `orchlib/tasks.py` | starts a worker with `hc run`, task protocol, worktree, evidence check, `collect` |
| `orchlib/state.py` | dashboard snapshot: routes, quotas, tasks, tool agents, `planning.inspect` |
| `orchlib/hc.py` | `hc` CLI calls and JSON-RPC over `hc connect` |

Routing first reads the raw account quota from the shared `quotas.json`, then applies the project's
`quota_windows`. For each selected window the projection is the remaining percent minus the expected
spend of active tasks from the shared `ledger.json` minus the estimate for the new task. Admission under
`admission.lock` records the task as `starting` before the terminal starts. The agent's `max_parallel`
and the optional `[accounts.<account>] max_parallel` are checked under the same lock. Spend samples are
stored per account, weight and window; the estimate is the median of the last five solo tasks.

A worker on the owner's account adds `owner_reserve_percent` to the threshold. For a review,
`dispatch --of <id>` excludes the author's account; picking that account manually gives
`independent: false`. A window that has reset with no new reading stays unknown.

## 3. Task lifecycle

```text
route(role, weight) -> decision + reason -> runtime/decisions.jsonl
  -> execute: git worktree .orchestration/worktrees/<id>, branch orch/<id>
  -> contract runtime/tasks/<id>.md = owner's task + protocol
  -> hc run --bg --name w-<id> --cwd <dir> --label orch.* [--outlive-parent] -- env PATH=... <agent argv> "<prompt>"
  -> herdr.space label: the owner's space or the project's ([workers] space), created when missing
  -> startup_check: the agent reported an OSC 7501 status, otherwise diagnostics (trust dialog, login)
  -> the worker writes a report; the host learns about the event with hc wait --children
  -> collect: report marker, .planning/ check, terminal stop, commit of worktree changes, report copy, ledger entry removal
  -> merge: task and conflict checks before the worktree is removed, refusal if .planning/ changed
```

The worker does not commit: the Codex sandbox protects `.git` even with `--add-dir`, and calling `hc send`
from the sandbox needs approval (the core socket is outside the writable paths). So completion is detected
with `hc wait` and the report, and the owner commits in `collect`.

## 4. Worker environment

herdr-core starts programs with the core's environment, not the calling terminal's. When Herdr App starts
the core over SSH, it usually has no `~/.local/bin` and no proxy. So the worker argv starts with `env` and the
variables from `[workers] pass_env`.

Worktrees live inside the repository by default (`.orchestration/worktrees/`): Claude inherits folder trust
from the project root. Codex trusts by Git root, so a worktree gets
`-c projects."<worktree>".trust_level="trusted"`. Trusting the project root itself stays a human decision.

## 5. State publishing

`orch.py watch` (started by `orch.py hub start` in its own hc terminal) rebuilds the snapshot on every
significant core event (`events.subscribe`) and on the quota timer. The snapshot is published:

- to the file `.orchestration/runtime/state.json`;
- to the core document `orch-<project>` (`doc.set`, a `doc` event for subscribers);
- to the hub terminal labels: `orch.rev`, `orch.q.<agent>`, `orch.route.<role>`.

The Herdr App mod redraws when the labels change, then reads the file from the hub's machine (`readTextFile {on}`).
The mod takes worker statuses straight from `terminals()`.

## 6. Remote machines

The scheduler runs on the owner's machine. Herdr App connects it as an SSH machine; terminal addresses
in the App get the machine prefix (`herdr-wsl/t7`), and the mod accounts for it when it focuses or stops a worker.
Starting workers on other machines (`hc run --on`) is not implemented in v0.2.
