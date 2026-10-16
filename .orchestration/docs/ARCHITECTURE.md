# Architecture

| Layer | Owns | Does not own |
|---|---|---|
| Human | product/architecture/destructive/release authority | mechanical execution |
| Claude/GSD owner | lifecycle, canonical `.planning/`, decisions, integration | external process lifecycle |
| Herdr | native process topology and lifecycle signals | project task semantics |
| Codex peers | independent review / bounded execution | canonical planning state |
| Git/CI | implementation evidence and deterministic checks | product decisions |

## Ownership

Canonical planning ownership lives in `.orchestration/owner.env`.

This is intentionally separate from GSD's `runtime` and model selection settings:
those settings configure GSD execution, while our marker controls the single-writer protocol.

## Control path

```text
human
  -> Claude owner
      -> GSD artifact
      -> Codex peer via Herdr
          -> report / commit evidence
      -> owner decision / merge
      -> GSD verifier / human gate
```

## Completion

Herdr lifecycle answers: "what appears to be happening in this terminal process?"

The project protocol answers: "did this work item complete correctly?"

The latter requires durable evidence:
- report path;
- exact sentinel;
- expected commit/scope;
- required checks.

## Isolation

Git worktrees isolate working trees and branches only.

Parallel project execution also needs explicit isolation for shared resources:
- DB/schema;
- ports;
- caches;
- queues/topics;
- test buckets/directories;
- external rate-limited APIs.

Use `.orchestration/hooks/worktree-env`.

## Context boundary

Peer chats are disposable.
`/clear` starts a fresh peer chat between independent tasks.
Owner session handoff only happens on a durable safe boundary.
