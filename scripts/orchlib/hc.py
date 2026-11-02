"""Thin herdr-core access: the `hc` CLI for commands, `hc connect` for
JSON-RPC (documents, event subscription). ORCH_HC replaces the binary in tests."""
import json
import os
import subprocess
import threading


class HCError(Exception):
    def __init__(self, msg, kind=None, code=None):
        super().__init__(msg)
        self.kind, self.code = kind, code


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
        raise HCError(f"hc {' '.join(args)}: rc={p.returncode} {p.stderr.strip()[:400]}", kind, p.returncode)
    out = p.stdout.strip()
    if out.startswith(("{", "[")):
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
    return out


def available():
    try:
        call("server", "status", "--json", timeout=10)
        return True
    except (OSError, HCError, subprocess.TimeoutExpired):
        return False


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
        self.p = subprocess.Popen([*binary(), "connect"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.n = 0
        self.lock = threading.Lock()
        self.pending = {}
        self.on_event = on_event
        self.closed = threading.Event()
        threading.Thread(target=self._reader, daemon=True).start()
        self.call("hello")

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
            self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
            self.p.stdin.flush()
        if not slot["ev"].wait(timeout) or slot["msg"] is None:
            self.pending.pop(i, None)
            raise HCError(f"hc rpc {method}: no answer")
        if "error" in slot["msg"]:
            e = slot["msg"]["error"]
            raise HCError(f"hc rpc {method}: {e}", (e.get("data") or {}).get("kind") if isinstance(e, dict) else None)
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
        try:
            self.p.kill()
            self.p.wait(timeout=5)
        except Exception:
            pass


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
