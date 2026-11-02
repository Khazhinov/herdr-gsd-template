#!/usr/bin/env python3
"""Offline tests: routing matrix, quota normalization, config validation,
worker lifecycle on a fake herdr-core, GSD cross-AI bridge."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "scripts"))
from orchlib import config, quota, route  # noqa: E402

NOW = 1_800_000_000.0


def q(agent, remaining, stale=False, resets_in_h=48):
    return {"agent": agent, "available": True, "confidence": "official-rpc", "stale": stale,
            "observed_at": NOW, "effective_remaining_percent": remaining,
            "windows": [{"name": "7d", "remaining_percent": remaining, "used_percent": 100 - remaining,
                         "resets_at": NOW + resets_in_h * 3600, "window_minutes": 10080}]}


def cfg():
    return config.load(SRC)


class Routing(unittest.TestCase):
    """Test matrix B of the v0.2 migration pack."""

    def decide(self, role, quotas, **kw):
        kw.setdefault("installed", {"claude": True, "codex": True, "kimi": True, "zcode": True})
        return route.decide(cfg(), role, quotas, now=NOW, **kw)

    def test_codex_first(self):
        d = self.decide("execute", {"codex": q("codex", 70), "claude": q("claude", 90)})
        self.assertEqual(d["selected"], "codex")
        self.assertIn("quota 70% > heavy reserve 30%", d["reason"])

    def test_codex_reserve_falls_back_to_claude(self):
        d = self.decide("execute", {"codex": q("codex", 25), "claude": q("claude", 80)})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("codex (quota 25% <= heavy reserve 30%)", d["reason"])

    def test_codex_below_heavy_reserve_still_reviews(self):
        d = self.decide("review", {"codex": q("codex", 25), "claude": q("claude", 80)})
        self.assertEqual(d["selected"], "codex")

    def test_review_independence(self):
        d = self.decide("review", {"codex": q("codex", 60), "claude": q("claude", 90)})
        self.assertEqual(d["selected"], "codex")
        self.assertTrue(d["independent"])

    def test_review_falls_back_to_owner_marked_not_independent(self):
        d = self.decide("review", {"codex": q("codex", 5), "claude": q("claude", 90)})
        self.assertEqual(d["selected"], "claude")
        self.assertFalse(d["independent"])
        self.assertIn("NOT independent", d["reason"])

    def test_unknown_quota_fails_closed_for_heavy(self):
        d = self.decide("execute", {"codex": quota.unknown("codex", "x"), "claude": quota.unknown("claude", "x")})
        self.assertIsNone(d["selected"])
        self.assertIn("fails closed", d["reason"])

    def test_stale_quota_is_unknown(self):
        d = self.decide("execute", {"codex": q("codex", 90, stale=True), "claude": q("claude", 80)})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("quota stale", d["reason"])

    def test_unknown_quota_allows_light(self):
        d = self.decide("review", {"codex": quota.unknown("codex", "x"), "claude": q("claude", 90)})
        self.assertEqual(d["selected"], "codex")

    def test_candidate_agents_not_auto_routed(self):
        d = self.decide("research", {"codex": q("codex", 60), "claude": q("claude", 60)})
        self.assertEqual(d["selected"], "codex")
        self.assertIn("kimi (stability candidate", d["reason"])

    def test_busy_agent_skipped(self):
        d = self.decide("execute", {"codex": q("codex", 70), "claude": q("claude", 90)}, running={"codex": 2})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("busy 2/2", d["reason"])

    def test_not_installed_skipped(self):
        d = self.decide("execute", {"codex": q("codex", 70), "claude": q("claude", 90)},
                        installed={"codex": False, "claude": True})
        self.assertEqual(d["selected"], "claude")

    def test_override_and_ineligible_override(self):
        qs = {"codex": q("codex", 70), "claude": q("claude", 90)}
        self.assertEqual(self.decide("execute", qs, override="claude")["selected"], "claude")
        d = self.decide("execute", {"codex": q("codex", 70), "claude": q("claude", 10)}, override="claude")
        self.assertEqual(d["selected"], "codex")
        self.assertIn("override claude ignored", d["reason"])

    def test_use_or_lose_prefers_expiring_capacity(self):
        c = cfg()
        c["routing"]["roles"]["execute"]["strategy"] = "use-or-lose"
        qs = {"codex": q("codex", 40, resets_in_h=90), "claude": q("claude", 50, resets_in_h=10)}
        d = route.decide(c, "execute", qs, installed={"codex": True, "claude": True}, now=NOW)
        self.assertEqual(d["selected"], "claude")

    def test_deterministic(self):
        qs = {"codex": q("codex", 55), "claude": q("claude", 66)}
        a, b = self.decide("execute", qs), self.decide("execute", qs)
        self.assertEqual(a, b)

    def test_no_agent_ids_in_scheduler(self):
        text = (SRC / "scripts/orchlib/route.py").read_text()
        for aid in ("codex", "claude", "kimi", "zcode"):
            self.assertNotIn(f'"{aid}"', text)


class Quotas(unittest.TestCase):
    RPC = {"ordinaryUsageAllowed": True,
           "rateLimits": {"primary": {"usedPercent": 27, "windowDurationMins": 300, "resetsAt": NOW + 3600},
                          "secondary": {"usedPercent": 59, "windowDurationMins": 10080, "resetsAt": NOW + 86400},
                          "planType": "plus"},
           "rateLimitResetCredits": {"credits": [{"status": "available"}, {"status": "used"}]}}

    def test_codex_rpc(self):
        r = quota.probe_codex(NOW, 1800, rpc=lambda: self.RPC)
        self.assertEqual(r["confidence"], "official-rpc")
        self.assertEqual([w["name"] for w in r["windows"]], ["5h", "7d"])
        self.assertEqual(r["effective_remaining_percent"], 41.0)
        self.assertEqual(r["extra"]["reset_credits_available"], 1)

    def test_codex_rollout_fallback_and_reset_window(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "2026/10/31/rollout-x.jsonl"
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps({"timestamp": "2026-10-31T10:00:00Z", "payload": {"rate_limits": {
                "primary": {"used_percent": 80, "window_minutes": 300, "resets_at": NOW - 10},
                "secondary": {"used_percent": 30, "window_minutes": 10080, "resets_at": NOW + 999}}}}) + "\n")

            def broken():
                raise OSError("no codex")
            r = quota.probe_codex(NOW, 0, rpc=broken, sessions_root=td)
            self.assertEqual(r["confidence"], "parsed-local-telemetry")
            self.assertEqual(r["windows"][0]["remaining_percent"], 100.0)  # window already reset
            self.assertEqual(r["effective_remaining_percent"], 70.0)
            self.assertIn("rpc_error", r["extra"])

    def test_codex_nothing(self):
        def broken():
            raise OSError("no codex")
        with tempfile.TemporaryDirectory() as td:
            r = quota.probe_codex(NOW, 0, rpc=broken, sessions_root=td)
        self.assertFalse(r["available"])
        self.assertEqual(r["confidence"], "unknown")

    def test_claude_snapshot_and_stale(self):
        with tempfile.TemporaryDirectory() as td:
            snap = Path(td) / "s.json"
            snap.write_text(json.dumps({"observed_at": NOW - 60, "rate_limits": {
                "five_hour": {"used_percentage": 15, "resets_at": NOW + 3600},
                "seven_day": {"used_percentage": 41, "resets_at": NOW + 86400}}}))
            r = quota.probe_claude(NOW, 1800, snapshot=snap)
            self.assertEqual(r["effective_remaining_percent"], 59.0)
            self.assertFalse(r["stale"])
            self.assertTrue(quota.probe_claude(NOW + 3600, 1800, snapshot=snap)["stale"])
            snap.write_text(json.dumps({"observed_at": NOW, "rate_limits": None}))
            self.assertFalse(quota.probe_claude(NOW, 1800, snapshot=snap)["available"])

    def test_variants_share_one_reading_and_gate_on_chosen_windows(self):
        c = cfg()
        c["agents"]["codex-exec"] = dict(c["agents"]["codex"], quota_windows=["5h"])
        calls = []
        orig = quota.probe_codex
        quota.probe_codex = lambda now, s: calls.append(1) or quota.finish(quota.codex_from_rpc(self.RPC, now), s, now)
        try:
            shared = {}
            a = quota.probe(c, "codex", NOW, shared)
            b = quota.probe(c, "codex-exec", NOW, shared)
        finally:
            quota.probe_codex = orig
        self.assertEqual(len(calls), 1)
        self.assertEqual(a["effective_remaining_percent"], 41.0)
        self.assertEqual(b["effective_remaining_percent"], 73.0)  # weekly window does not gate
        self.assertEqual(b["agent"], "codex-exec")

    def test_headroom(self):
        self.assertEqual(quota.headroom(q("x", 50, resets_in_h=10), NOW), 5.0)
        self.assertIsNone(quota.headroom(quota.unknown("x", "r"), NOW))


class Config(unittest.TestCase):
    def test_unknown_agent_in_chain(self):
        c = cfg()
        c["routing"]["roles"]["execute"]["chain"].append("ghost")
        with self.assertRaisesRegex(config.ConfigError, "unknown agent 'ghost'"):
            config.validate(c)

    def test_unknown_probe(self):
        c = cfg()
        c["agents"]["codex"]["quota"] = "magic"
        with self.assertRaisesRegex(config.ConfigError, "unknown probe"):
            config.validate(c)

    def test_owner_needs_capability(self):
        c = cfg()
        c["routing"]["owner"] = "codex"
        with self.assertRaisesRegex(config.ConfigError, "owner"):
            config.validate(c)

    def test_public_defaults_are_safe(self):
        text = (SRC / ".orchestration/agents.toml").read_text()
        for bad in ("danger-full-access", "--ask-for-approval", "never", "--dangerously-skip-permissions",
                    "bypassPermissions"):
            cmds = [ln for ln in text.splitlines() if ln.startswith(("command", "worktree_args"))]
            self.assertFalse(any(bad in ln for ln in cmds), bad)

    def test_codex_runs_without_daemon(self):
        self.assertIn("--no-daemon", cfg()["agents"]["codex"]["command"])


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.repo = Path(self.td) / "proj"
        shutil.copytree(SRC, self.repo, ignore=shutil.ignore_patterns(".git", "runtime", "worktrees", "__pycache__", "docs"))
        (self.repo / ".orchestration/agents.local.toml").write_text(
            '[agents.codex]\nquota = "static"\nquota_static = {remaining_percent = 80}\n'
            '[agents.claude]\nquota = "static"\nquota_static = {remaining_percent = 90}\n')
        g = ["git", "-C", str(self.repo)]
        subprocess.run(g + ["init", "-q", "-b", "main"], check=True)
        subprocess.run(g + ["config", "user.email", "t@example.invalid"], check=True)
        subprocess.run(g + ["config", "user.name", "T"], check=True)
        subprocess.run(g + ["add", "-A"], check=True)
        subprocess.run(g + ["commit", "-qm", "init"], check=True)
        self.env = {"ORCH_HC": f"{sys.executable} {SRC / 'tests/fake_hc.py'}",
                    "FAKE_HC_STATE": str(Path(self.td) / "hc.json"),
                    "ORCH_CACHE_DIR": str(Path(self.td) / "cache"),
                    "HC_TERMINAL_ID": "", "FAKE_HC_WORKER": "none"}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        quota.CACHE_DIR = Path(self.env["ORCH_CACHE_DIR"])
        quota.QUOTA_CACHE = quota.CACHE_DIR / "quotas.json"
        import orch
        self.orch = orch

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.td, ignore_errors=True)

    def run_orch(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = self.orch.main(["--root", str(self.repo), *args])
        return rc, buf.getvalue()

    def task(self, name="t.md", text="# Task\nDo it.\n"):
        p = Path(self.td) / name
        p.write_text(text)
        return str(p)

    def calls(self):
        return json.loads(Path(self.env["FAKE_HC_STATE"]).read_text())["calls"]

    def test_execute_lifecycle(self):
        rc, out = self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "p1-exec", "--json")
        self.assertEqual(rc, 0, out)
        t = json.loads(out)
        self.assertEqual(t["agent"], "codex")
        wt = Path(t["cwd"])
        self.assertTrue(wt.exists())
        self.assertEqual(wt, self.repo / ".orchestration/worktrees/p1-exec")
        run = next(c for c in self.calls() if c[0] == "run")
        argv = run[run.index("--") + 1:]
        self.assertEqual(argv[0], "env")
        self.assertTrue(any(a.startswith("PATH=") for a in argv))
        self.assertIn("--no-daemon", argv)
        self.assertIn("--add-dir", argv)
        self.assertIn(f'projects."{wt}".trust_level="trusted"', argv)
        self.assertIn("orch.task=p1-exec", run)
        contract = Path(t["contract"]).read_text()
        self.assertIn("Do not run git commit", contract)
        self.assertIn(t["report"], contract)

        # The worker's terminal is live inside the worktree: removal refused.
        with self.assertRaises(SystemExit) as e:
            self.run_orch("worktree", "remove", "p1-exec")
        self.assertIn("live terminals still inside", str(e.exception))

        # No report yet: still running, worker kept.
        rc, out = self.run_orch("collect", "p1-exec")
        self.assertEqual(json.loads(out)["state"], "running")

        (wt / "feature.txt").write_text("x\n")
        Path(t["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(t["report"]).write_text("# Report\n\nResult: complete\n")
        rc, out = self.run_orch("collect", "p1-exec")
        r = json.loads(out)
        self.assertEqual(r["state"], "complete", r)
        self.assertEqual(r["evidence"]["commits"], 1)
        self.assertTrue(Path(r["backup"]).exists())
        rc, _ = self.run_orch("worktree", "merge", "p1-exec")
        self.assertEqual(rc, 0)
        self.assertTrue((self.repo / "feature.txt").exists())
        self.assertTrue((self.repo / "docs/orch/p1-exec.md").exists())
        self.assertFalse(wt.exists())

    def test_report_is_committed_with_branch(self):
        rc, out = self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "p2", "--json")
        t = json.loads(out)
        Path(t["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(t["report"]).write_text("Result: complete\n")
        r = json.loads(self.run_orch("collect", "p2")[1])
        # The report itself is committed, so check the claim needs real work too.
        self.assertEqual(r["evidence"]["commits"], 1)

    def test_review_runs_in_root_and_records_decision(self):
        rc, out = self.run_orch("dispatch", self.task(), "--role", "review", "--id", "r1", "--json")
        t = json.loads(out)
        self.assertEqual(Path(t["cwd"]), self.repo)
        self.assertIsNone(t["branch"])
        self.assertTrue(t["independent"])
        log = (self.repo / ".orchestration/runtime/decisions.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(log[-1])["task"], "r1")

    def test_demanded_agent_must_be_eligible(self):
        (self.repo / ".orchestration/agents.local.toml").write_text(
            '[agents.codex]\nquota = "static"\nquota_static = {remaining_percent = 5}\n'
            '[agents.claude]\nquota = "static"\nquota_static = {remaining_percent = 90}\n')
        with self.assertRaises(SystemExit) as e:
            self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "x1", "--agent", "codex")
        self.assertIn("not eligible", str(e.exception))

    def test_running_task_not_redispatched(self):
        self.run_orch("dispatch", self.task(), "--role", "review", "--id", "dup")
        with self.assertRaises(SystemExit):
            self.run_orch("dispatch", self.task(), "--role", "review", "--id", "dup")

    def test_gsd_cross_ai_bridge(self):
        os.environ["FAKE_HC_WORKER"] = "complete"
        os.environ["FAKE_HC_TOUCH"] = "plan-output.txt"
        try:
            sys.stdin = io.StringIO("<objective>Do the plan</objective>\n")
            rc, out = self.run_orch("gsd-cross-ai")
        finally:
            sys.stdin = sys.__stdin__
            os.environ.pop("FAKE_HC_TOUCH")
        self.assertEqual(rc, 0, out)
        self.assertIn("# Summary", out)
        self.assertTrue((self.repo / "plan-output.txt").exists())

    def test_status_snapshot(self):
        self.run_orch("dispatch", self.task(), "--role", "review", "--id", "s1")
        rc, out = self.run_orch("status", "--json", "--no-planning")
        s = json.loads(out)
        self.assertEqual(s["routing"]["execute"]["selected"], "codex")
        self.assertEqual(s["tasks"][0]["id"], "s1")
        self.assertEqual(s["tasks"][0]["live"]["state"], "live")


if __name__ == "__main__":
    unittest.main(verbosity=1)
