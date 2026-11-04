#!/usr/bin/env bash
# Install the GSD Mission Control mod into Herdr App and check it.
# Herdr App may run on this machine or on Windows while the project lives in WSL.
set -euo pipefail
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/herdr-app/gsd-mission-control
APP=${HERDR_APP_BIN:-}
HOME_DIR=${HERDR_APP_HOME:-}

if [[ -z "$HOME_DIR" ]]; then
  CMD=$(command -v cmd.exe || ls /mnt/c/Windows/System32/cmd.exe 2>/dev/null || true)
  if [[ -n "$CMD" ]]; then
    WINHOME=$(wslpath "$(cd /mnt/c && "$CMD" /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")
    HOME_DIR="$WINHOME/.config/herdr-app"
    APP=${APP:-"$WINHOME/AppData/Local/Programs/herdr-app/herdr-app.exe"}
  else
    HOME_DIR="$HOME/.config/herdr-app"
    APP=${APP:-herdr-app}
  fi
fi
[[ -d "$HOME_DIR" ]] || { echo "Herdr App home not found: $HOME_DIR (set HERDR_APP_HOME)" >&2; exit 2; }

DEST="$HOME_DIR/mods/gsd-mission-control"
mkdir -p "$DEST"
cp "$SRC/main.js" "$SRC/mod.json" "$DEST/"
echo "installed: $DEST"

# Layout "GSD Mission Control": the app's current main layout plus a right
# column with the mod. Generated from the installed main.json so it follows
# the app version; rerun this script after an app update.
python3 - "$HOME_DIR" <<'PY'
import json, sys
from pathlib import Path
home = Path(sys.argv[1])
main = json.loads((home / "layouts" / "main.json").read_text())
def find(n, i):
    if n.get("id") == i:
        return n
    for c in n.get("children", []):
        r = find(c, i)
        if r:
            return r
body = find(main, "work-body")
if body is None:
    sys.exit("main layout has no work-body row; layout not generated")
body["children"] = [c for c in body["children"] if c.get("id") != "mission-control"] + [{
    "id": "mission-control", "type": "block", "size": {"px": 460}, "min": 0, "max": 900,
    "radius": 10, "background": "chrome", "border": {"width": 1, "color": "border"},
    "content": {"mod": "gsd-mission-control"}}]
main.pop("preview", None)
main["name"] = "GSD Mission Control"
# Other installers (herdr-agent-kit's space-groups, agent-limits) edit this
# layout's sidebar too. Keep their edits: a block whose mod they replaced keeps
# it, a block they added stays after the same sibling.
out = home / "layouts" / "gsd-mission-control.json"
def walk(n):
    yield n
    for c in n.get("children", []):
        yield from walk(c)
old = find(json.loads(out.read_text()), "sidebar") if out.exists() else None
new = find(main, "sidebar")
if old and new:
    fresh = {n.get("id"): n for n in walk(new)}
    for n in walk(old):
        f = fresh.get(n.get("id"))
        if f and n.get("type") == "block" and f.get("type") == "block" and n.get("content") != f.get("content"):
            f["content"] = n["content"]
    for n in walk(old):
        f = fresh.get(n.get("id"))
        if not f or "children" not in n:
            continue
        ids = [c.get("id") for c in f.get("children", [])]
        for i, c in enumerate(n["children"]):
            if c.get("id") in fresh:
                continue
            prev = n["children"][i - 1].get("id") if i else None
            at = ids.index(prev) + 1 if prev in ids else 0
            f["children"].insert(at, c)
            ids.insert(at, c.get("id"))
            fresh[c.get("id")] = c
out.write_text(json.dumps(main, indent=2))
print("layout:", out)
PY

if [[ -x "$APP" ]] || command -v "$APP" >/dev/null 2>&1; then
  target=$DEST
  [[ "$APP" == *.exe ]] && target=$(wslpath -w "$DEST")
  "$APP" check "$target"
  echo "layout: herdr-app do layout.switch --name gsd-mission-control"
  echo "window: herdr-app do mod.open --name gsd-mission-control"
else
  echo "herdr-app binary not found; run 'herdr-app check $DEST' yourself" >&2
fi
