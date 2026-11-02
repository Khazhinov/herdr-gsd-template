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
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC / "scripts"))
from orchlib import config, hc, quota, route, tasks  # noqa: E402

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
        self.assertIn("quota 70% (7d) - 15% this task = 55% > heavy reserve 30%", d["reason"])

    def test_reserve_must_survive_the_task(self):
        # Field case: 36% left, a heavy plan costs ~35%.
        qs = {"codex": q("codex", 36), "claude": q("claude", 80)}
        d = self.decide("execute", qs, costs={"codex/heavy": 35})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("quota 36% (7d) - 35% this task = 1% <= heavy reserve 30%", d["reason"])
        # Field case: a second parallel heavy task sees the first one's spend.
        d = self.decide("execute", {"codex": q("codex", 77), "claude": q("claude", 80)},
                        costs={"codex/heavy": 35}, pending={"codex": 35})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("- 35% running", d["reason"])

    def test_cost_is_capped_so_a_full_window_admits_one_task(self):
        d = self.decide("execute", {"codex": q("codex", 100), "claude": q("claude", 80)}, costs={"codex/heavy": 90})
        self.assertEqual(d["selected"], "codex")

    def test_codex_reserve_falls_back_to_claude(self):
        d = self.decide("execute", {"codex": q("codex", 25), "claude": q("claude", 80)})
        self.assertEqual(d["selected"], "claude")
        self.assertIn("codex (quota 25% (7d) - 15% this task = 10% <= heavy reserve 30%)", d["reason"])

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

    def test_each_window_and_account_cap(self):
        c = cfg()
        c["routing"]["accounts"] = {"codex": {"max_parallel": 1}}
        x = q("codex", 90)
        x["windows"].append({"name": "5h", "remaining_percent": 31, "resets_at": NOW + 3600})
        d = route.decide(c, "execute", {"codex": x, "claude": q("claude", 80)},
                         costs={"codex/heavy/5h": 5, "codex/heavy/7d": 2}, now=NOW)
        self.assertEqual(d["selected"], "claude")
        self.assertIn("(5h)", d["reason"])
        d = route.decide(c, "execute", {"codex": q("codex", 90), "claude": q("claude", 80)},
                         running={"account:codex": 1}, now=NOW)
        self.assertIn("account busy 1/1", d["reason"])

    def test_owner_reserve_and_author_account(self):
        c = cfg()
        d = route.decide(c, "execute", {"codex": q("codex", 10), "claude": q("claude", 38)}, now=NOW)
        self.assertIsNone(d["selected"])
        self.assertEqual(d["owner_quota"], {"7d": 38})
        d = route.decide(c, "review", {"codex": q("codex", 90), "claude": q("claude", 90)},
                         exclude_account="codex", now=NOW)
        self.assertEqual(d["selected"], "claude")
        self.assertTrue(d["independent"])
        d = route.decide(c, "review", {"codex": q("codex", 90), "claude": q("claude", 90)},
                         exclude_account="codex", override="codex", now=NOW)
        self.assertFalse(d["independent"])

    def test_stale_low_light_is_denied(self):
        d = self.decide("review", {"codex": q("codex", 5, stale=True), "claude": q("claude", 90)})
        self.assertEqual(d["selected"], "claude")

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
            self.assertIsNone(r["windows"][0]["remaining_percent"])
            self.assertIsNone(r["effective_remaining_percent"])
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

    def test_vendor_denial_and_static_reset(self):
        denied = dict(self.RPC, ordinaryUsageAllowed=False)
        r = quota.probe_codex(NOW, 1800, rpc=lambda: denied)
        self.assertEqual([w["remaining_percent"] for w in r["windows"]], [0.0, 0.0])
        denied = dict(self.RPC, rateLimits=dict(self.RPC["rateLimits"], rateLimitReachedType="primary"))
        self.assertEqual(quota.probe_codex(NOW, 1800, rpc=lambda: denied)["effective_remaining_percent"], 0)
        self.assertIsNone(quota.probe_static("x", {"remaining_percent": 50, "resets_at": NOW-1}, NOW)["effective_remaining_percent"])
        self.assertEqual(quota.probe_static("x", {"remaining_percent": 50, "resets_at": NOW-1,
                                                   "period_minutes": 60}, NOW)["effective_remaining_percent"], 50)

    def test_raw_cache_is_shared_but_gating_is_project_local(self):
        with tempfile.TemporaryDirectory() as td:
            old_dir, old_cache = quota.CACHE_DIR, quota.QUOTA_CACHE
            quota.CACHE_DIR = Path(td)
            quota.QUOTA_CACHE = Path(td) / "quotas.json"
            c = cfg()
            try:
                with mock.patch.object(quota, "probe_codex", return_value=quota.finish(quota.codex_from_rpc(self.RPC, NOW), 0, NOW)) as probe:
                    a = quota.all_quotas(c, max_age=9999999999)
                    c["agents"]["codex"]["quota_windows"] = ["5h"]
                    b = quota.all_quotas(c, max_age=9999999999)
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(a["codex"]["effective_remaining_percent"], 41)
                self.assertEqual(b["codex"]["effective_remaining_percent"], 73)
            finally:
                quota.CACHE_DIR, quota.QUOTA_CACHE = old_dir, old_cache

    def test_rpc_multiple_lines_in_one_read(self):
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / "rpc.py"
            script.write_text('import json, sys\nsys.stdout.write(json.dumps({"id":1,"result":{}})+"\\n"+json.dumps({"id":2,"result":{"ok":1}})+"\\n")\nsys.stdout.flush()\nsys.stdin.read()\n')
            self.assertEqual(quota.codex_rpc(timeout=2, argv=[sys.executable, str(script)]), {"ok": 1})

    def test_rpc_constructor_closes_failed_process(self):
        with mock.patch.object(hc.subprocess, "Popen") as popen, mock.patch.object(hc.RPC, "call", side_effect=hc.HCError("hello")):
            with self.assertRaises(hc.HCError):
                hc.RPC()
            popen.return_value.kill.assert_called_once()


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
        c["routing"]["owner"] = "kimi"
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

    def test_account_cap_and_static_period_validate(self):
        c = cfg()
        c["routing"]["accounts"] = {"codex": {"max_parallel": 0}}
        with self.assertRaisesRegex(config.ConfigError, "max_parallel"):
            config.validate(c)
        c["routing"]["accounts"]["codex"]["max_parallel"] = 1
        c["agents"]["codex"]["quota_static"] = {"period_minutes": 0}
        with self.assertRaisesRegex(config.ConfigError, "period_minutes"):
            config.validate(c)


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

    def test_quota_burn_is_measured_per_task(self):
        rc, out = self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "b1", "--json")
        t = json.loads(out)
        self.assertEqual(t["quota_start"], 80)
        (self.repo / ".orchestration/agents.local.toml").write_text(
            '[agents.codex]\nquota = "static"\nquota_static = {remaining_percent = 62}\n'
            '[agents.claude]\nquota = "static"\nquota_static = {remaining_percent = 90}\n')
        Path(t["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(t["report"]).write_text("# Report\n\nResult: complete\n")
        self.run_orch("collect", "b1")
        from orchlib import tasks
        c = config.load(self.repo)
        done = tasks.load_task(c, "b1")
        self.assertEqual((done["quota_burn"], done["quota_shared"]), ({"budget": 18.0}, False))
        self.assertEqual(tasks.costs(c), {"codex/heavy/budget": 18.0})
        rc, out = self.run_orch("route", "execute", "--json")
        self.assertIn("quota 62% (budget) - 18% this task = 44% > heavy reserve 30%", json.loads(out)["reason"])

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
        # Limits are shown per agent environment, not per model variant.
        self.assertEqual(sorted(s["providers"]), ["claude", "codex"])
        self.assertEqual(s["providers"]["codex"]["agents"], ["codex"])

    def test_account_ledger_serializes_concurrent_admission(self):
        c = config.load(self.repo)
        c["routing"]["accounts"] = {"codex": {"max_parallel": 1}}
        started, release = threading.Event(), threading.Event()
        results = []
        def launch(*args, **kwargs):
            if not started.is_set():
                started.set()
                release.wait(5)
            return {"address": "fake-admission"}
        def first():
            try:
                results.append(tasks.dispatch(c, self.task("one.md"), "review", "one"))
            except BaseException as e:
                results.append(e)
        with mock.patch.object(hc, "run", side_effect=launch), mock.patch.object(tasks, "startup_check", return_value={"ok": True}):
            worker = threading.Thread(target=first)
            worker.start()
            self.assertTrue(started.wait(5))
            second = tasks.dispatch(c, self.task("two.md"), "review", "two")
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results[0]["agent"], "codex")
        self.assertEqual(second["agent"], "claude")
        self.assertEqual({results[0]["agent"], second["agent"]}, {"codex", "claude"})

    def test_launch_failure_cleans_ledger_worktree_and_marks_failed(self):
        c = config.load(self.repo)
        with mock.patch.object(hc, "run", side_effect=hc.HCError("failed")):
            with self.assertRaises(hc.HCError):
                tasks.dispatch(c, self.task(), "execute", "bad-launch")
        self.assertEqual(tasks.load_task(c, "bad-launch")["state"], "failed")
        self.assertFalse(tasks.wt_paths(c, "bad-launch")[0].exists())
        self.assertEqual(tasks.ledger()["entries"], [])

    def test_pending_uses_earliest_account_start_once(self):
        c = config.load(self.repo)
        data = {"entries": [
            {"account": "codex", "project_root": str(self.repo), "task_id": "a", "agent": "codex",
             "started_at": 1, "quota_start": {"budget": 80}, "cost_estimate": {"budget": 15}},
            {"account": "codex", "project_root": "/other", "task_id": "b", "agent": "codex",
             "started_at": 2, "quota_start": {"budget": 75}, "cost_estimate": {"budget": 15}}], "samples": {}}
        quotas = {"codex": {"windows": [{"name": "budget", "remaining_percent": 65}]}}
        self.assertEqual(tasks.pending(c, quotas, {}, data), {"codex": {"budget": 15}})

    def test_window_burn_survives_other_window_reset_and_solo_median(self):
        c = config.load(self.repo)
        t = {"agent": "codex", "quota_start_windows": {"5h": 80, "7d": 60},
             "quota_resets": {"5h": NOW - 1, "7d": NOW + 1000}}
        reading = {"codex": {"windows": [{"name": "5h", "remaining_percent": None},
                                          {"name": "7d", "remaining_percent": 50}]}}
        with mock.patch.object(quota, "all_quotas", return_value=reading):
            self.assertEqual(tasks.quota_burn(c, t, NOW), {"7d": 10})
        data = {"entries": [], "samples": {"codex/heavy/7d": [1, 2, 3, 4, 5, 20]}}
        self.assertEqual(tasks.costs(c, data), {"codex/heavy/7d": 4})

    def test_collect_keep_worker_never_commits_and_planning_is_guarded(self):
        t = json.loads(self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "guard", "--json")[1])
        wt = Path(t["cwd"])
        report = Path(t["report"])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("Result: complete\n")
        (wt / "feature.txt").write_text("x\n")
        r = json.loads(self.run_orch("collect", "guard", "--keep-worker")[1])
        self.assertEqual(r["state"], "running")
        self.assertEqual(subprocess.check_output(["git", "-C", str(wt), "rev-list", "--count", "HEAD"], text=True).strip(), "1")
        (wt / ".planning").mkdir(exist_ok=True)
        (wt / ".planning" / "bad.md").write_text("bad")
        with self.assertRaisesRegex(SystemExit, "bad.md"):
            self.run_orch("collect", "guard")
        (wt / ".planning" / "bad.md").unlink()
        self.assertEqual(json.loads(self.run_orch("collect", "guard")[1])["state"], "complete")
        (self.repo / "feature.txt").write_text("untracked")
        with self.assertRaisesRegex(SystemExit, "untracked files"):
            self.run_orch("worktree", "merge", "guard")

    def test_replace_archives_collected_task_and_review_of_author(self):
        c = config.load(self.repo)
        author = json.loads(self.run_orch("dispatch", self.task(), "--role", "review", "--id", "author", "--json")[1])
        Path(author["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(author["report"]).write_text("Result: complete\n")
        self.run_orch("collect", "author")
        with self.assertRaisesRegex(SystemExit, "already exists"):
            self.run_orch("dispatch", self.task(), "--role", "review", "--id", "author")
        t = json.loads(self.run_orch("dispatch", self.task(), "--role", "review", "--id", "author", "--replace", "--of", "author", "--json")[1])
        self.assertEqual(t["agent"], "claude")
        self.assertTrue(t["independent"])
        self.assertTrue(list((tasks.runtime(c) / "archive").glob("author-*/author.json")))
        self.assertTrue(list((tasks.runtime(c) / "archive").glob("author-*/author.md")))

    def test_merge_preflight_rejects_conflicts_and_branch_planning(self):
        t = json.loads(self.run_orch("dispatch", self.task(), "--role", "execute", "--id", "merge-guard", "--json")[1])
        wt = Path(t["cwd"])
        (wt / "shared.txt").write_text("branch\n")
        Path(t["report"]).parent.mkdir(parents=True, exist_ok=True)
        Path(t["report"]).write_text("Result: complete\n")
        self.run_orch("collect", "merge-guard")
        (self.repo / "shared.txt").write_text("owner\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "shared.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "owner"], check=True)
        with self.assertRaisesRegex(SystemExit, "merge conflict"):
            self.run_orch("worktree", "merge", "merge-guard")
        self.assertTrue(wt.exists())
        (wt / ".planning").mkdir(exist_ok=True)
        (wt / ".planning" / "changed.md").write_text("bad")
        subprocess.run(["git", "-C", str(wt), "add", ".planning/changed.md"], check=True)
        subprocess.run(["git", "-C", str(wt), "commit", "-qm", "bad"], check=True)
        with self.assertRaisesRegex(SystemExit, "changed.md"):
            self.run_orch("worktree", "merge", "merge-guard")

    def test_ledger_prunes_missing_and_old_terminals(self):
        c = config.load(self.repo)
        with tasks.admission():
            data = tasks.ledger()
            data["entries"] = [
                {"account": "codex", "agent": "codex", "project_root": "/other", "task_id": "gone",
                 "started_at": NOW, "state": "running", "terminal": "absent"},
                {"account": "codex", "agent": "codex", "project_root": "/other", "task_id": "old",
                 "started_at": 1, "state": "starting"}]
            tasks.save_ledger(data)
        self.assertEqual(tasks.running_counts(c), {})


class ShellChecks(unittest.TestCase):
    def test_self_check_preserves_pycache_and_installer_accepts_worktree(self):
        script = (SRC / "scripts/self-check.sh").read_text()
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", script)
        self.assertNotIn("cleanup_pycache", script)
        with tempfile.TemporaryDirectory() as td:
            root, wt = Path(td) / "repo", Path(td) / "wt"
            root.mkdir()
            subprocess.run(["git", "-C", str(root), "init", "-q", "-b", "main"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "t@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "T"], check=True)
            (root / "seed").write_text("x")
            subprocess.run(["git", "-C", str(root), "add", "seed"], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "seed"], check=True)
            subprocess.run(["git", "-C", str(root), "worktree", "add", "-qb", "test", str(wt)], check=True)
            p = subprocess.run([str(SRC / "scripts/install-into-repo.sh"), str(wt)],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue((wt / "scripts/orch.py").exists())


if __name__ == "__main__":
    unittest.main(verbosity=1)
