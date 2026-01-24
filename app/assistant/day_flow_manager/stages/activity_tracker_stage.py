# stages/activity_tracker_stage.py
"""
Activity Tracker Stage

Flow:
1. Prepare inputs: current activity counts, recent chat, calendar events, accepted tickets
2. Execute: Run activity_tracker agent to detect activities from chat/calendar/tickets
3. Output: Apply agent output to activity_recorder, write resource_activity_tracker_output.json
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    get_calendar_events_completed,
    get_recently_accepted_tickets,
)

logger = get_logger(__name__)


class ActivityTrackerStage(BaseStage):
    """
    Pipeline stage that runs the activity_tracker agent to detect
    activities from chat, calendar events, and accepted tickets.
    """

    stage_id: str = "activity_tracker"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    # -------------------------------------------------------------------------
    # Input gathering
    # -------------------------------------------------------------------------

    def _get_current_activity_counts(self, state: Dict[str, Any]) -> Dict[str, int]:
        """Get current activity counts from activity_recorder."""
        try:
            from app.assistant.day_flow_manager.activity_recorder import (
                ActivityRecorder,
            )
            
            # Load activity state from pipeline state or create fresh
            # ActivityRecorder needs a status_data dict
            recorder = ActivityRecorder(state)
            state = recorder.get_state()
            
            counts = {}
            activities = state.get("activities", {})
            for field_name, data in activities.items():
                counts[field_name] = data.get("count_today", 0)
            
            return counts
        except Exception as e:
            logger.warning(f"Could not get activity counts: {e}")
            return {}

    def _get_activity_reset_info(self, state: Dict[str, Any], now_utc: datetime) -> Dict[str, Any]:
        """Get last reset timestamps and minutes since reset per activity."""
        try:
            from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder

            recorder = ActivityRecorder(state)
            payload = recorder.build_output_payload(now_utc=now_utc)
            activities = payload.get("activities", {}) if isinstance(payload, dict) else {}

            reset_info: Dict[str, Any] = {}
            for field_name, data in activities.items():
                if not isinstance(data, dict):
                    continue
                reset_info[field_name] = {
                    "last_reset_utc": data.get("last_reset_utc"),
                    "minutes_since_reset": data.get("minutes_since_reset"),
                    "last_reset_reason": data.get("last_reset_reason"),
                }
            return reset_info
        except Exception as e:
            logger.warning(f"Could not get activity reset info: {e}")
            return {}

    # Calendar/tickets helpers live in utils.context_sources

    def _format_chat_excerpts(self, chat_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format chat messages for agent input."""
        excerpts = []
        for msg in chat_messages:
            excerpts.append({
                "time_local": msg.get("time_local", ""),
                "sender": msg.get("sender", ""),
                "content": msg.get("content", ""),
            })
        return excerpts

    # -------------------------------------------------------------------------
    # Agent call
    # -------------------------------------------------------------------------

    def _call_agent(self, agent_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the activity_tracker agent."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message
            
            agent = DI.agent_factory.create_agent("activity_tracker")
            result = agent.action_handler(Message(agent_input=agent_input))
            
            if hasattr(result, "data") and isinstance(result.data, dict):
                return result.data
            elif isinstance(result, dict):
                return result
            else:
                return {"result": str(result)}
                
        except Exception as e:
            logger.error(f"Error calling activity_tracker agent: {e}")
            return None

    # -------------------------------------------------------------------------
    # Output application
    # -------------------------------------------------------------------------

    def _apply_agent_output(self, output: Dict[str, Any], now_utc: datetime, state: Dict[str, Any]) -> None:
        """Apply agent output to activity_recorder."""
        try:
            from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder
            
            recorder = ActivityRecorder(state)
            
            # Apply activity counts
            activity_counts = output.get("activity_counts", {})
            for field_name, count in activity_counts.items():
                if isinstance(count, int) and count >= 0:
                    recorder.set_count_today(field_name, count)
            
            # Reset activities that occurred
            activities_to_reset = output.get("activities_to_reset", [])
            if activities_to_reset:
                for field_name in activities_to_reset:
                    recorder.record_occurrence(field_name, timestamp_utc=now_utc, increment_count=False)
            
            # Write the output resource file
            recorder.write_output_resource(now_utc=now_utc)
            
        except Exception as e:
            logger.error(f"Error applying agent output: {e}")

    # -------------------------------------------------------------------------
    # Main run
    # -------------------------------------------------------------------------

    def run(self, ctx: StageContext) -> StageResult:
        """
        1. Prepare inputs
        2. Execute agent
        3. Output
        """
        # Step 1: Prepare inputs
        current_counts = self._get_current_activity_counts(ctx.state)
        chat_excerpts = self._format_chat_excerpts(ctx.new_chat_messages or [])
        calendar_completed = get_calendar_events_completed(hours=4)
        accepted_tickets = get_recently_accepted_tickets(hours=2)
        
        # Build agent input
        agent_input: Dict[str, Any] = {
            "current_activity_counts": current_counts,
            "recent_chat_excerpts": chat_excerpts,
            "calendar_events_completed": calendar_completed,
            "recent_accepted_tickets": accepted_tickets,
        }
        
        # Step 2: Execute agent
        output = self._call_agent(agent_input)
        
        if not output:
            logger.warning("ActivityTrackerStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={"chat_count": len(chat_excerpts)},
            )
        
        # Step 3: Apply output and write resource
        self._apply_agent_output(output, ctx.now_utc, ctx.state)
        
        # Build stage output (LOCAL time for display)
        now_local = ctx.now_local
        reset_info = self._get_activity_reset_info(ctx.state, ctx.now_utc)
        stage_output: Dict[str, Any] = {
            "activity_counts": output.get("activity_counts", {}),
            "activities_reset": output.get("activities_to_reset", []),
            "activity_resets": reset_info,
            "sleep_events": output.get("sleep_events", []),
            "wake_segments": output.get("wake_segments", []),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
        }
        
        # Write stage output
        ctx.write_resource(self._output_filename(), stage_output)
        
        logger.info(
            f"ActivityTrackerStage: counts={output.get('activity_counts', {})}, "
            f"reset={output.get('activities_to_reset', [])}"
        )
        
        return StageResult(
            output=stage_output,
            debug={
                "chat_messages_processed": len(chat_excerpts),
                "calendar_events": len(calendar_completed),
                "tickets_processed": len(accepted_tickets),
            },
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """Reset activity counts at 5AM boundary using defaults from config."""
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {})
        defaults = daily_reset.get("output_resource_defaults", {})
        
        now_local = ctx.now_local
        
        # Write stage output with defaults (all counts to 0, all minutes_since to 0)
        default_data: Dict[str, Any] = {
            "activity_counts": defaults.get("activity_counts", {
                "finger_stretch": 0,
                "standing_break": 0,
                "hydration": 0,
                "coffee": 0,
                "meal": 0,
                "snack": 0,
            }),
            "minutes_since": defaults.get("minutes_since", {
                "finger_stretch": 0,
                "standing_break": 0,
                "hydration": 0,
                "coffee": 0,
                "meal": 0,
                "snack": 0,
            }),
            "activities_reset": defaults.get("activities_reset", []),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "daily_boundary",
        }
        
        ctx.write_resource(self._output_filename(), default_data)
        
        # Also reset the activity recorder
        try:
            from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder
            
            recorder = ActivityRecorder(ctx.state)
            
            boundary_date = now_local.strftime("%Y-%m-%d")
            recorder.reset_for_new_day(boundary_date)
            recorder.write_output_resource(now_utc=ctx.now_utc)
        except Exception as e:
            logger.warning(f"ActivityRecorder reset warning: {e}")
        
        logger.info("ActivityTrackerStage: Daily reset complete")
