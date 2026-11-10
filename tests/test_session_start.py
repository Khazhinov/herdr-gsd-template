import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('session_start', ROOT / 'scripts/session-start.py')
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


class SessionStartup(unittest.TestCase):
    def test_worker_does_not_start_owner_hub(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(startup.subprocess, 'run') as run:
            root = Path(temp)
            result = startup.start(root, root / 'service-worktree')
            self.assertEqual(result['status'], 'skipped')
            run.assert_not_called()

    def test_start_uses_existing_idempotent_hub_command(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = subprocess.CompletedProcess([], 0, 'hub already running', '')
            with patch.object(startup.subprocess, 'run', return_value=result) as run:
                self.assertEqual(startup.start(root, root)['status'], 'ready')
            self.assertEqual(run.call_args.args[0][-2:], ['hub', 'start'])
            self.assertEqual(json.loads((root / '.orchestration/runtime/session-start.json').read_text())['status'], 'ready')

    def test_reconcile_preserves_hooks_mcp_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('scripts', '.orchestration', '.codex', '.claude'):
                (root / name).mkdir()
            shutil.copy2(ROOT / 'scripts/reconcile-runtime-config.py', root / 'scripts/reconcile-runtime-config.py')
            shutil.copy2(ROOT / '.orchestration/claude-owner-block.md', root / '.orchestration/claude-owner-block.md')
            (root / '.codex/config.toml').write_text(
                '[features]\nhooks = true\ndaemon_auto_start = true\n'
                '[mcp_servers.example]\ncommand = "example"\n'
                '# GSD-HERDR-PEER-CONFIG:BEGIN\n[agents]\nenabled = false\n'
                '# GSD-HERDR-PEER-CONFIG:END\n')
            existing = {'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'existing-hook'}]}]}}
            (root / '.codex/hooks.json').write_text(json.dumps(existing))
            (root / '.claude/settings.json').write_text(json.dumps(existing))
            snapshots = []
            for _ in range(2):
                subprocess.run([sys.executable, str(root / 'scripts/reconcile-runtime-config.py')], check=True, capture_output=True)
                snapshots.append([(root / p).read_text() for p in ('.codex/config.toml', '.codex/hooks.json', '.claude/settings.json')])
            self.assertEqual(*snapshots)
            self.assertIn('daemon_auto_start = false', snapshots[0][0])
            self.assertIn('[mcp_servers.example]', snapshots[0][0])
            for text in snapshots[0][1:]:
                self.assertIn('existing-hook', text)
                self.assertEqual(text.count('scripts/session-start.py'), 1)


if __name__ == '__main__':
    unittest.main()
