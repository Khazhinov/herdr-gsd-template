# Herdr + GSD template

Пустой публичный orchestration-template для разработки по схеме **GSD + Herdr + Claude Code + Codex**.

В репозитории нет прикладного кода, бизнес-контекста и готового `.planning/`. Он предназначен для двух сценариев:

1. начать новый проект;
2. наложить orchestration layer на существующий Git-репозиторий.

**Claude Code** по умолчанию владеет GSD lifecycle и canonical `.planning/`.  
**Codex CLI** работает независимыми peer-процессами в Herdr: `peer-review`, `peer-code`, `peer-exec`.

> Репозиторий вырос из доклада **«Разработка (почти) непрерывного цикла с блэк-джеком и GSD»**.  
> Контекст выступления и анонс: [Мысли и байты — пост о конференции](https://t.me/thoughts_and_bytes/27).  
> Канал автора: [Мысли и байты](https://t.me/thoughts_and_bytes/).

## Используемые проекты

- [Open GSD / GSD Core](https://github.com/open-gsd/gsd-core) — project lifecycle, planning artifacts, execution and verification.
- [Herdr](https://github.com/herdrdev/herdr) — agent-aware terminal/process runtime and automation.
- [Claude Code](https://github.com/anthropics/claude-code) — default owner/orchestrator.
- [OpenAI Codex](https://github.com/openai/codex) — independent peer review and execution runtime.

Этот template не является частью этих проектов и не аффилирован с их разработчиками.

## Проверенный compatibility baseline

Проверено **2026-10-16**:

| Component | Baseline |
|---|---:|
| GSD Core | `1.17.0` pinned by bootstrap |
| Herdr | `>= 0.9.3` |
| Claude Code | `>= 2.1.301` |
| Codex CLI | `>= 0.163.0` |
| Node.js | `>= 24` |
| npm | `>= 10` |
| Python | `>= 3.10` |

GSD устанавливается официальным runtime-specific installer'ом, а не копированием его generated commands/skills.

Проверить локальное окружение:

```bash
./scripts/version-check.py --strict
./scripts/doctor.sh
```

## Архитектура

```text
Human
  |
  v
Claude owner / GSD
  |
  +-- peer-review ---- Codex: CONTEXT / architecture / PLAN review
  +-- peer-code ------ Codex: diff / code review
  `-- peer-exec ------ Codex: bounded implementation in worktree
                            |
                            v
                       commits + checks
                            |
                            v
                    durable peer report
                            |
                            v
                    Claude owner / merge
                            |
                            v
                GSD verifier / human gate
```

Границы ответственности:

- **GSD** — project lifecycle и durable planning artifacts;
- **Herdr** — реальные CLI-процессы, panes и lifecycle signals;
- **custom protocol** — single-writer state, task contracts, report/sentinel completion, quota routing, worktree lifecycle;
- **Git/CI** — implementation evidence и deterministic checks.

## Инварианты

- Durable state = GSD artifacts + peer reports + Git, не chat history.
- Canonical `.planning/` меняет только runtime из `.orchestration/owner.env`.
- GSD `runtime`/model settings не являются нашим lock/ownership mechanism.
- Herdr `working/idle/done/blocked/unknown` — scheduler signal, не доказательство task success.
- Peer completion = report + exact sentinel + expected commits/checks.
- Codex peer не запускает GSD orchestration и не создаёт собственный swarm.
- Worktree изолирует Git/filesystem, но не БД, порты, cache, queues и внешние API.
- Перед каждой независимой peer task очищается Codex chat context.
- Перед удалением worktree `peer-exec` возвращается в repository root.
- Heavy Codex task стартует только после best-effort оценки доступного лимита.
- При сомнении в независимости двух writers — выполнять последовательно.

## Новый проект

Пока репозиторий не отмечен на GitHub как **Template repository**, можно клонировать его и заменить remote:

```bash
git clone https://github.com/Khazhinov/herdr-gsd-template.git my-project
cd my-project

git remote remove origin
git remote add origin <your-repository-url>

./scripts/bootstrap.sh
```

После этого:

```bash
herdr
```

В **первом/root pane**:

```bash
claude
```

Первый prompt Claude:

```text
Initialize this repository according to .claude/CLAUDE.md.
Verify versions, ensure Codex peer-review/peer-code/peer-exec exist,
show peer states and Codex quota estimate, then stop and wait for my GSD command.
```

Claude сам создаст дочерние Herdr panes через:

```bash
./scripts/herdr-ensure-peers.sh
```

Далее в Claude:

```text
/gsd-new-project
```

После появления `.planning/config.json`:

```bash
./scripts/apply-gsd-policy.py
```

С этого момента Codex уже участвует в обязательных review/execution gates.

## Добавить orchestration в существующий repository

Клонировать template во временный каталог:

```bash
git clone https://github.com/Khazhinov/herdr-gsd-template.git /tmp/herdr-gsd-template
/tmp/herdr-gsd-template/scripts/install-into-repo.sh /path/to/existing/repo
```

Затем:

```bash
cd /path/to/existing/repo
./scripts/bootstrap.sh
```

Installer **не перезаписывает молча** существующие:
- `AGENTS.md`;
- `.claude/CLAUDE.md`;
- `.codex/config.toml`;
- одноимённые orchestration scripts.

Конфликтующие starter-варианты складываются в:

```text
.orchestration/merge-required/
```

`bootstrap.sh` **fail-closed** и не продолжит установку, пока там остаются файлы.
Вручную перенесите нужные фрагменты в project-owned файлы, удалите разобранные
merge-required copies, затем запускайте bootstrap.

После разрешения конфликтов:

```bash
herdr
# first/root pane:
claude
```

Для существующего codebase:

```text
/gsd-onboard
```

После создания `.planning/config.json`:

```bash
./scripts/apply-gsd-policy.py
```

## GSD policy

Template не пытается использовать все GSD gates одновременно.

Sanitized policy:

```json
{
  "runtime": "claude",
  "mode": "interactive",
  "model_profile": "adaptive",
  "parallelization": true,
  "planning": {"commit_docs": true},
  "workflow": {
    "research": false,
    "plan_check": false,
    "verifier": true,
    "code_review": false,
    "node_repair_budget": 1,
    "context_guard_mode": "warn",
    "use_worktrees": true,
    "compact_content": true
  }
}
```

Почему:

- automatic phase research выключен — research вызывается по необходимости;
- GSD plan checker заменён независимым `peer-review`;
- GSD code review заменён `peer-code`;
- GSD verifier остаётся: он проверяет достижение goal/requirements, а не качество diff;
- worktree isolation остаётся;
- auto-repair loop ограничен;
- planning artifacts коммитятся для session recovery и immutable-ish review ranges.

Это **case-derived policy**, а не универсальная рекомендация.

## Herdr topology

Пользователь вручную создаёт только первый tab/root pane и запускает owner.

Дальше owner создаёт child panes:

```text
owner (Claude)
  +-- peer-review (Codex)
  +-- peer-code   (Codex)
  `-- peer-exec   (Codex)
```

Используется agent API Herdr:

```text
pane split
agent start
agent get
agent prompt
agent wait
agent read
```

Обычная task submission не использует raw `pane send-text + Enter`.

## Fresh context

Перед каждой независимой peer task:

```bash
./scripts/peer-reset.sh peer-review
```

Reset отправляет текущую Codex slash command:

```text
/clear
```

Это начинает fresh chat, **не меняя cwd**.

Если нужно переместить worker в worktree, выполняется controlled process restart:

```bash
./scripts/peer-restart-in.sh peer-exec /path/to/worktree
```

Context reset и cwd relocation намеренно разделены.

## Task contract и communication protocol

Скопировать шаблон:

```bash
cp .orchestration/templates/peer-task.md /tmp/task.md
```

Task должен содержать:
- artifact paths;
- Git range;
- goal;
- allowed write scope;
- forbidden scope;
- required checks;
- output report path;
- exact completion sentinel;
- deviation policy.

Dispatch:

```bash
./scripts/peer-dispatch.sh peer-review /tmp/task.md
./scripts/peer-watch.sh peer-review docs/peer/<report>.md
```

Herdr state не используется как business completion.

Логическая task считается завершённой только когда есть:

```text
report exists
AND expected sentinel exists
AND expected commits/scope exist
AND required checks pass
```

## Codex peer guard

Project-local `.codex/config.toml` по умолчанию отключает native Codex fan-out:

```toml
[agents]
enabled = false
max_concurrent_threads_per_session = 1
max_depth = 0

[features.multi_agent_v2]
enabled = false
max_concurrent_threads_per_session = 1
```

Это сознательно: concurrency контролируется Claude + Herdr.

Если Codex переводится в owner-role, это отдельный migration:
1. закончить текущую owner-операцию на committed safe boundary;
2. установить GSD для Codex официальным `--codex --local` installer;
3. пересмотреть peer-lockdown в `.codex/config.toml`;
4. изменить `.orchestration/owner.env`;
5. только после этого стартовать новый owner session.

Не устанавливайте GSD в Codex «на всякий случай» в стандартном peer-only режиме.

## Monitoring

Статус:

```bash
./scripts/peer-status.sh
```

Долгий watch:

```bash
./scripts/peer-watch.sh peer-exec docs/peer/<report>.md
```

По умолчанию:

- report/lifecycle poll: 15 секунд;
- quota refresh: 10 минут;
- `blocked` → остановка и вмешательство owner/human;
- `idle/done` без report после grace window → protocol violation;
- `unknown` не считается успешным завершением.

Никаких auto-approval security dialogs.

## Codex limits

Замысел routing простой: **пока у Codex есть комфортный остаток лимита, тяжёлое исполнение по возможности отдаётся `peer-exec`, а Claude сохраняется как owner/orchestrator и резервный executor. Когда доступный лимит Codex подходит к заданному порогу, новые тяжёлые задачи остаются у Claude, а Codex используется для коротких review/fix/research задач. Уже начатая задача не прерывается — переключение происходит только между durable tasks.**

```bash
./scripts/codex-limits.py --threshold 30
./scripts/codex-limits.py --json
```

Это **best-effort parser локальной Codex rollout telemetry**, не официальный billing/quota API.

Если доступны primary и secondary windows, scheduler использует более ограничивающий остаток.

Policy:

- effective remaining > threshold → heavy Codex execution разрешён;
- <= threshold → только short review/research/fix;
- telemetry unavailable → automatic heavy routing disabled;
- уже начатую task не мигрировать;
- switching происходит только между durable tasks.

## Worktree lifecycle

```bash
wt=$(./scripts/peer-worktree.sh create 02-03)
./scripts/peer-worktree.sh enter 02-03

# dispatch peer-exec task with $wt

./scripts/peer-worktree.sh merge 02-03
```

`merge`:

1. убеждается, что peer worktree clean;
2. **возвращает `peer-exec` в repository root**;
3. делает merge;
4. удаляет worktree;
5. делает prune;
6. ещё раз подтверждает root invariant.

Так worker никогда не остаётся с cwd уже удалённого worktree.

Для БД/портов/cache используйте:

```text
.orchestration/hooks/worktree-env
```

Пример есть в `worktree-env.example`.

## Optimization stack

Одинаково обязателен для Claude и Codex:

- semantic/code graph MCP, если подключён;
- `rg`/`git grep` до широкого чтения;
- targeted ranges;
- paths/headings/commit ranges вместо копирования больших документов;
- no reread unchanged files;
- diff-only rereview;
- deterministic checks пакетно через shell/CI;
- тихий happy path и только нужный failure tail;
- binary decisions не отдавать reasoning model;
- large logs хранить artifact'ами, не в conversational context;
- fresh bounded peer chats;
- expensive reasoning для решений, workhorse execution для bounded implementation.

Полные правила:

```text
.agents/skills/gsd-context-discipline/SKILL.md
```

`.mcp.example.json` — placeholder для repository graph/search MCP.

## Security defaults

Public template намеренно **не** включает:

- `danger-full-access`;
- `approval_policy = "never"`;
- auto-confirm permission/security dialogs.

Расширяйте permissions только осознанно и локально.

## Проверки

В репозитории есть GitHub Actions workflow `.github/workflows/template-self-check.yml`.
Он не использует Claude/OpenAI credentials: один job прогоняет offline/mocked regression suite, второй под Node 24 ставит pinned GSD официальным installer'ом и проверяет reconcile.

Полный offline suite:

```bash
./scripts/test-template.sh
```

Только static/protocol:

```bash
./scripts/self-check.sh --offline
```

Local environment:

```bash
./scripts/doctor.sh
```

Подробности:
- `.orchestration/docs/ARCHITECTURE.md`
- `.orchestration/docs/OPERATIONS.md`
- `.orchestration/docs/COMPATIBILITY.md`
- `.orchestration/docs/REVIEW.md`
- `.orchestration/docs/SOURCES.md`

## Обновление зависимостей

Не меняйте версии только потому, что появился новый релиз.

Порядок:

1. обновить `.orchestration/versions.env`;
2. проверить release notes;
3. `./scripts/version-check.py --strict`;
4. переустановить GSD official installer'ом;
5. `./scripts/reconcile-runtime-config.py`;
6. `./scripts/self-check.sh --offline`;
7. прогнать authenticated Herdr smoke test;
8. прогнать worktree lifecycle;
9. обновить `COMPATIBILITY.md` и `REVIEW.md`.

## License

MIT. См. [LICENSE](LICENSE).
