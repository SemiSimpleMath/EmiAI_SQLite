import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

# Ensure repo root is on sys.path when running this file directly.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class _FakeRecorder:
    def __init__(self):
        self.reset_called_with = None
        self._defs = {}

    def get_state(self):
        return {"activities": {}}

    def reset_on_afk_return(self, timestamp_utc=None):
        self.reset_called_with = timestamp_utc

    def write_output_resource(self, now_utc=None):
        # no-op for unit test (avoid filesystem writes)
        return None


class ActivityTrackerAfkDbFallbackTest(unittest.TestCase):
    def test_resets_using_stable_last_afk_return_utc(self):
        from app.assistant.day_flow_manager.day_flow_manager import StageContext
        from app.assistant.day_flow_manager.stages.activity_tracker_stage import ActivityTrackerStage
        from app.assistant.ServiceLocator import service_locator

        now_utc = datetime.now(timezone.utc)
        now_local = now_utc
        last_run_utc = now_utc - timedelta(minutes=10)

        state = {
            "stage_runs": {
                "activity_tracker": {"last_run_utc": last_run_utc.isoformat()},
            }
        }

        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_local,
            state=state,
            config={},
            stage_config={},
            resources_dir=None,
        )

        stage = ActivityTrackerStage()
        fake_recorder = _FakeRecorder()

        stage._get_unprocessed_accepted_tickets = lambda: []
        stage._get_recent_chat_since = lambda *_args, **_kwargs: []
        stage._get_activity_recorder = lambda _ctx: fake_recorder
        stage._get_afk_intervals_since = lambda *_args, **_kwargs: []  # ensure we rely on snapshot

        # Provide a stable return timestamp (the pattern we want).
        return_dt = now_utc - timedelta(minutes=2)

        class _FakeMonitor:
            def get_computer_activity(self_inner):
                return {"is_afk": False, "last_afk_return_utc": return_dt.isoformat()}

        # Monkeypatch DI.afk_monitor for this test only.
        old_di = service_locator.DI
        try:
            class _FakeDI:
                afk_monitor = _FakeMonitor()

            service_locator.DI = _FakeDI()  # type: ignore[assignment]
            stage.run(ctx)
        finally:
            service_locator.DI = old_di  # type: ignore[assignment]

        self.assertIsNotNone(fake_recorder.reset_called_with)
        self.assertEqual(fake_recorder.reset_called_with.isoformat(), return_dt.isoformat())

    def test_raises_loudly_if_last_afk_return_key_missing(self):
        from app.assistant.day_flow_manager.day_flow_manager import StageContext
        from app.assistant.day_flow_manager.stages.activity_tracker_stage import ActivityTrackerStage
        from app.assistant.ServiceLocator import service_locator

        now_utc = datetime.now(timezone.utc)
        ctx = StageContext(
            now_utc=now_utc,
            now_local=now_utc,
            state={"stage_runs": {"activity_tracker": {"last_run_utc": (now_utc - timedelta(minutes=10)).isoformat()}}},
            config={},
            stage_config={},
            resources_dir=None,
        )

        stage = ActivityTrackerStage()
        stage._get_unprocessed_accepted_tickets = lambda: []
        stage._get_recent_chat_since = lambda *_args, **_kwargs: []
        stage._get_activity_recorder = lambda _ctx: _FakeRecorder()

        class _BadMonitor:
            def get_computer_activity(self_inner):
                # Missing the required stable key.
                return {"is_afk": False}

        old_di = service_locator.DI
        try:
            class _FakeDI:
                afk_monitor = _BadMonitor()

            service_locator.DI = _FakeDI()  # type: ignore[assignment]
            with self.assertRaises(RuntimeError):
                stage.run(ctx)
        finally:
            service_locator.DI = old_di  # type: ignore[assignment]


class StageRunsPreserveExtrasTest(unittest.TestCase):
    def test_record_stage_run_preserves_extra_keys(self):
        from app.assistant.day_flow_manager.day_flow_manager import PhysicalPipelineManager

        mgr = PhysicalPipelineManager.__new__(PhysicalPipelineManager)
        mgr.state = {
            "stage_runs": {
                "activity_tracker": {"last_afk_reset_utc": "2026-02-04T00:00:00+00:00"}
            }
        }

        now = datetime(2026, 2, 4, 12, 0, 0, tzinfo=timezone.utc)
        # Call the method under test (it only mutates mgr.state and marks dirty).
        mgr._mark_dirty = lambda: None
        mgr._record_stage_run("activity_tracker", now, "ready", debug=None)

        info = mgr.state["stage_runs"]["activity_tracker"]
        self.assertEqual(info.get("last_afk_reset_utc"), "2026-02-04T00:00:00+00:00")
        self.assertEqual(info.get("last_run_utc"), now.isoformat())


if __name__ == "__main__":
    unittest.main()

