#!/usr/bin/env python3
import argparse, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def env_file(path):
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        # shell files use ${VAR:-default}; capture default for documentation checks
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

def check_tool(name, command, minimum, strict=False):
    if not shutil.which(command[0]):
        print(f"{name}: MISSING (need >= {minimum})")
        return False
    raw = run(command)
    got = ver_tuple(raw)
    want = ver_tuple(minimum)
    ok = bool(got and want and got >= want)
    print(f"{name}: {'.'.join(map(str, got)) if got else 'unknown'} (baseline >= {minimum}) {'OK' if ok else 'CHECK'}")
    if strict and not ok:
        return False
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="fail below the verified compatibility baseline")
    ns = ap.parse_args()
    e = env_file(ROOT / ".orchestration/versions.env")

    ok = True
    ok &= check_tool("Python", ["python3", "--version"], e.get("PYTHON_MIN_VERSION", "3.10.0"), ns.strict)
    ok &= check_tool("Node.js", ["node", "--version"], f"{e.get('NODE_MIN_MAJOR','24')}.0.0", ns.strict)
    ok &= check_tool("npm", ["npm", "--version"], f"{e.get('NPM_MIN_MAJOR','10')}.0.0", ns.strict)
    ok &= check_tool("Herdr", ["herdr", "--version"], e.get("HERDR_MIN_VERSION", "0.9.3"), ns.strict)
    ok &= check_tool("Claude Code", ["claude", "--version"], e.get("CLAUDE_MIN_VERSION", "2.1.301"), ns.strict)
    ok &= check_tool("Codex", ["codex", "--version"], e.get("CODEX_MIN_VERSION", "0.163.0"), ns.strict)
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
