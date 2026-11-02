#!/usr/bin/env python3
"""Minimal herdr-core double for offline tests. State: $FAKE_HC_STATE (JSON).

FAKE_HC_WORKER=complete|incomplete|none makes `run` simulate the worker:
it reads the contract named in the prompt, creates FAKE_HC_TOUCH (if set) in
the cwd and writes the report with that sentinel.
"""
import json
import os
import re
import sys
from pathlib import Path

STATE = Path(os.environ["FAKE_HC_STATE"])


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"n": 0, "terms": {}, "calls": [], "docs": {}}


def save(s):
    STATE.write_text(json.dumps(s))


def find(s, t):
    for addr, term in s["terms"].items():
        if t in (addr, term.get("name")):
            return addr, term
    print(json.dumps({"error": {"kind": "not_found", "message": f"no terminal {t}"}}), file=sys.stderr)
    raise SystemExit(3)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def simulate(argv, cwd):
    mode = os.environ.get("FAKE_HC_WORKER", "none")
    m = re.search(r"Read the task contract (\S+)", argv[-1])
    if mode == "none" or not m:
        return
    text = Path(m.group(1)).read_text()
    report = Path(re.search(r"Write your report to `([^`]+)`", text).group(1))
    if os.environ.get("FAKE_HC_TOUCH"):
        (Path(cwd) / os.environ["FAKE_HC_TOUCH"]).write_text("work\n")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"# Summary\n\nDone by fake worker.\n\nResult: {mode}\n")


def main(a):
    s = load()
    cmd, args = a[0], a[1:]
    s["calls"].append(a)
    if cmd == "run":
        i = args.index("--")
        argv = args[i + 1:]
        s["n"] += 1
        addr = f"t{s['n']}"
        labels = {}
        j = 0
        while j < i:
            if args[j] == "--label":
                k, v = args[j + 1].split("=", 1)
                labels[k] = v
            j += 1
        cwd = opt(args, "--cwd")
        live = os.environ.get("FAKE_HC_WORKER", "none") == "none" or os.environ.get("FAKE_HC_STAY") == "1"
        s["terms"][addr] = {"address": addr, "name": opt(args, "--name"), "argv": argv, "cwd": cwd,
                            "labels": labels, "state": "live" if live else "finished",
                            "status": {"app": "fake", "state": "working"}}
        simulate(argv, cwd)
        save(s)
        print(json.dumps({"address": addr, "state": "live"}))
    elif cmd == "ls":
        save(s)
        terms = [t for t in s["terms"].values() if "--all" in args or t["state"] == "live"]
        print(json.dumps({"terminals": terms}))
    elif cmd == "get":
        save(s)
        print(json.dumps(find(s, args[0])[1]))
    elif cmd in ("kill", "rm"):
        try:
            addr, t = find(s, args[0])
        except SystemExit:
            save(s)
            raise
        if cmd == "kill":
            t["state"] = "finished"
        else:
            s["terms"].pop(addr)
        save(s)
        print("{}")
    elif cmd == "label":
        addr, t = find(s, args[0])
        for kv in args[1:]:
            if "=" in kv:
                k, v = kv.split("=", 1)
                t["labels"][k] = v
        save(s)
        print("{}")
    elif cmd in ("wait", "send", "keys"):
        save(s)
        print(json.dumps({"ended": True, "reason": "status"}))
    elif cmd == "read":
        save(s)
        print("fake screen")
    elif cmd == "server":
        save(s)
        print(json.dumps({"version": "fake"}))
    elif cmd == "connect":
        save(s)
        for line in sys.stdin:
            req = json.loads(line)
            if req["method"] == "terminal.list":
                all_ = (req.get("params") or {}).get("all")
                res = {"terminals": [x for x in s["terms"].values() if all_ or x["state"] == "live"]}
            elif req["method"] == "doc.get":
                res = {"value": None, "version": 0}
            else:
                res = {"version": 1}
            print(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": res}), flush=True)
    else:
        save(s)
        print(f"fake hc: unsupported {cmd}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
