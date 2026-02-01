# stages/daily_context_generator_stage.py
"""
Daily Context Generator Stage

Flow:
1. Load stage config, check gate conditions
2. Prepare inputs: Build context items (calendar, chat, tickets, AFK intervals)
3. Execute: Run daily_context_tracker agent
4. Output: Write resource_daily_context_generator_output.json

Notes:
- This is an agent-based stage (calls LLM) so it should be gated by AFK and interval.
- Output includes both LOCAL display strings and UTC ISO strings for downstream math.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.day_flow_manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    get_calendar_events_upcoming_for_daily_context,
    get_calendar_events_completed,
    get_current_presence_status,
    get_significant_activity_segments,
    get_responded_tickets_categorized,
)
from app.assistant.utils.chat_formatting import messages_to_chat_excerpts

logger = get_logger(__name__)


class DailyContextGeneratorStage(BaseStage):
    """
    Pipeline stage that runs the daily_context_tracker agent to generate
    daily context summary (what's happening today, user's state, etc.)
    """

    stage_id: str = "daily_context_generator"

    # -------------------------------------------------------------------------
    # Config & Cursor
    # -------------------------------------------------------------------------

    def _output_filename(self) -> str:
        return "resource_daily_context_generator_output.json"

    def _parse_iso_utc(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    def _get_last_run_utc(self, ctx: StageContext) -> Optional[datetime]:
        """Get this stage's last run timestamp from state."""
        stage_runs = ctx.state.get("stage_runs", {})
        stage_info = stage_runs.get(self.stage_id, {}) or {}
        return self._parse_iso_utc(stage_info.get("last_run_utc"))

    def _get_afk_snapshot(self) -> Dict[str, Any]:
        """Best-effort realtime snapshot from AFKMonitor."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            monitor = getattr(DI, "afk_monitor", None)
            if monitor is None:
                return {}
            snapshot = monitor.get_computer_activity()
            return snapshot if isinstance(snapshot, dict) else {}
        except Exception:
            return {}

    # -------------------------------------------------------------------------
    # Gate Logic
    # -------------------------------------------------------------------------

    def should_run_stage(self, ctx: StageContext) -> Tuple[bool, str]:
        """Check if stage should run based on interval and AFK guard."""
        stage_cfg = self.get_stage_config(ctx)
        run_policy = stage_cfg.get("run_policy", {}) if isinstance(stage_cfg, dict) else {}
        min_interval = int(run_policy.get("min_interval_seconds", 300))  # Default 5 min for agent stages

        last_run_utc = self._get_last_run_utc(ctx)
        if last_run_utc:
            elapsed = (ctx.now_utc - last_run_utc).total_seconds()
            if elapsed < min_interval:
                remaining = int(min_interval - elapsed)
                return False, f"interval={remaining}s remaining"

        afk_guard = stage_cfg.get("afk_guard", {}) if isinstance(stage_cfg, dict) else {}
        if isinstance(afk_guard, dict):
            snapshot = self._get_afk_snapshot()
            is_afk = bool(snapshot.get("is_afk", False))
            is_potentially_afk = bool(snapshot.get("is_potentially_afk", False))
            if afk_guard.get("skip_when_afk", True) and is_afk:
                return False, "afk_guard=afk"
            if afk_guard.get("skip_when_potentially_afk", False) and is_potentially_afk:
                return False, "afk_guard=potentially_afk"

        return True, "ready"

    # -------------------------------------------------------------------------
    # Context building helpers
    # -------------------------------------------------------------------------

    def _get_current_daily_context(self, ctx: StageContext) -> Dict[str, Any]:
        """Get current daily context from previous stage output."""
        try:
            existing = ctx.read_resource(self._output_filename())
            if existing and existing.get("date") == ctx.now_local.strftime("%Y-%m-%d"):
                return existing
            return {"expected_schedule": "", "day_theme": "", "milestones": [], "current_status": ""}
        except Exception:
            return {"expected_schedule": "", "day_theme": "", "milestones": [], "current_status": ""}

    def _get_daily_context_mode(self, current_context: Dict[str, Any], ctx: StageContext) -> str:
        """Determine if we should rebuild or incrementally update."""
        if not current_context.get("day_theme"):
            return "rebuild"
        if current_context.get("date") != ctx.now_local.strftime("%Y-%m-%d"):
            return "rebuild"
        return "incremental"

    # -------------------------------------------------------------------------
    # Agent call
    # -------------------------------------------------------------------------

    def _call_agent(self, agent_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the daily_context_tracker agent."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message

            agent = DI.agent_factory.create_agent("daily_context_tracker")
            result = agent.action_handler(Message(agent_input=agent_input))

            if hasattr(result, "data") and isinstance(result.data, dict):
                return result.data
            elif isinstance(result, dict):
                return result
            else:
                return {"result": str(result)}

        except Exception as e:
            logger.error(f"Error calling daily_context_tracker agent: {e}")
            return None


    # -------------------------------------------------------------------------
    # Main run
    # -------------------------------------------------------------------------

    def run(self, ctx: StageContext) -> StageResult:
        """
        1. Prepare inputs - build context items
        2. Execute agent
        3. Output
        """
        now_utc = ctx.now_utc
        now_local = ctx.now_local

        # Step 1: Build context items that the agent needs
        stage_config = self.get_stage_config(ctx)
        lookbacks = stage_config.get("lookback_hours", {}) if isinstance(stage_config, dict) else {}
        calendar_upcoming_hours = int(lookbacks.get("calendar_upcoming", 12))
        calendar_completed_hours = int(lookbacks.get("calendar_completed", 4))
        chat_excerpts_hours = int(lookbacks.get("chat_excerpts", 4))
        tickets_hours = int(lookbacks.get("recent_tickets", 2))

        current_daily_context = self._get_current_daily_context(ctx)
        daily_context_mode = self._get_daily_context_mode(current_daily_context, ctx)

        # Get day_start for activity segments
        day_start_utc = self._parse_iso_utc(ctx.state.get("day_start_time_utc"))
        if not day_start_utc:
            # Fallback to 8 hours ago
            day_start_utc = now_utc - timedelta(hours=8)
        
        activity_segments = get_significant_activity_segments(since_utc=day_start_utc)

        context = {
            "day_of_week": ctx.now_local.strftime("%A"),
            "daily_context_mode": daily_context_mode,
            "current_daily_context": current_daily_context,
            "calendar_events_upcoming": get_calendar_events_upcoming_for_daily_context(hours=calendar_upcoming_hours),
            "recent_chat_excerpts": self._get_recent_chat_excerpts(hours=chat_excerpts_hours),
            "calendar_events_completed": get_calendar_events_completed(hours=calendar_completed_hours),
            "recent_responded_tickets": get_responded_tickets_categorized(since_utc=now_utc - timedelta(hours=tickets_hours)),
            "presence_status": get_current_presence_status(),
            "activity_segments": activity_segments,
        }

        # Step 2: Execute agent
        output = self._call_agent(context)

        if not output:
            logger.warning("DailyContextGeneratorStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={"mode": daily_context_mode},
            )

        # Step 3: Build and write output
        # Agent outputs: expected_schedule, day_theme, milestones, current_status
        milestones = output.get("milestones", [])
        if not isinstance(milestones, list):
            milestones = []

        stage_output: Dict[str, Any] = {
            "date": now_local.strftime("%Y-%m-%d"),
            "expected_schedule": output.get("expected_schedule", ""),
            "day_theme": output.get("day_theme", ""),
            "milestones": milestones,
            "current_status": output.get("current_status", ""),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "last_updated_utc": now_utc.isoformat(),
        }

        ctx.write_resource(self._output_filename(), stage_output)

        logger.info(
            f"DailyContextGeneratorStage: mode={daily_context_mode}, "
            f"milestones={len(milestones)}"
        )

        return StageResult(
            output=stage_output,
            debug={
                "mode": daily_context_mode,
                "milestone_count": len(milestones),
                "output_keys": list(output.keys())[:10],
            },
        )

    def _get_recent_chat_excerpts(self, *, hours: int) -> list[dict]:
        """
        Daily-context policy:
        - recent window is configured in stage config (hours)
        - default chat filters apply (no commands, no injections, no summaries)
        - return excerpt dicts for prompt consumption
        """
        try:
            from app.assistant.ServiceLocator.service_locator import DI

            cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=int(hours))
            msgs = DI.global_blackboard.get_recent_chat_since_utc(
                cutoff_utc,
                limit=30,
                content_limit=300,
            )
            return messages_to_chat_excerpts(msgs)
        except Exception:
            return []

    def reset_stage(self, ctx: StageContext) -> None:
        """Reset daily context at boundary using defaults from config."""
        now_utc = ctx.now_utc
        now_local = ctx.now_local

        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {}) if isinstance(stage_config, dict) else {}
        defaults = daily_reset.get("output_resource_defaults", {}) if isinstance(daily_reset, dict) else {}

        default_data: Dict[str, Any] = {
            "date": now_local.strftime("%Y-%m-%d"),
            "expected_schedule": defaults.get("expected_schedule", ""),
            "day_theme": defaults.get("day_theme", ""),
            "milestones": defaults.get("milestones", []),
            "current_status": defaults.get("current_status", ""),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "last_updated_utc": now_utc.isoformat(),
            "_reset_reason": "daily_boundary",
        }

        ctx.write_resource(self._output_filename(), default_data)
        logger.info("DailyContextGeneratorStage: daily reset complete")
