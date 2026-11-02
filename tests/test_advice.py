#!/usr/bin/env python3
"""Offline tests: owner context advice, owner switch, template update check."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "scripts"))
from orchlib import advice, config, quota  # noqa: E402

NOW = time.time()


def q(agent, remaining):
    return {"agent": agent, "available": True, "stale": False, "observed_at": NOW,
            "effective_remaining_percent": remaining,
            "windows": [{"name": "5h", "remaining_percent": remaining, "used_percent": 100 - remaining,
                         "resets_at": NOW + 3600}]}


class Advice(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp())
        self.old_cache = quota.CACHE_DIR
        quota.CACHE_DIR = self.td / "cache"
        self.root = self.td / "proj"
        shutil.copytree(SRC, self.root, ignore=shutil.ignore_patterns(".git", "runtime", "worktrees", "__pycache__"))
        (self.root / ".orchestration/template.toml").write_text('version = "0.2.0"\nupstream = "none"\n')
        self.cfg = config.load(self.root)

    def tearDown(self):
        quota.CACHE_DIR = self.old_cache
        shutil.rmtree(self.td, ignore_errors=True)

    def tap(self, tokens):
        advice.record_session({"session_id": "s1", "workspace": {"project_dir": str(self.root)},
                               "context_window": {"context_window_size": 1_000_000,
                                                  "current_usage": {"input_tokens": 10,
                                                                    "cache_read_input_tokens": tokens - 10}}})

    def compute(self, quotas, running=0):
        return advice.compute(self.cfg, quotas, running, check_update=False)

    def test_context_thresholds(self):
        qs = {"claude": q("claude", 80), "codex": q("codex", 80)}
        self.tap(40_000)
        self.assertEqual(self.compute(qs)["items"], [])
        self.tap(120_000)
        r = self.compute(qs, running=1)
        self.assertEqual([i["kind"] for i in r["items"]], ["context"])
        self.assertIn("/compact", r["items"][0]["text"])
        self.assertIn("after the running tasks", r["items"][0]["text"])
        self.tap(200_000)
        kinds = [i["kind"] for i in self.compute(qs)["items"]]
        self.assertEqual(kinds, ["context", "handoff"])

    def test_owner_low_quota_suggests_agent_with_most_left(self):
        r = self.compute({"claude": q("claude", 6), "codex": q("codex", 70)})
        own = next(i for i in r["items"] if i["kind"] == "owner")
        self.assertIn("hand over to codex", own["text"])
        self.assertEqual(own["command"], "python3 scripts/orch.py owner set codex --launch")
        self.assertTrue(any(i["kind"] == "handoff" for i in r["items"]))

    def test_owner_low_quota_without_alternative(self):
        r = self.compute({"claude": q("claude", 6), "codex": q("codex", 5)})
        own = next(i for i in r["items"] if i["kind"] == "owner")
        self.assertIsNone(own["command"])

    def test_stale_low_quota_advises_only_before_window_reset(self):
        old = q("claude", 8)
        old["stale"] = True
        quotas = {"claude": old, "codex": q("codex", 70)}
        r = advice.compute(self.cfg, quotas, 0, now=NOW, check_update=False)
        own = next(i for i in r["items"] if i["kind"] == "owner")
        self.assertEqual(own["level"], "warn")
        self.assertIn("stale reading", own["text"])
        self.assertIn("verify the current quota", own["text"])
        self.assertIn("hand over to codex", own["text"])
        self.assertTrue(r["owner_quota_stale"])

        old["windows"][0]["resets_at"] = NOW - 1
        r = advice.compute(self.cfg, quotas, 0, now=NOW, check_update=False)
        self.assertFalse(any(i["kind"] == "owner" for i in r["items"]))

    def test_update_check_uses_tags(self):
        up = self.td / "up"
        subprocess.run(["git", "init", "-q", str(up)], check=True)
        g = ["git", "-C", str(up), "-c", "user.email=t@example.invalid", "-c", "user.name=T"]
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "x"], check=True)
        for t in ("v0.1.0", "v0.10.0", "v0.3.0", "junk"):
            subprocess.run(g + ["tag", t], check=True)
        self.assertEqual(advice.latest_release(str(up)), "0.10.0")
        (self.root / ".orchestration/template.toml").write_text(f'version = "0.2.0"\nupstream = "{up}"\n')
        r = advice.compute(self.cfg, {"claude": q("claude", 80)}, 0)
        self.assertEqual([i["kind"] for i in r["items"]], ["update"])

    def test_new_release_is_seen_at_a_forced_boundary(self):
        up = self.td / "up"
        subprocess.run(["git", "init", "-q", str(up)], check=True)
        g = ["git", "-C", str(up), "-c", "user.email=t@example.invalid", "-c", "user.name=T"]
        subprocess.run(g + ["commit", "-q", "--allow-empty", "-m", "x"], check=True)
        subprocess.run(g + ["tag", "v0.2.0"], check=True)
        (self.root / ".orchestration/template.toml").write_text(f'version = "0.2.0"\nupstream = "{up}"\n')
        self.assertFalse(advice.update(self.cfg, now=NOW)["available"])

        # The installed project and its cache predate the new release.
        subprocess.run(g + ["tag", "v0.2.1"], check=True)
        self.assertFalse(advice.update(self.cfg, now=NOW + 1)["available"])
        self.assertTrue(advice.update(self.cfg, now=NOW + 1, force=True)["available"])
        r = advice.compute(self.cfg, {"claude": q("claude", 80)}, 0, now=NOW + 1)
        self.assertEqual([i["kind"] for i in r["items"]], ["update"])
        self.assertIn("template 0.2.1 available", r["items"][0]["text"])

    def test_claude_quota_merges_sessions(self):
        def tap(sid, five_used, five_reset):
            advice.record_session({"session_id": sid, "cwd": str(self.root), "rate_limits": {
                "five_hour": {"used_percentage": five_used, "resets_at": five_reset},
                "seven_day": {"used_percentage": 40, "resets_at": NOW + 86400}}})
        # An idle session still shows its window from before the reset (95% used).
        tap("idle", 95, NOW - 600)
        tap("busy", 20, NOW + 4 * 3600)
        tap("busy2", 27, NOW + 4 * 3600)
        q = quota.probe_claude(NOW, 1800)
        five = next(w for w in q["windows"] if w["name"] == "5h")
        self.assertEqual(five["used_percent"], 27)

    def test_tap_keeps_snapshot_without_rate_limits(self):
        env = {**os.environ, "ORCH_CACHE_DIR": str(quota.CACHE_DIR)}
        cmd = [sys.executable, str(SRC / "scripts/orch.py"), "statusline-tap", "--", "true"]
        rl = {"five_hour": {"used_percentage": 30, "resets_at": NOW + 3600}}
        subprocess.run(cmd, input=json.dumps({"session_id": "a", "rate_limits": rl}), text=True, env=env, check=True)
        subprocess.run(cmd, input=json.dumps({"session_id": "b"}), text=True, env=env, check=True)
        snap = json.loads((quota.CACHE_DIR / "claude-statusline.json").read_text())
        self.assertEqual(snap["rate_limits"], rl)

    def test_owner_set_requires_handoff(self):
        env = {**os.environ, "ORCH_CACHE_DIR": str(quota.CACHE_DIR), "ORCH_HC": "false"}
        cmd = [sys.executable, str(SRC / "scripts/orch.py"), "--root", str(self.root), "owner", "set", "codex"]
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("HANDOFF.json", p.stderr)
        (self.root / ".planning").mkdir(exist_ok=True)
        (self.root / ".planning/HANDOFF.json").write_text(json.dumps({"x": 1}))
        p = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('owner = "codex"', (self.root / ".orchestration/routing.toml").read_text())


if __name__ == "__main__":
    unittest.main()
