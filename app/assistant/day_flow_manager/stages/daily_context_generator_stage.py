# stages/daily_context_generator_stage.py
"""
Daily Context Generator Stage

Flow:
1. Prepare inputs: Build context items (calendar, chat, tickets, AFK intervals)
2. Execute: Run daily_context_tracker agent
3. Output: Write resource_daily_context_generator_output.json
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    get_calendar_events_upcoming_for_daily_context,
    get_calendar_events_completed,
    get_recent_chat_excerpts,
    get_recently_accepted_tickets,
    get_recent_afk_intervals,
)

logger = get_logger(__name__)


class DailyContextGeneratorStage(BaseStage):
    """
    Pipeline stage that runs the daily_context_tracker agent to generate
    daily context summary (what's happening today, user's state, etc.)
    """

    stage_id: str = "daily_context_generator"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    # -------------------------------------------------------------------------
    # Context building helpers
    # -------------------------------------------------------------------------

    def _get_current_daily_context(self, ctx: StageContext) -> Dict[str, Any]:
        """Get current daily context from previous stage output."""
        try:
            existing = ctx.read_resource(self._output_filename())
            if existing and existing.get("date") == ctx.now_local.strftime("%Y-%m-%d"):
                return existing
            return {"day_description": "", "milestones": []}
        except Exception:
            return {"day_description": "", "milestones": []}

    def _get_daily_context_mode(self, current_context: Dict[str, Any], ctx: StageContext) -> str:
        """Determine if we should rebuild or incrementally update."""
        # If context is empty or from different day, rebuild
        if not current_context.get("day_description"):
            return "rebuild"
        if current_context.get("date") != ctx.now_local.strftime("%Y-%m-%d"):
            return "rebuild"
        return "incremental"

    # Calendar/chat/tickets/afk helpers live in utils.context_sources

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
        # Step 1: Build context items that the agent needs
        current_daily_context = self._get_current_daily_context(ctx)
        daily_context_mode = self._get_daily_context_mode(current_daily_context, ctx)
        
        context = {
            "day_of_week": ctx.now_local.strftime("%A"),
            "daily_context_mode": daily_context_mode,
            "current_daily_context": current_daily_context,
            "calendar_events_upcoming": get_calendar_events_upcoming_for_daily_context(),
            "recent_chat_excerpts": get_recent_chat_excerpts(),
            "calendar_events_completed": get_calendar_events_completed(),
            "recent_accepted_tickets": get_recently_accepted_tickets(),
            "recent_afk_intervals": get_recent_afk_intervals(),
        }
        
        # Step 2: Execute agent (context passed via agent_input)
        agent_input: Dict[str, Any] = context
        output = self._call_agent(agent_input)
        
        if not output:
            logger.warning("DailyContextGeneratorStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={},
            )
        
        # Step 3: Build and write output (LOCAL time)
        now_local = ctx.now_local

        # Replace all fields with agent output
        stage_output: Dict[str, Any] = {
            "date": now_local.strftime("%Y-%m-%d"),
            "day_description": output.get("day_description", ""),
            "milestones": output.get("milestones", []),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
        }
        
        ctx.write_resource(self._output_filename(), stage_output)
        
        logger.info(f"DailyContextGeneratorStage: mode={daily_context_mode}, milestones={len(stage_output['milestones'])}")
        
        return StageResult(
            output=stage_output,
            debug={"mode": daily_context_mode, "output_keys": list(output.keys())[:10]},
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """Reset daily context at 5AM boundary using defaults from config."""
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {})
        defaults = daily_reset.get("output_resource_defaults", {})
        
        now_local = ctx.now_local
        
        default_data: Dict[str, Any] = {
            "date": now_local.strftime("%Y-%m-%d"),
            "day_description": defaults.get("day_description", "Day summary not run yet. Will be generated after first pipeline run."),
            "milestones": defaults.get("milestones", []),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "daily_boundary",
        }
        
        ctx.write_resource(self._output_filename(), default_data)
        logger.info("DailyContextGeneratorStage: Daily reset complete")
