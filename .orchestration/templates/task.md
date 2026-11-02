# Task <id>: <one-line goal>

## Type
`execute | review | research | debug | plan`

## Input
- Artifacts: `<paths, requirement ids, plan file>`
- Git range (reviews): `<base>..<head>`

## Goal
<what must become true, or what must be checked>

## Allowed scope
- `<paths the worker may change>`

## Forbidden
- Do not reopen accepted owner/human decisions unless evidence contradicts them.
- Do not broaden scope; stop with `Result: incomplete` when a decision is missing.

## Context discipline
- Search (graph/semantic/rg) before broad reads; read targeted ranges only.
- Do not reread unchanged files. On rereview inspect the correction diff only.
- Batch deterministic checks; keep successful output terse.

## Quota discipline
Every tool call resends the whole session context, so the number of calls, not
the output size, drives quota spend.
- Run a long command (full test suite, type check, build) as one call with the
  longest allowed wait (Codex: maximum `yield_time_ms`, then `wait` on the same
  session with the maximum timeout, at most 10 times; Claude: one Bash call with
  a long timeout). Never poll it with `ps`, `pgrep`, `tail` of its log or `sleep`.
- Send long output to a log outside the worktree; print only the summary line,
  or `tail -40` on failure. Keep `max_output_tokens` at 4000 or less.
- Read skills and docs by section, not whole files.

## Required checks
```bash
# project-specific commands
```

<!-- orch.py appends the protocol: cwd, report path, sentinel, no .planning writes. -->
