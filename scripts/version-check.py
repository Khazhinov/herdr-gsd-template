#!/usr/bin/env python3
import argparse
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_file(path):
    out = {}
    for raw in path.read_text().splitlines() if path.exists() else []:
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        m = re.fullmatch(r"\$\{[^:}]+:-([^}]+)\}", v.strip())
        out[k.strip()] = (m.group(1) if m else v.strip()).strip('"')
    return out


def ver_tuple(s):
    m = re.search(r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)", s or "")
    return tuple(map(int, m.groups())) if m else None


def run(cmd):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (p.stdout + "\n" + p.stderr).strip()


def check(name, command, minimum, required=True):
    if not shutil.which(command[0]):
        print(f"{name}: MISSING (need >= {minimum}){'' if required else ' optional'}")
        return not required
    got, want = ver_tuple(run(command)), ver_tuple(minimum)
    ok = bool(got and want and got >= want)
    print(
        f"{name}: {'.'.join(map(str, got)) if got else 'unknown'} (baseline >= {minimum}) "
        f"{'OK' if ok else 'CHECK'}"
    )
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail below the verified baseline")
    ns = ap.parse_args()
    e = env_file(ROOT / ".orchestration/versions.env")
    ok = True
    ok &= check("Python", ["python3", "--version"], e.get("PYTHON_MIN_VERSION", "3.11.0"))
    ok &= check("Node.js", ["node", "--version"], f"{e.get('NODE_MIN_MAJOR', '24')}.0.0")
    ok &= check("npm", ["npm", "--version"], f"{e.get('NPM_MIN_MAJOR', '10')}.0.0")
    ok &= check("herdr-core (hc)", ["hc", "--version"], e.get("HC_MIN_VERSION", "0.1.16"))
    ok &= check("Claude Code", ["claude", "--version"], e.get("CLAUDE_MIN_VERSION", "2.1.316"))
    ok &= check(
        "Codex", ["codex", "--version"], e.get("CODEX_MIN_VERSION", "0.165.0"), required=False
    )
    return 1 if ns.strict and not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
