# stages/day_flow_orchestrator_stage.py
"""
Physical Orchestrator Stage

Flow:
1. Prepare inputs: Build context items (computer_activity, time_since, tickets, etc.)
2. Execute: Run day_flow_orchestrator agent
3. Create tickets: Hand suggestions to ticket module
4. Output: Write resource_day_flow_orchestrator_output.json

Note: This is the final stage that decides what proactive suggestions to make.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.day_flow_manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    build_time_since,
    get_calendar_events_for_orchestrator,
    get_responded_tickets_categorized,
    _format_ticket_for_context,
)
from app.assistant.utils.chat_formatting import messages_to_chat_excerpts

logger = get_logger(__name__)


class DayFlowOrchestratorStage(BaseStage):
    """
    Pipeline stage that runs the day_flow_orchestrator agent to decide
    what wellness suggestions to make based on all available context.
    """

    stage_id: str = "day_flow_orchestrator"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    # -------------------------------------------------------------------------
    # Gate logic
    # -------------------------------------------------------------------------

    def should_run_stage(self, ctx: StageContext) -> Tuple[bool, str]:
        """Check if stage should run based on interval and AFK guard."""
        stage_cfg = self.get_stage_config(ctx)
        run_policy = stage_cfg.get("run_policy", {}) if isinstance(stage_cfg, dict) else {}
        min_interval = int(run_policy.get("min_interval_seconds", 300))

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
            if afk_guard.get("skip_when_potentially_afk", True) and is_potentially_afk:
                return False, "afk_guard=potentially_afk"

        return True, "ready"

    def _get_last_run_utc(self, ctx: StageContext) -> Optional[datetime]:
        """Get last run time for this stage."""
        stage_runs = ctx.state.get("stage_runs", {})
        last_run_str = stage_runs.get(self.stage_id, {}).get("last_run_utc")
        if last_run_str:
            try:
                dt = datetime.fromisoformat(last_run_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception as e:
                logger.warning(f"DayFlowOrchestratorStage: could not parse last_run_utc '{last_run_str}': {e}", exc_info=True)
        return None

    def _get_afk_snapshot(self) -> Dict[str, Any]:
        """Get current AFK status from monitor."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            monitor = getattr(DI, "afk_monitor", None)
            if monitor:
                return monitor.get_computer_activity() or {}
        except Exception as e:
            logger.warning(f"DayFlowOrchestratorStage: could not read AFK snapshot: {e}", exc_info=True)
        return {}

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

    def _get_tracked_activity_names(self) -> set:
        """Get set of tracked activity field_names from config."""
        try:
            import json
            from pathlib import Path
            config_path = Path(__file__).resolve().parent / "stage_configs" / "config_tracked_activities.json"
            if config_path.exists():
                config = json.loads(config_path.read_text(encoding="utf-8"))
                activities = config.get("activities", {})
                return {act.get("field_name") for act in activities.values() if act.get("field_name")}
            return set()
        except Exception as e:
            logger.warning(f"Could not load tracked activities config: {e}")
            return set()

    # Calendar/chat/tickets/time_since helpers live in utils.context_sources

    def _get_active_tickets(self) -> List[Dict[str, Any]]:
        """Get tickets in PENDING, PROPOSED, or SNOOZED state."""
        try:
            from app.assistant.ticket_manager import get_ticket_manager, TicketState
            
            tickets = get_ticket_manager().get_tickets(
                states=[TicketState.PENDING, TicketState.PROPOSED, TicketState.SNOOZED],
                limit=50,
            )
            return [_format_ticket_for_context(t) for t in tickets]
        except Exception as e:
            logger.warning(f"Could not get active tickets: {e}")
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
            
            # Extract activity names from status_effects
            # Agent: [{"activity_name": "coffee"}, {"activity_name": "finger_stretch"}]
            # Ticket: ["coffee", "finger_stretch"]
            status_effects_list = suggestion.get("status_effects", [])
            status_effect = []
            if isinstance(status_effects_list, list):
                for item in status_effects_list:
                    if isinstance(item, dict) and item.get("activity_name"):
                        status_effect.append(item["activity_name"])
            
            try:
                ticket = ticket_manager.create_ticket(
                    ticket_type="day_flow",
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
                )
                if ticket:
                    # Propose and emit to UI
                    ticket_manager.mark_proposed(ticket.ticket_id)
                    self._emit_ticket_to_ui(ticket)
                    created += 1
                    logger.info(f"🎯 Created ticket: {suggestion_type} - {title}")
            except Exception as e:
                logger.warning(f"Error creating ticket: {e}")
        
        return created

    # -------------------------------------------------------------------------
    # UI emission
    # -------------------------------------------------------------------------

    def _emit_ticket_to_ui(self, ticket) -> None:
        """Emit a ticket to the frontend via WebSocket with TTS."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
            from datetime import datetime, timezone
            
            ticket_dict = ticket.to_dict() if hasattr(ticket, "to_dict") else ticket
            
            # Determine button layout based on whether status_effect references a tracked activity
            status_effect = ticket_dict.get("status_effect") or []
            tracked_names = self._get_tracked_activity_names()
            is_tracked_activity = any(name in tracked_names for name in status_effect)
            ticket_dict["button_layout"] = "activity" if is_tracked_activity else "advice"
            
            # Emit the suggestion data for the popup
            message = Message(
                event_topic='proactive_suggestion',
                data=ticket_dict
            )
            DI.event_hub.publish(message)
            
            # Also emit TTS message so Emi speaks the suggestion
            tts_text = ticket_dict.get('message') or ticket_dict.get('title', 'I have a suggestion for you.')
            tts_message = UserMessage(
                data_type='user_msg',
                sender='day_flow_orchestrator',
                receiver=None,
                timestamp=datetime.now(timezone.utc),
                role='assistant',
                user_message_data=UserMessageData(
                    feed=None,
                    tts=True,
                    tts_text=tts_text
                )
            )
            tts_message.event_topic = 'socket_emit'
            DI.event_hub.publish(tts_message)
            logger.debug(f"Emitted ticket to UI: {ticket_dict.get('ticket_id')}")
            
        except Exception as e:
            logger.warning(f"Could not emit ticket to UI: {e}")

    # -------------------------------------------------------------------------
    # Agent call
    # -------------------------------------------------------------------------

    def _call_agent(self, agent_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the day_flow_orchestrator agent."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message
            
            agent = DI.agent_factory.create_agent("day_flow_orchestrator")
            result = agent.action_handler(Message(agent_input=agent_input))
            
            if hasattr(result, "data") and isinstance(result.data, dict):
                return result.data
            elif isinstance(result, dict):
                return result
            else:
                return {"result": str(result)}
                
        except Exception as e:
            logger.error(f"Error calling day_flow_orchestrator agent: {e}")
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
        stage_config = self.get_stage_config(ctx)
        lookbacks = stage_config.get("lookback_hours", {}) if isinstance(stage_config, dict) else {}
        tickets_hours = int(lookbacks.get("recent_tickets", 2))

        context = {
            "day_of_week": ctx.now_local.strftime("%A"),
            "time_since": build_time_since(),
            "calendar_events": get_calendar_events_for_orchestrator(),
            "location_summary": self._get_location_summary(),
            "recent_chat_messages": self._get_recent_chat_messages(),
            "active_tickets": self._get_active_tickets(),
            "recent_responded_tickets": get_responded_tickets_categorized(since_utc=ctx.now_utc - timedelta(hours=tickets_hours)),
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

    def _get_recent_chat_messages(self) -> List[Dict[str, Any]]:
        """
        Orchestrator policy:
        - last 2 hours
        - default chat filters apply (no commands, no injections, no summaries)
        - return excerpt dicts for prompt consumption
        """
        try:
            from app.assistant.ServiceLocator.service_locator import DI

            cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=2)
            msgs = DI.global_blackboard.get_recent_chat_since_utc(
                cutoff_utc,
                limit=20,
                content_limit=200,
            )
            return messages_to_chat_excerpts(msgs)
        except Exception:
            return []

    def reset_stage(self, ctx: StageContext) -> None:
        """Reset orchestrator state at boundary using defaults from config."""
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {}) if isinstance(stage_config, dict) else {}
        defaults = daily_reset.get("output_resource_defaults", {}) if isinstance(daily_reset, dict) else {}

        now_utc = ctx.now_utc
        now_local = ctx.now_local

        default_data: Dict[str, Any] = {
            "suggestions": defaults.get("suggestions", []),
            "suggestion_type": defaults.get("suggestion_type"),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "last_updated_utc": now_utc.isoformat(),
            "_reset_reason": "daily_boundary",
        }

        ctx.write_resource(self._output_filename(), default_data)
        logger.info("DayFlowOrchestratorStage: daily reset complete")
