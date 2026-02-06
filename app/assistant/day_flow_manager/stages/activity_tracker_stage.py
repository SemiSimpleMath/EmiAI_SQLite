"""
Activity Tracker Stage

Purpose:
- Process accepted tickets and update tracked activity counts
- Optionally call activity_tracker agent if new chat affects counts
- Handle AFK-based resets for activities configured with reset_on_afk
- Refresh resource_tracked_activities_output.json so minutes_since advances
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.day_flow_manager import BaseStage, StageContext, StageResult
from app.assistant.utils.chat_formatting import messages_to_chat_excerpts

logger = get_logger(__name__)


class ActivityTrackerStage(BaseStage):
    stage_id: str = "activity_tracker"

    def _output_filename(self) -> str:
        return "resource_tracked_activities_output.json"

    def _parse_iso_utc(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _get_afk_snapshot(self, ctx: StageContext) -> Dict[str, Any]:
        """
        Get current AFK status from AFKMonitor.

        Strict contract: no fallbacks. If AFKMonitor is unavailable or returns
        an invalid payload, raise loudly so the pipeline fails fast.
        """
        from app.assistant.ServiceLocator.service_locator import DI

        monitor = getattr(DI, "afk_monitor", None)
        if monitor is None:
            logger.error("ActivityTrackerStage: DI.afk_monitor is missing (strict mode)")
            raise RuntimeError("AFKMonitor missing: DI.afk_monitor is None")

        snapshot = monitor.get_computer_activity()
        if not isinstance(snapshot, dict):
            logger.error("ActivityTrackerStage: AFKMonitor returned non-dict snapshot (strict mode)")
            raise RuntimeError(f"AFKMonitor returned invalid snapshot type: {type(snapshot)}")

        # Enforce presence of stable API keys. Values may be None, but keys must exist.
        if "last_afk_return_utc" not in snapshot:
            logger.error("ActivityTrackerStage: snapshot missing 'last_afk_return_utc' (strict mode)")
            raise RuntimeError("AFKMonitor snapshot missing required key: last_afk_return_utc")

        return snapshot

    def _get_last_run_utc(self, ctx: StageContext) -> Optional[datetime]:
        """Get this stage's last run timestamp from state."""
        stage_runs = ctx.state.get("stage_runs", {})
        stage_info = stage_runs.get(self.stage_id, {}) or {}
        return self._parse_iso_utc(stage_info.get("last_run_utc"))

    def _get_last_afk_reset_utc(self, ctx: StageContext) -> Optional[datetime]:
        """Get timestamp of last AFK reset we performed."""
        stage_runs = ctx.state.get("stage_runs", {})
        stage_info = stage_runs.get(self.stage_id, {}) or {}
        return self._parse_iso_utc(stage_info.get("last_afk_reset_utc"))

    def _set_last_afk_reset_utc(self, ctx: StageContext, dt: datetime) -> None:
        """Record when we last performed an AFK reset."""
        if "stage_runs" not in ctx.state:
            ctx.state["stage_runs"] = {}
        if self.stage_id not in ctx.state["stage_runs"]:
            ctx.state["stage_runs"][self.stage_id] = {}
        ctx.state["stage_runs"][self.stage_id]["last_afk_reset_utc"] = dt.isoformat()

    def _get_recent_chat_since(self, cutoff_utc: datetime, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Activity-tracker policy:
        - use stage's last_run_utc as cutoff
        - default chat filters apply (no commands, no injections, no summaries)
        - return excerpt dicts for the activity_tracker agent
        """
        try:
            from app.assistant.ServiceLocator.service_locator import DI

            msgs = DI.global_blackboard.get_recent_chat_since_utc(
                cutoff_utc,
                limit=limit,
                # Activity tracking doesn't need long messages; keep short.
                content_limit=250,
            )
            return messages_to_chat_excerpts(msgs)
        except Exception:
            return []


    def _get_unprocessed_accepted_tickets(self) -> List[Any]:
        """
        Get ACCEPTED day_flow tickets that haven't been processed yet.
        Returns raw ticket objects so we can mark them as processed.
        """
        from app.assistant.ticket_manager import get_ticket_manager, TicketState

        try:
            return get_ticket_manager().get_tickets(
                ticket_type="day_flow",
                state=TicketState.ACCEPTED,
                effects_processed=0,
            )
        except Exception:
            logger.warning("Could not get accepted tickets", exc_info=True)
            return []


    def _get_afk_intervals_since(self, since_utc: datetime, until_utc: datetime) -> List[Dict[str, Any]]:
        """Get AFK intervals that occurred between since_utc and until_utc."""
        try:
            from app.assistant.afk_manager.afk_statistics import get_afk_intervals_overlapping_range
            return get_afk_intervals_overlapping_range(since_utc, until_utc)
        except Exception as e:
            logger.warning(f"Could not get AFK intervals: {e}")
            return []

    def _get_activity_recorder(self, ctx: StageContext):
        """Get ActivityRecorder instance."""
        from app.assistant.day_flow_manager.activity_recorder import ActivityRecorder
        return ActivityRecorder(ctx.state)

    def _get_current_counts(self, recorder) -> Dict[str, int]:
        """Get current activity counts from recorder."""
        state = recorder.get_state()
        activities = state.get("activities", {})
        return {
            field_name: data.get("count_today", 0)
            for field_name, data in activities.items()
        }

    def should_run_stage(self, ctx: StageContext) -> Tuple[bool, str]:
        """Check if stage should run based on interval and AFK guard."""
        stage_cfg = self.get_stage_config(ctx)
        run_policy = stage_cfg.get("run_policy", {}) if isinstance(stage_cfg, dict) else {}
        min_interval = int(run_policy.get("min_interval_seconds", 60))

        last_run_utc = self._get_last_run_utc(ctx)
        if last_run_utc:
            elapsed = (ctx.now_utc - last_run_utc).total_seconds()
            if elapsed < min_interval:
                remaining = int(min_interval - elapsed)
                return False, f"interval={remaining}s remaining"

        afk_guard = stage_cfg.get("afk_guard", {}) if isinstance(stage_cfg, dict) else {}
        if isinstance(afk_guard, dict):
            snapshot = self._get_afk_snapshot(ctx)
            is_afk = bool(snapshot.get("is_afk", False))
            is_potentially_afk = bool(snapshot.get("is_potentially_afk", False))
            if afk_guard.get("skip_when_afk") and is_afk:
                return False, "afk_guard=afk"
            if afk_guard.get("skip_when_potentially_afk") and is_potentially_afk:
                return False, "afk_guard=potentially_afk"

        return True, "ready"

    def run(self, ctx: StageContext) -> StageResult:
        """
        Main run logic:
        1. Get accepted tickets since last run, update counts for tracked activities, mark as processed
        2. If new chat exists, call activity_tracker agent to detect count adjustments
        3. Check for AFK events and reset applicable timers
        4. Write output resource
        """
        now_utc = ctx.now_utc
        last_run_utc = self._get_last_run_utc(ctx)
        
        # Use a reasonable fallback if this is first run (e.g., 1 hour ago)
        if not last_run_utc:
            last_run_utc = now_utc - timedelta(hours=1)

        logger.debug(f"ActivityTrackerStage: running (last_run={last_run_utc.isoformat()})")

        recorder = self._get_activity_recorder(ctx)
        debug_info: Dict[str, Any] = {
            "last_run_utc": last_run_utc.isoformat(),
            "tickets_found": 0,
            "chat_messages": 0,
            "agent_called": False,
            "afk_reset_triggered": False,
        }

        # Step 1: Get accepted tickets since last run and update counts for tracked activities
        from app.assistant.ticket_manager import get_ticket_manager
        ticket_manager = get_ticket_manager()
        
        accepted_tickets = self._get_unprocessed_accepted_tickets()
        debug_info["tickets_found"] = len(accepted_tickets)
        
        for ticket in accepted_tickets:
            responded_at = ticket.responded_at or now_utc
            
            # status_effect is a list like ["finger_stretch", "coffee"]
            status_effect = ticket.status_effect or []
            if isinstance(status_effect, list):
                for activity_name in status_effect:
                    if activity_name in recorder._defs:
                        recorder.record_occurrence(activity_name, timestamp_utc=responded_at)
                        logger.info(f"ActivityTracker: recorded {activity_name} from ticket {ticket.ticket_id}")
            
            # Mark ticket as processed regardless of whether it's a tracked activity
            ticket_manager.mark_ticket_processed(ticket.id)

        # Step 2: Check for recent chat and optionally call activity_tracker agent
        recent_chat = self._get_recent_chat_since(last_run_utc)
        debug_info["chat_messages"] = len(recent_chat)

        if recent_chat:
            # Call activity_tracker agent to analyze chat for count adjustments
            try:
                from app.assistant.ServiceLocator.service_locator import DI
                from app.assistant.utils.pydantic_classes import Message

                agent = DI.agent_factory.create_agent("activity_tracker")
                current_counts = self._get_current_counts(recorder)

                agent_input: Dict[str, Any] = {
                    "current_activity_counts": current_counts,
                    "recent_chat": recent_chat,
                }

                output = agent.action_handler(Message(agent_input=agent_input)).data
                debug_info["agent_called"] = True

                # Process agent output - it may provide updated counts
                if isinstance(output, dict):
                    activity_updates = output.get("activity_counts") or output.get("activities") or {}
                    for field_name, new_count in activity_updates.items():
                        if field_name in recorder._defs and isinstance(new_count, int):
                            current = current_counts.get(field_name, 0)
                            if new_count != current:
                                recorder.set_count_today(field_name, new_count)
                                logger.debug(f"ActivityTracker: agent adjusted {field_name}: {current} -> {new_count}")

            except Exception as e:
                logger.warning(f"ActivityTracker: agent call failed: {e}")

        # Step 3: Reset applicable timers based on AFKMonitor state.
        #
        # Policy:
        # - Use stable AFK API timestamp: last_afk_return_utc
        # - Stage stores its own cursor last_afk_reset_utc
        # - If last_afk_return_utc > last_afk_reset_utc => new AFK segment completed => reset
        #
        # This keeps "time since" timers consistent with presence session boundaries.
        last_afk_reset_utc = self._get_last_afk_reset_utc(ctx)
        reset_dt = None
        reset_reason = None
        snapshot = self._get_afk_snapshot(ctx)
        last_return_iso = snapshot.get("last_afk_return_utc")
        dt_return = self._parse_iso_utc(last_return_iso) if isinstance(last_return_iso, str) else None
        if dt_return:
            reset_dt = dt_return
            reset_reason = "afk_return_utc"

        if reset_dt and (last_afk_reset_utc is None or reset_dt > last_afk_reset_utc):
            recorder.reset_on_afk_return(timestamp_utc=reset_dt)
            self._set_last_afk_reset_utc(ctx, reset_dt)
            debug_info["afk_reset_triggered"] = True
            debug_info["afk_reset_at"] = reset_dt.isoformat()
            debug_info["afk_reset_reason"] = reset_reason
            logger.debug(f"ActivityTracker: AFK reset triggered ({reset_reason}) at {reset_dt.isoformat()}")

        # Step 4: Write output resource (this also updates minutes_since for all activities)
        recorder.write_output_resource(now_utc=now_utc)

        output = {
            "last_run_utc": now_utc.isoformat(),
            "status": "ok",
        }

        return StageResult(
            output=output,
            debug=debug_info,
        )

    def reset_stage(self, ctx: StageContext) -> None:
        """
        Reset at daily boundary (5 AM):
        - All tracked quantities set to 0
        - Clear last_afk_reset_utc so new day starts fresh
        """
        recorder = self._get_activity_recorder(ctx)
        
        # Get the day_start_time from state if available, otherwise use current time
        day_start = ctx.state.get("day_start_time")
        if day_start:
            day_start_dt = self._parse_iso_utc(day_start)
            if day_start_dt:
                day_local_str = day_start_dt.strftime("%Y-%m-%d")
            else:
                day_local_str = ctx.now_utc.strftime("%Y-%m-%d")
        else:
            day_local_str = ctx.now_utc.strftime("%Y-%m-%d")

        recorder.reset_for_new_day(day_local_str)
        recorder.write_output_resource(now_utc=ctx.now_utc)
        
        # Clear last_afk_reset_utc so new day handles AFK returns fresh
        if "stage_runs" in ctx.state and self.stage_id in ctx.state["stage_runs"]:
            ctx.state["stage_runs"][self.stage_id].pop("last_afk_reset_utc", None)
        
        logger.info(f"ActivityTrackerStage: reset for new day {day_local_str}")
