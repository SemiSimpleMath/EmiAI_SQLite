# stages/health_inference_stage.py
"""
Health Inference Stage

Flow:
1. Load stage config, check gate conditions
2. Prepare inputs: Build context items (time_since, calendar_events, etc.)
3. Execute: Run health_status_inference agent
4. Output: Write resource_health_inference_output.json

Notes:
- This is an agent-based stage (calls LLM) so it should be gated by AFK and interval.
- Output includes both LOCAL display strings and UTC ISO strings for downstream math.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.assistant.utils.logging_config import get_logger
from app.assistant.day_flow_manager.day_flow_manager import BaseStage, StageContext, StageResult
from app.assistant.day_flow_manager.utils.context_sources import (
    build_time_since,
    get_calendar_events_for_health_inference,
    get_responded_tickets_categorized,
)
from app.assistant.utils.chat_formatting import messages_to_chat_history_text

logger = get_logger(__name__)


class HealthInferenceStage(BaseStage):
    """
    Pipeline stage that runs the health_status_inference agent to infer
    user's health/energy/cognitive state from available data.
    """

    stage_id: str = "health_inference"

    # -------------------------------------------------------------------------
    # Config & Cursor
    # -------------------------------------------------------------------------

    def _output_filename(self) -> str:
        return "resource_health_inference_output.json"

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
        now_utc = ctx.now_utc
        now_local = ctx.now_local

        # Step 1: Build context items that the agent needs
        stage_config = self.get_stage_config(ctx)
        lookbacks = stage_config.get("lookback_hours", {}) if isinstance(stage_config, dict) else {}
        chat_hours = int(lookbacks.get("chat_history", 2))
        tickets_hours = int(lookbacks.get("recent_tickets", 2))
        
        # Get day_start for tickets context
        day_start_utc = self._parse_iso_utc(ctx.state.get("day_start_time_utc"))
        if not day_start_utc:
            day_start_utc = now_utc - timedelta(hours=8)

        calendar_events = get_calendar_events_for_health_inference()
        todo_tasks = self._get_todo_tasks()

        context = {
            "time_since": build_time_since(),
            "calendar_events": calendar_events,
            "recent_responded_tickets": get_responded_tickets_categorized(since_utc=now_utc - timedelta(hours=tickets_hours)),
            "todo": todo_tasks,
            "recent_chat_history": self._get_recent_chat_history(hours=chat_hours),
            "meetings_today": len([e for e in calendar_events if e.get("is_meeting")]),
            "tasks": todo_tasks,  # Alias for template compatibility
        }

        # Step 2: Execute agent
        output = self._call_agent(context)

        if not output:
            logger.warning("HealthInferenceStage: Agent returned no output")
            return StageResult(
                output={"error": "Agent returned no output"},
                debug={},
            )

        # Step 3: Build and write output
        stage_output: Dict[str, Any] = {
            **output,
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "last_updated_utc": now_utc.isoformat(),
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

    def _get_recent_chat_history(self, *, hours: int) -> str:
        """
        Health-inference policy:
        - short window (configured hours)
        - default chat filters apply (no commands, no injections, no summaries)
        - return a compact multi-line string for the agent prompt
        """
        try:
            from app.assistant.ServiceLocator.service_locator import DI

            cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=int(hours))
            msgs = DI.global_blackboard.get_recent_chat_since_utc(
                cutoff_utc,
                limit=20,
                content_limit=200,
            )
            return messages_to_chat_history_text(msgs)
        except Exception:
            return ""

    def reset_stage(self, ctx: StageContext) -> None:
        """Reset health inference at boundary using defaults from config."""
        now_utc = ctx.now_utc
        now_local = ctx.now_local

        stage_config = self.get_stage_config(ctx)
        daily_reset = stage_config.get("daily_reset", {}) if isinstance(stage_config, dict) else {}
        defaults = daily_reset.get("output_resource_defaults", {}) if isinstance(daily_reset, dict) else {}

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
            "general_health_assessment": defaults.get(
                "general_health_assessment",
                "Initial state - health status not yet assessed",
            ),
            "last_updated": now_local.strftime("%Y-%m-%d %I:%M %p"),
            "last_updated_utc": now_utc.isoformat(),
            "_reset_reason": "daily_boundary",
        }

        ctx.write_resource(self._output_filename(), default_data)
        logger.info("HealthInferenceStage: daily reset complete")
