# Compatibility - 2026-11-02

English | [Русский](COMPATIBILITY.ru.md)

| Component | Version tested | Template requirement | Note |
|---|---|---|---|
| GSD Core | 1.19.0 | pin `1.19.0` | installer `--claude --local`; overlay keys are checked by a test |
| herdr-core | 0.1.16 | `>= 0.1.16` | `hc run/wait/get/ls/label/kill/rm/connect`, documents, events |
| Herdr App | 0.1.11 (Windows) | optional | Mission Control mod and layout; core in WSL as an SSH machine |
| Claude Code | 2.1.316 | `>= 2.1.316` | statusline `rate_limits`, folder trust inheritance |
| Codex CLI | 0.165.0 | `>= 0.165.0` | `--no-daemon`, `app-server` quota RPC, `-c projects.<path>.trust_level` |
| Node.js | 22.22.0 (test environment) | `>= 24` (GSD requirement) | GSD 1.19 runs on 22 with no runtime engine check; the upstream requirement is kept |
| Python | 3.12.3 | `>= 3.11` | `tomllib`, `datetime.UTC` |
| Kimi Code | installed in `~/.kimi-code/bin`, subscription not paid | `candidate` | TUI without an initial prompt (`prompt = "send"`); smoke test not run |
| OpenCode | 1.19.5 | `candidate` | `--prompt` for the initial prompt; worker smoke test passed on `opencode/deepseek-v4.1-flash-free`; herdr-core status needs the plugin `.orchestration/adapters/opencode/herdr-core-status.js` (OSC 7501), the stock herdr plugin talks to the socket of the legacy Herdr TUI |
| ZCode | not installed | `experimental` | adapter described, smoke test not run |

## Paths

| Path | State |
|---|---|
| Windows Herdr App -> WSL2 (SSH machine) | verified: PoC, workers, mod, layout |
| Linux without the App | partly verified: `orch.py watch` as a terminal dashboard, offline tests |
| macOS | not verified |
