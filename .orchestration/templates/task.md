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

## Required checks
```bash
# project-specific commands
```

<!-- orch.py appends the protocol: cwd, report path, sentinel, no .planning writes. -->
