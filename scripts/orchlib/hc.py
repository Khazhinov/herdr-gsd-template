"""Thin herdr-core access: the `hc` CLI for commands, `hc connect` for
JSON-RPC (documents, event subscription). ORCH_HC replaces the binary in tests."""

import contextlib
import json
import os
import subprocess
import sys
import threading
import uuid


class HCError(Exception):
    def __init__(self, msg, kind=None, code=None):
        super().__init__(msg)
        self.kind, self.code = kind, code


DAEMON_HINT = (
    "this command runs inside the shared Codex app-server daemon, with the environment of the "
    "terminal that started the daemon (wrong HC_TERMINAL_ID, sandbox, PATH). Restart Codex "
    "with `codex --no-daemon`, or set `features.daemon_auto_start = false` and stop the daemon "
    "(OPERATIONS 3.3)"
)


def codex_daemon():
    """True when an ancestor process is the Codex app-server daemon (Linux /proc)."""
    pid = os.getppid()
    while pid > 1:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                argv = f.read().split(b"\0")
            with open(f"/proc/{pid}/stat") as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return False
        if b"codex" in argv[0] and b"app-server" in b" ".join(argv):
            return True
    return False


def binary():
    return os.environ.get("ORCH_HC", "hc").split()


def call(*args, check=True, timeout=None):
    """Run `hc <args>`; JSON output is parsed, text returned as-is."""
    p = subprocess.run([*binary(), *args], capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        kind = None
        try:
            kind = json.loads(p.stderr).get("error", {}).get("kind")
        except (json.JSONDecodeError, AttributeError):
            pass
        msg = f"hc {' '.join(args)}: rc={p.returncode} {p.stderr.strip()[:400]}"
        if "Operation not permitted" in p.stderr:
            msg += ("\nthis agent's sandbox blocks the herdr-core socket: turn the network on in its "
                    "permission profile and restart it (OPERATIONS 3.3); the core itself is running")
        raise HCError(msg, kind, p.returncode)
    out = p.stdout.strip()
    if out.startswith(("{", "[")):
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return out


def ls(all_=False):
    """Full terminal facts (labels, foreground cwd, status object) via RPC;
    `hc ls` prints only a summary row per terminal."""
    try:
        rpc = RPC()
        try:
            r = rpc.call("terminal.list", all=all_)
        finally:
            rpc.close()
    except (OSError, HCError):
        r = call("ls", "--json", *(["--all"] if all_ else []))
    return r.get("terminals", []) if isinstance(r, dict) else []


def get(t):
    return call("get", t, "--json")


def run(argv, name, cwd, labels=None, outlive_parent=False, no_parent=False):
    args = ["run", "--bg", "--json", "--name", name, "--cwd", str(cwd)]
    for k, v in (labels or {}).items():
        args += ["--label", f"{k}={v}"]
    if outlive_parent:
        args.append("--outlive-parent")
    if no_parent:
        args.append("--no-parent")
    return call(*args, "--", *argv)


def send(t, text):
    return call("send", t, text, "--json")


def wait(t=None, children=None, timeout=180):
    args = ["wait", "--json", "--timeout", str(int(timeout))]
    if children:
        args += ["--children", children]
    if t:
        args.append(t)
    return call(*args, check=False, timeout=timeout + 30)


def label(t, labels):
    return call("label", t, *[f"{k}={v}" for k, v in labels.items()], "--json")


def kill(t):
    return call("kill", t, "--json", check=False)


def rm(t):
    return call("rm", t, "--json", check=False)


def read(t, lines=60):
    return call("read", t, "--lines", str(lines), check=False)


class RPC:
    """JSON-RPC over `hc connect`. Notifications go to on_event (own thread)."""

    def __init__(self, on_event=None):
        self.p = subprocess.Popen(
            [*binary(), "connect"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.n = 0
        self.lock = threading.Lock()
        self.pending = {}
        self.on_event = on_event
        self.closed = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()
        try:
            self.call("hello")
        except BaseException:
            self.close()
            raise

    def _reader(self):
        for line in self.p.stdout:
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "id" in o and o["id"] in self.pending:
                slot = self.pending.pop(o["id"])
                slot["msg"] = o
                slot["ev"].set()
            elif o.get("method") and self.on_event:
                self.on_event(o)
        self.closed.set()
        for slot in list(self.pending.values()):
            slot["ev"].set()

    def call(self, method, timeout=15, **params):
        with self.lock:
            self.n += 1
            i = self.n
            slot = {"ev": threading.Event(), "msg": None}
            self.pending[i] = slot
            self.p.stdin.write(
                json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n"
            )
            self.p.stdin.flush()
        if not slot["ev"].wait(timeout) or slot["msg"] is None:
            self.pending.pop(i, None)
            raise HCError(f"hc rpc {method}: no answer")
        if "error" in slot["msg"]:
            e = slot["msg"]["error"]
            raise HCError(
                f"hc rpc {method}: {e}",
                (e.get("data") or {}).get("kind") if isinstance(e, dict) else None,
            )
        return slot["msg"].get("result")

    def doc_put(self, name, value):
        """Write a document, retrying once on a version race."""
        for _ in range(3):
            cur = self.call("doc.get", name=name)
            try:
                return self.call("doc.set", name=name, value=value, version=cur.get("version", 0))
            except HCError:
                continue
        return None

    def close(self):
        with contextlib.suppress(Exception):
            self.p.kill()
            self.p.wait(timeout=5)
            self.p.stdin.close()
            self.p.stdout.close()


def doc_put_once(name, value):
    """Best-effort publication; orchestration never depends on it."""
    try:
        rpc = RPC()
    except (OSError, HCError):
        return False
    try:
        rpc.doc_put(name, value)
        return True
    except HCError:
        return False
    finally:
        rpc.close()


# ---------------------------------------------------------------- Herdr App placement

APP_DOC = "herdr-app"  # core document with the App layout: spaces, tabs, terminals
SPACES = ("caller", "project")


def _inside(path, root):
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


def _tab_terminals(node):
    if (node.get("content") or {}).get("terminal"):
        yield node["content"]["terminal"]
    for c in node.get("children") or []:
        yield from _tab_terminals(c)


def caller_space():
    """Space of the terminal that runs this command, if it is shown in the App."""
    me = os.environ.get("HC_TERMINAL_ID")
    if not me:
        return None
    try:
        return (get(me).get("labels") or {}).get("herdr.space")
    except HCError:
        return None


def project_space(value, root, terminals):
    """The space whose terminals work inside `root` now; else one created inside `root`.
    The App names a space after the live folder of its tabs; `folder` keeps the folder the space
    was created in, so it is only a fallback (same rule as Mission Control)."""
    cwd = {t.get("address"): (t.get("foreground") or {}).get("cwd") or t.get("cwd") for t in terminals}
    created = None
    for sp in value.get("spaces", []):
        for tab in sp.get("tabs") or []:
            if any(cwd.get(a) and _inside(cwd[a], root) for a in _tab_terminals(tab.get("root") or {})):
                return sp["id"]
        if created is None and sp.get("folder") and _inside(sp["folder"], root):
            created = sp["id"]
    return created


def place(name, root, mode="caller"):
    """Show terminal `name` in Herdr App and return the space id. `caller`: the calling terminal's
    space, else the project's. `project`: the space working in `root`, created when none exists.
    A terminal labelled `herdr.space` gets a tab from the App; no label means it stays hidden."""
    if mode not in SPACES:
        raise HCError(f"[workers] space must be one of {', '.join(SPACES)}")
    sid = caller_space() if mode == "caller" else None
    if sid:
        label(name, {"herdr.space": sid})
        return sid
    rpc = RPC()
    try:
        for _ in range(3):  # doc.set fails on a concurrent layout change: read again
            doc = rpc.call("doc.get", name=APP_DOC) or {}
            value = doc.get("value") if isinstance(doc.get("value"), dict) else {"spaces": []}
            terms = (rpc.call("terminal.list", all=False) or {}).get("terminals", [])
            sid = project_space(value, root, terms)
            if sid:
                label(name, {"herdr.space": sid})
                return sid
            me = next((t for t in terms if t.get("name") == name), None)
            if not me:
                return None
            sid, tab = "sp" + uuid.uuid4().hex, "tb" + uuid.uuid4().hex
            value.setdefault("spaces", []).append({"id": sid, "name": "", "folder": os.path.realpath(root),
                "tabs": [{"id": tab, "name": "", "root": {"id": tab, "type": "row", "children": [
                    {"id": "p" + uuid.uuid4().hex, "type": "block",
                     "content": {"terminal": me["address"]}}]}}]})
            try:
                rpc.call("doc.set", name=APP_DOC, value=value, version=doc.get("version", 0))
            except HCError as e:
                if e.kind == "conflict":
                    continue
                raise
            label(name, {"herdr.space": sid, "herdr.tab": tab})
            return sid
    finally:
        rpc.close()
    return None


def show(name, root, mode="caller"):
    """`place` that never fails a launch: the terminal runs either way."""
    try:
        return place(name, root, mode)
    except (OSError, HCError, ValueError) as e:
        print(f"{name}: not shown in Herdr App ({e})", file=sys.stderr)
        return None
