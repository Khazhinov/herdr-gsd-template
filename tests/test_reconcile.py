#!/usr/bin/env python3
import shutil, subprocess, tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "repo"
    shutil.copytree(source, root)
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

with tempfile.TemporaryDirectory() as td:
    root = Path(td) / "repo"
    shutil.copytree(source, root)
    (root / ".codex/config.toml").write_text('[agents]\nmax_concurrent_threads_per_session = 7\n')
    q = subprocess.run(
        [str(root / "scripts/reconcile-runtime-config.py")],
        cwd=root, capture_output=True, text=True
    )
    assert q.returncode == 3
    assert "starter marker block is missing" in q.stderr

print("reconcile test: PASS")
