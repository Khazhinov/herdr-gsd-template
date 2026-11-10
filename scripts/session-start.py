#!/usr/bin/env python3
"""Restore project startup without requiring CLI arguments or a bootstrap prompt."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = (
    'Follow root AGENTS.md and restore .planning/STATE.md automatically. '
    'Act on the user request using the project workflow without requiring a '
    'bootstrap prompt. Only the declared owner writes canonical planning.'
)


def start(root=ROOT, cwd=None):
    # A worker in a nested repository/worktree must not bootstrap as an owner.
    if Path(cwd or Path.cwd()).resolve() != root.resolve():
        return {'status': 'skipped', 'reason': 'not the workspace root'}
    report = {'status': 'unavailable'}
    try:
        result = subprocess.run(
            [sys.executable, str(root / 'scripts/orch.py'), 'hub', 'start'],
            cwd=root, text=True, capture_output=True, timeout=35,
        )
        report = {
            'status': 'ready' if result.returncode == 0 else 'unavailable',
            'exit_code': result.returncode,
            'detail': (result.stdout + result.stderr).strip()[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        report['detail'] = str(error)
    target = root / '.orchestration/runtime/session-start.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hook', action='store_true')
    args = parser.parse_args()
    payload = {}
    if args.hook:
        try:
            payload = json.load(sys.stdin)
        except (ValueError, OSError):
            pass
    report = start(cwd=payload.get('cwd'))
    if args.hook:
        context = CONTEXT + f" SessionStart has already attempted owner startup: {report['status']}."
        if report['status'] == 'unavailable':
            context += ' Herdr startup needs attention; inspect .orchestration/runtime/session-start.json.'
        if report['status'] != 'skipped':
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': context}}))
    else:
        print(json.dumps(report, ensure_ascii=False))
    # A disconnected Herdr must not prevent the agent from accepting a task.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
