# Peer task

## Type
`review | code-review | execution | research | debug`

## Input
- Artifact paths: `<paths>`
- Git range: `<base>..<head>`
- Worktree: `<absolute path or n/a>`

## Goal
`<what must become true / what must be checked>`

## Allowed scope
- `<paths>`

## Forbidden
- Do not modify canonical `.planning/`.
- Do not broaden scope without stopping.
- Do not spawn child agents.
- Do not reopen accepted owner/human decisions unless evidence contradicts them.

## Context discipline
- Search/graph before broad reads.
- Read only relevant ranges.
- Do not reread unchanged files.
- Use this task contract; do not reload generic methodology docs unless a missing rule blocks work.
- Batch deterministic checks; keep successful output terse.
- On rereview inspect correction diff, not the whole project.

## Required checks
```bash
# project-specific commands
```

## Output
Write report to: `<report-path>`

Final line must be exactly one of:
`Result: complete`
`Result: incomplete`
`Major issue: yes`
`Major issue: no`
