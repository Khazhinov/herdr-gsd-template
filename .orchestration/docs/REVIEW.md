# Review and verification in v0.2

English | [Русский](REVIEW.ru.md)

## 1. Profiles

| Profile | CONTEXT and PLAN review | Code review | Verification |
|---|---|---|---|
| lean (default) | independent worker `orch.py dispatch --role review` | independent worker on the branch diff | GSD verifier |
| strict | the same + `/gsd-plan-review-convergence` | worker + `/gsd-review` with `review.default_reviewers` | GSD verifier + human |

## 2. Why the built-in GSD lanes are not the main path

GSD 1.19 supports reviewer lanes (`codex`, `claude`, `kimi-code`, `opencode` and others) and
`review.reviewer_instances`. A lane calls a CLI once and knows nothing about quotas and reserves. The scheduler
picks a reviewer with quotas and independence in mind and records the reason. So the GSD lanes are kept
for the strict profile as a confirmation, not as the main path.

## 3. Independence

The `review` role has `independent = true`: the owner is picked only when no other suitable agent exists,
and the decision is marked `independent: false`. The owner records such a review as an unmet independence condition.

## 4. Cycle

One independent review, one owner fix, a repeat review only of the changed areas.
Before the repeat review the worker gets the previous findings and the fix diff, not the whole context.
