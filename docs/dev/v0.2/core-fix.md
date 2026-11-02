# core-fix

Реализованы исправления маршрутизации, квот и жизненного цикла из ревью v0.2.

| Пункт | Закрытые замечания | Файлы | Проверка |
|---|---|---|---|
| 1. Общий ledger и атомарный допуск | R1, R4, C1, C6, C13, C14, C15 | `scripts/orchlib/tasks.py`, `scripts/orchlib/route.py` | `test_account_ledger_serializes_concurrent_admission`, `test_launch_failure_cleans_ledger_worktree_and_marks_failed`, `test_ledger_prunes_missing_and_old_terminals` |
| 2. Исходный кэш по учётной записи | C5 | `scripts/orchlib/quota.py` | `test_raw_cache_is_shared_but_gating_is_project_local` |
| 3. Расход и прогноз по окнам | R2, C2, C3 | `scripts/orchlib/tasks.py`, `scripts/orchlib/route.py`, `.orchestration/routing.toml` | `test_each_window_and_account_cap`, `test_pending_uses_earliest_account_start_once`, `test_window_burn_survives_other_window_reset_and_solo_median` |
| 4. Резерв владельца | C7 | `scripts/orchlib/route.py`, `scripts/orchlib/config.py`, `.orchestration/routing.toml` | `test_owner_reserve_and_author_account` |
| 5. Запрет провайдера и устаревшая квота | R3, C11, C12 | `scripts/orchlib/quota.py`, `scripts/orchlib/route.py` | `test_vendor_denial_and_static_reset`, `test_stale_low_light_is_denied` |
| 6. Сброс окна, RPC и период статического бюджета | R8, R9, C16, C18 | `scripts/orchlib/quota.py`, `scripts/orchlib/hc.py`, `scripts/orchlib/config.py` | `test_codex_rollout_fallback_and_reset_window`, `test_rpc_multiple_lines_in_one_read`, `test_rpc_constructor_closes_failed_process`, `test_account_cap_and_static_period_validate` |
| 7. Сбор, защита `.planning/` и предварительная проверка merge | R5, R6, R7, C8, C9, C19 | `scripts/orchlib/tasks.py`, `scripts/orch.py` | `test_collect_keep_worker_never_commits_and_planning_is_guarded`, `test_merge_preflight_rejects_conflicts_and_branch_planning`, `test_replace_archives_collected_task_and_review_of_author` |
| 8. Независимое ревью от автора | C4 | `scripts/orchlib/tasks.py`, `scripts/orchlib/route.py`, `scripts/orch.py` | `test_owner_reserve_and_author_account`, `test_replace_archives_collected_task_and_review_of_author` |
| 9. Shell исправления | R11, C20 | `scripts/self-check.sh`, `scripts/install-into-repo.sh` | `test_self_check_preserves_pycache_and_installer_accepts_worktree` |

Документация обновлена в `.orchestration/docs/DECISIONS.md`, `.orchestration/docs/ARCHITECTURE.md` и `CHANGELOG.md`.

Проверки: `./scripts/test-template.sh` прошёл, 53 теста; `git diff --check` прошёл.

Отклонение: `collect --keep-worker` оставляет задачу в состоянии `running` и запись в ledger, чтобы работающий терминал продолжал учитываться при допуске. Коммит выполняется только при обычном `collect` после остановки терминала.

Открытые вопросы: нет.

Result: complete
