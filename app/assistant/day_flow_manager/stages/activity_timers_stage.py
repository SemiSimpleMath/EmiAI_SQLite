"""
Activity Timers Stage

Purpose:
- Periodically refresh resource_tracked_activities_output.json so minutes_since advances
- Does NOT call any agent or change activity timestamps/counters
"""

from __future__ import annotations

from typing import Any, Dict

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult

logger = get_logger(__name__)


class ActivityTimersStage(BaseStage):
    stage_id: str = "activity_timers"

    def _output_filename(self) -> str:
        return "resource_tracked_activities_output.json"

    def run(self, ctx: StageContext) -> StageResult:
        try:
            from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder

            recorder = ActivityRecorder(ctx.state)
            recorder.write_output_resource(now_utc=ctx.now_utc)
            payload = recorder.build_output_payload(now_utc=ctx.now_utc)
        except Exception as e:
            logger.warning(f"ActivityTimersStage: refresh failed: {e}")
            return StageResult(output={"error": str(e)}, debug={"refreshed": False})

        return StageResult(
            output=payload if isinstance(payload, dict) else {"refreshed": True},
            debug={"refreshed": True},
        )
