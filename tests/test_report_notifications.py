import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from orchlib import hc, tasks


class ReportNotificationTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.cfg = {"root": Path(root.name)}
        self.owner = {"address": "t1", "state": "live", "status": {"state": "idle"}}
        self.worker = {
            "id": "review",
            "state": "running",
            "parent": "t1",
            "notify_owner": True,
            "started_at": 1,
            "sentinel": "Major issue: no",
            "startup_ok": True,
            "live": {"state": "live", "status": "done", "status_ms": 1},
        }

    def notify(self):
        tasks.notify_reports(self.cfg, [self.worker], [self.owner])

    @patch.object(hc, "send")
    def test_report_waits_for_the_original_owner_to_be_idle(self, send):
        other = {"address": "t2", "state": "live", "status": {"state": "idle"}}
        tasks.notify_reports(self.cfg, [self.worker], [other])
        self.owner["status"]["state"] = "working"
        self.notify()
        send.assert_not_called()

        self.owner["status"]["state"] = "done"
        self.notify()
        self.notify()
        send.assert_called_once_with(
            "t1", "Worker report ready for review. Run python3 scripts/orch.py collect review."
        )

    @patch.object(hc, "send")
    def test_parallel_reports_share_one_notification_per_owner(self, send):
        other_owner = {"address": "t2", "state": "live", "status": {"state": "idle"}}
        docs = dict(self.worker, id="docs")
        lint = dict(self.worker, id="lint", parent="t2")
        followup = dict(self.worker, id="followup", sentinel=None,
                        live={"state": "live", "status": "working"})
        records = [self.worker, docs, lint, followup]
        terminals = [self.owner, other_owner]

        tasks.notify_reports(self.cfg, records, terminals)
        tasks.notify_reports(self.cfg, records, terminals)
        self.assertEqual(send.call_count, 2)
        owner, message = send.call_args_list[0].args
        self.assertEqual(owner, "t1")
        self.assertIn("collect review.", message)
        self.assertIn("collect docs.", message)
        self.assertNotIn("followup", message)
        self.assertNotIn("lint", message)
        self.assertEqual(send.call_args_list[1].args[0], "t2")

        followup["sentinel"] = "Result: complete"
        self.owner["status"]["state"] = "working"
        tasks.notify_reports(self.cfg, records, terminals)
        self.assertEqual(send.call_count, 2)
        self.owner["status"]["state"] = "idle"
        tasks.notify_reports(self.cfg, records, terminals)
        self.assertEqual(send.call_count, 3)
        send.assert_called_with(
            "t1", "Worker report ready for followup. Run python3 scripts/orch.py collect followup."
        )

    @patch.object(hc, "send")
    def test_blocker_followed_by_report_and_reused_task_id(self, send):
        self.worker.update(sentinel=None, live={"state": "live", "status": "blocked", "status_ms": 2})
        self.notify()
        self.notify()
        send.assert_called_once_with("t1", "Worker for review reported blocked. Check its Herdr tab.")

        self.worker["sentinel"] = "Result: incomplete"
        self.notify()
        self.notify()
        self.assertEqual(send.call_count, 2)

        self.worker["started_at"] = 3
        self.notify()
        self.assertEqual(send.call_count, 3)

    @patch.object(hc, "send")
    def test_worker_exit_without_a_report_wakes_owner_once(self, send):
        self.worker.update(sentinel=None, live={"state": "finished"})
        self.notify()
        self.notify()
        send.assert_called_once_with(
            "t1", "Worker for review exited without a report. Check the dispatch and collect its status."
        )

    @patch.object(hc, "send")
    def test_completed_turn_without_a_report_wakes_owner_once(self, send):
        self.worker.update(sentinel=None, startup_ok=False,
                           live={"state": "live", "status": "done", "turn": 0})
        self.notify()
        send.assert_not_called()

        self.worker["live"]["turn"] = 1
        self.notify()
        self.notify()
        send.assert_called_once_with(
            "t1", "Worker for review finished its turn without a report. Check its Herdr tab."
        )

        self.worker["sentinel"] = "Result: incomplete"
        self.notify()
        self.notify()
        self.assertEqual(send.call_count, 2)
        send.assert_called_with(
            "t1", "Worker report ready for review. Run python3 scripts/orch.py collect review."
        )

    @patch.object(hc, "send")
    def test_no_wake_for_startup_block_or_closed_owner(self, send):
        self.worker.update(sentinel=None, startup_ok=False,
                           live={"state": "live", "status": "blocked", "status_ms": 2})
        self.notify()
        self.owner["state"] = "finished"
        self.worker["sentinel"] = "Result: complete"
        self.notify()
        send.assert_not_called()

    @patch.object(hc, "send")
    def test_delivery_error_leaves_report_available_for_retry(self, send):
        send.side_effect = [hc.HCError("unavailable"), {"turn": 1}]
        with contextlib.redirect_stderr(io.StringIO()):
            self.notify()
        self.notify()
        self.notify()
        self.assertEqual(send.call_count, 2)
