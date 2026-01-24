# stages/day_flow_orchestrator_stage.py
"""
Physical Orchestrator Stage

Flow:
1. Prepare inputs: Build context items (computer_activity, time_since, tickets, etc.)
2. Execute: Run proactive_orchestrator agent
3. Create tickets: Hand suggestions to ticket module
4. Output: Write resource_day_flow_orchestrator_output.json

Note: This is the final stage that decides what proactive suggestions to make.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    build_time_since,
    get_calendar_events_for_orchestrator,
    get_recent_chat_excerpts,
    get_active_tickets_for_orchestrator,
    get_recently_accepted_tickets_for_orchestrator,
)

logger = get_logger(__name__)


class DayFlowOrchestratorStage(BaseStage):
    """
    Pipeline stage that runs the proactive_orchestrator agent to decide
    what wellness suggestions to make based on all available context.
    """

    stage_id: str = "day_flow_orchestrator"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    # -------------------------------------------------------------------------
    # Context building helpers
    # Note: Most data comes from resource files that agents subscribe to.
    # Only build context for data NOT available as resource files.
    # -------------------------------------------------------------------------

    def _get_location_summary(self) -> str:
        """Get current location summary."""
        try:
            from app.assistant.location_manager.location_manager import get_location_manager
            location_manager = get_location_manager()
            current = location_manager.get_current_location()
            return f"Currently: {current.get('label', 'Unknown')}"
        except Exception as e:
            logger.warning(f"Could not get location: {e}")
            return "Location unavailable"

    # Calendar/chat/tickets/time_since helpers live in utils.context_sources

    def _get_recent_tickets(self, hours: int = 5) -> List[Dict[str, Any]]:
        """Get all recent tickets."""
        try:
            from app.assistant.ticket_manager import get_ticket_manager
            
            manager = get_ticket_manager()
            tickets = manager.get_recent_tickets(hours=hours)
            return [
                {
                    "ticket_id": getattr(t, "ticket_id", None),
                    "suggestion_type": getattr(t, "suggestion_type", None),
                    "title": getattr(t, "title", None),
                    "state": getattr(t, "state", None),
                    "created_at": getattr(t, "created_at", None),
                }
                for t in tickets
            ]
        except Exception as e:
            logger.warning(f"Could not get recent tickets: {e}")
            return []

    # -------------------------------------------------------------------------
    # Ticket creation
    # -------------------------------------------------------------------------

    def _create_tickets(
        self,
        suggestions: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> int:
        """
        Create tickets from agent suggestions.
        
        Maps agent output fields to ticket_manager.create_ticket() parameters.
        Returns number of tickets created.
        """
        from app.assistant.ticket_manager import get_ticket_manager
        
        try:
            ticket_manager = get_ticket_manager()
        except Exception as e:
            logger.warning(f"Could not get ticket manager: {e}")
            return 0
        
        created = 0
        for suggestion in suggestions:
            suggestion_type = suggestion.get("suggestion_type", "general")
            title = suggestion.get("title", "")
            
            if not title:
                continue
            
            # Convert status_effects list to dict
            # Agent: [{"activity_name": "coffee", "action": "completed"}, ...]
            # Ticket: {"coffee": "completed", ...}
            status_effects_list = suggestion.get("status_effects", [])
            status_effect = {}
            if isinstance(status_effects_list, list):
                for item in status_effects_list:
                    if isinstance(item, dict) and item.get("activity_name"):
                        status_effect[item["activity_name"]] = item.get("action", "completed")
            
            try:
                ticket = ticket_manager.create_ticket(
                    suggestion_type=suggestion_type,
                    title=title,
                    message=suggestion.get("message", ""),
                    action_type=suggestion.get("action_type", "none"),
                    action_params={"priority": suggestion.get("priority", 5)},
                    trigger_context={
                        "location": context.get("location_summary", ""),
                        "time": context.get("day_of_week", ""),
                        "time_since": context.get("time_since", {}),
                    },
                    trigger_reason=suggestion.get("trigger_reason", ""),
                    valid_hours=4,
                    status_effect=status_effect,
                    ticket_type="wellness",
                )
                if ticket:
                    created += 1
                    logger.info(f"🎯 Created ticket: {suggestion_type} - {title}")
            except Exception as e:
                logger.warning(f"Error creating ticket: {e}")
        
        return created

    # -------------------------------------------------------------------------
    # Agent call
    # -------------------------------------------------------------------------

    def _call_agent(self, agent_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the proactive_orchestrator agent."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message
            
            agent = DI.agent_factory.create_agent("proactive_orchestrator")
            result = agent.action_handler(Message(agent_input=agent_input))
            
            if hasattr(result, "data") and isinstance(result.data, dict):
                return result.data
            elif isinstance(result, dict):
                return result
            else:
                return {"result": str(result)}
                
        except Exception as e:
            logger.error(f"Error calling proactive_orchestrator agent: {e}")
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
        # Step 1: Build context items NOT available as resource files
        # 
        # Resource files agents subscribe to (no need to build here):
        #   - resource_afk_statistics_output (computer activity)
        #   - resource_weather (weather)
        #   - resource_sleep_output (sleep data)
        #   - resource_activity_tracker_output (activity tracking)
        #   - resource_tracked_activities_output (activity definitions)
        #   - resource_daily_context_generator_output (daily context)
        #   - resource_health_inference_output (health status)
        #   - resource_user_routine, resource_user_health (user prefs)
        #
        # Only build context for dynamic data not in resource files:
        context = {
            "day_of_week": ctx.now_local.strftime("%A"),
            "time_since": build_time_since(include_water=True),
            "calendar_events": get_calendar_events_for_orchestrator(),
            "location_summary": self._get_location_summary(),
            "recent_chat_messages": get_recent_chat_excerpts(hours=2, limit=20, content_limit=200),
            "active_tickets": get_active_tickets_for_orchestrator(),
            "recent_accepted_tickets": get_recently_accepted_tickets_for_orchestrator(hours=2),
            "recent_tickets": self._get_recent_tickets(),
        }
        
        # Step 2: Execute agent (context passed via agent_input)
        output = self._call_agent(context)
        
        if not output:
            logger.warning("DayFlowOrchestratorStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={},
            )
        
        # Step 3: Create tickets from suggestions
        suggestions = output.get("suggestions", [])
        tickets_created = 0
        if isinstance(suggestions, list) and suggestions:
            tickets_created = self._create_tickets(suggestions, context)
        
        # Step 4: Build and write output (LOCAL time)
        now_local = ctx.now_local
        stage_output: Dict[str, Any] = {
            **output,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "tickets_created": tickets_created,
        }
        
        ctx.write_resource(self._output_filename(), stage_output)
        
        # Log summary
        suggestion_type = output.get("suggestion_type", "none")
        logger.info(
            f"DayFlowOrchestratorStage: suggestion_type={suggestion_type}, "
            f"suggestions={len(suggestions) if isinstance(suggestions, list) else 0}, "
            f"tickets_created={tickets_created}"
        )
        
        return StageResult(
            output=stage_output,
            debug={
                "output_keys": list(output.keys())[:10],
                "tickets_created": tickets_created,
            },
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """Reset orchestrator state at 5AM boundary using defaults from config."""
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {})
        defaults = daily_reset.get("output_resource_defaults", {})
        
        now_local = ctx.now_local
        
        default_data: Dict[str, Any] = {
            "suggestions": defaults.get("suggestions", []),
            "suggestion_type": defaults.get("suggestion_type"),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "daily_boundary",
        }
        
        ctx.write_resource(self._output_filename(), default_data)
        logger.info("DayFlowOrchestratorStage: Daily reset complete")
