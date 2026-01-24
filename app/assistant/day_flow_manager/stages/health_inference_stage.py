# stages/health_inference_stage.py
"""
Health Inference Stage

Flow:
1. Prepare inputs: Build context items (time_since, calendar_events, etc.)
2. Execute: Run health_status_inference agent
3. Output: Write resource_health_inference_output.json
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    build_time_since,
    get_calendar_events_for_health_inference,
    get_recent_chat_history,
    get_recent_tickets_for_health_inference,
)

logger = get_logger(__name__)


class HealthInferenceStage(BaseStage):
    """
    Pipeline stage that runs the health_status_inference agent to infer
    user's health/energy/cognitive state from available data.
    """

    stage_id: str = "health_inference"

    def _output_filename(self) -> str:
        return f"resource_{self.stage_id}_output.json"

    # -------------------------------------------------------------------------
    # Context building helpers
    # -------------------------------------------------------------------------


    def _get_todo_tasks(self) -> List[Dict[str, Any]]:
        """Get todo/tasks from event repository."""
        try:
            from app.assistant.event_repository.event_repository import EventRepositoryManager
            import json
            
            repo = EventRepositoryManager()
            tasks_json = repo.search_events(data_type="todo")
            tasks_list = json.loads(tasks_json) if tasks_json else []
            
            result = []
            for task in tasks_list:
                data = task.get("data", {})
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except Exception:
                        continue
                if isinstance(data, dict):
                    result.append({
                        "title": data.get("title", data.get("name", "")),
                        "completed": data.get("completed", data.get("done", False)),
                    })
            return result
        except Exception as e:
            logger.warning(f"Could not get tasks: {e}")
            return []

    # Calendar/chat/tickets/time_since helpers live in utils.context_sources

    # -------------------------------------------------------------------------
    # Agent call
    # -------------------------------------------------------------------------

    def _call_agent(self, agent_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call the health_status_inference agent."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message
            
            agent = DI.agent_factory.create_agent("health_status_inference")
            result = agent.action_handler(Message(agent_input=agent_input))
            
            if hasattr(result, "data") and isinstance(result.data, dict):
                return result.data
            elif isinstance(result, dict):
                return result
            else:
                return {"result": str(result)}
                
        except Exception as e:
            logger.error(f"Error calling health_status_inference agent: {e}")
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
        calendar_events = get_calendar_events_for_health_inference()
        todo_tasks = self._get_todo_tasks()
        context = {
            "time_since": build_time_since(include_water=False),
            "calendar_events": calendar_events,
            "recent_tickets": get_recent_tickets_for_health_inference(),
            "todo": todo_tasks,
            "recent_chat_history": get_recent_chat_history(hours=2, limit=20, content_limit=200),
            "meetings_today": len([e for e in calendar_events if e.get("is_meeting")]),
            "tasks": todo_tasks,  # Alias for template compatibility
        }
        
        # Step 2: Execute agent (context passed via agent_input)
        output = self._call_agent(context)
        
        if not output:
            logger.warning("HealthInferenceStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={},
            )
        
        # Step 3: Build and write output (LOCAL time)
        now_local = ctx.now_local
        stage_output: Dict[str, Any] = {
            **output,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
        }
        
        ctx.write_resource(self._output_filename(), stage_output)
        
        # Log key health indicators if present
        energy = output.get("energy_level", output.get("energy", "unknown"))
        cognitive = output.get("cognitive_load", output.get("cognitive", "unknown"))
        logger.info(f"HealthInferenceStage: energy={energy}, cognitive={cognitive}")
        
        return StageResult(
            output=stage_output,
            debug={"output_keys": list(output.keys())[:10]},
        )

    def reset_daily(self, ctx: StageContext) -> None:
        """Reset health inference at 5AM boundary using defaults from config."""
        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {})
        defaults = daily_reset.get("output_resource_defaults", {})
        
        now_local = ctx.now_local
        
        # Use the structured schema from config
        default_data: Dict[str, Any] = {
            "mental": defaults.get("mental", {
                "mood": "neutral",
                "stress_load": "neutral",
                "anxiety": "neutral",
                "mental_energy": "normal",
                "social_capacity": "normal",
            }),
            "cognitive": defaults.get("cognitive", {
                "load": "Low",
                "interruption_tolerance": "High",
                "focus_depth": "Normal",
            }),
            "physical": defaults.get("physical", {
                "energy_level": "Normal",
                "pain_level": "none",
            }),
            "physiology": defaults.get("physiology", {
                "hunger_probability": "Low",
                "hydration_need": "Low",
                "caffeine_state": "Optimal",
            }),
            "health_concerns_today": defaults.get("health_concerns_today", []),
            "general_health_assessment": defaults.get("general_health_assessment", "Initial state - health status not yet assessed"),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "_reset_reason": "daily_boundary",
        }
        
        ctx.write_resource(self._output_filename(), default_data)
        logger.info("HealthInferenceStage: Daily reset complete")
