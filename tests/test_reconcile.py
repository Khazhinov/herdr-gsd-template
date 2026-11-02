#!/usr/bin/env python3
import json, shutil, subprocess, tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
IGNORE = shutil.ignore_patterns('.git', 'runtime', 'worktrees', '__pycache__')

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "repo"
    shutil.copytree(source, root, ignore=IGNORE)
    (root / ".claude/CLAUDE.md").write_text("# GSD generated content\n")

    # A manually merged config has the starter marker plus unrelated settings.
    (root / ".codex/config.toml").write_text(
        '[features]\nhooks = true\nfoo = "bar"\n\n'
        '# GSD-HERDR-PEER-CONFIG:BEGIN\n'
        '[agents]\nenabled = true\nmax_concurrent_threads_per_session = 99\nmax_depth = 9\n\n'
        '[features.multi_agent_v2]\nenabled = true\nmax_concurrent_threads_per_session = 99\n'
        '# GSD-HERDR-PEER-CONFIG:END\n'
    )

    cmd = [str(root / "scripts/reconcile-runtime-config.py")]
    subprocess.run(cmd, cwd=root, check=True, capture_output=True, text=True)
    first_claude = (root / ".claude/CLAUDE.md").read_text()
    first_codex = (root / ".codex/config.toml").read_text()

    subprocess.run(cmd, cwd=root, check=True, capture_output=True, text=True)
    assert (root / ".claude/CLAUDE.md").read_text() == first_claude
    assert (root / ".codex/config.toml").read_text() == first_codex
    assert first_claude.count("GSD-HERDR-STARTER:BEGIN") == 1
    assert first_codex.count("GSD-HERDR-PEER-CONFIG:BEGIN") == 1
    assert 'foo = "bar"' in first_codex
    assert "enabled = false" in first_codex
    assert "max_concurrent_threads_per_session = 1" in first_codex
    sl = json.loads((root / ".claude/settings.json").read_text())["statusLine"]["command"]
    assert sl.count("statusline-tap") == 1 and " -- " not in sl, sl

# An existing project statusline is chained after the tap, once.
with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "repo"
    shutil.copytree(source, root, ignore=IGNORE)
    (root / ".claude/settings.json").write_text(json.dumps({"hooks": {"x": 1}, "statusLine": {"type": "command", "command": "node gsd-statusline.js"}}))
    for _ in range(2):
        subprocess.run([str(root / "scripts/reconcile-runtime-config.py")], cwd=root, check=True, capture_output=True)
    data = json.loads((root / ".claude/settings.json").read_text())
    assert data["hooks"] == {"x": 1}
    assert data["statusLine"]["command"].endswith("statusline-tap -- 'node gsd-statusline.js'"), data

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "repo"
    shutil.copytree(source, root, ignore=IGNORE)
    (root / ".codex/config.toml").write_text('[agents]\nmax_concurrent_threads_per_session = 7\n')
    q = subprocess.run(
        [str(root / "scripts/reconcile-runtime-config.py")],
        cwd=root, capture_output=True, text=True
    )
    assert q.returncode == 3
    assert "starter marker block is missing" in q.stderr

print("reconcile test: PASS")
