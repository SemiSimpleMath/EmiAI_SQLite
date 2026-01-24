# stages/agent_stage.py

from __future__ import annotations

from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.day_flow_manager.manager import BaseStage, StageContext, StageResult

logger = get_logger(__name__)


def _make_message(agent_input: Dict[str, Any]):
    """
    Placeholder import shim.

    Replace this with your real Message class import if needed.
    """
    try:
        from app.assistant.utils.pydantic_classes import Message
        return Message(agent_input=agent_input)
    except Exception:
        try:
            from app.assistant.message import Message  # type: ignore
            return Message(agent_input=agent_input)
        except Exception as e:
            raise ImportError(
                "Could not import Message. Update _make_message() with the correct import path."
            ) from e


class AgentStage(BaseStage):
    """
    Generic stage that runs an agent by name.

    Stage config example:
    {
      "id": "health_inference",
      "enabled": true,
      "stage_class": "app.assistant.day_flow_manager.stages.agent_stage:AgentStage",
      "agent_name": "health_inference",
      "input_resources": {
        "health_context": "resource_health_context.json",
        "afk_statistics": "resource_afk_statistics.json"
      },
      "output_resource_file": "resource_health_inference_output.json"
    }

    Behavior:
    - Reads each input resource JSON and places it into agent_input["resources"][key]
    - Adds time context (now_utc, now_local) and optionally chat excerpt payload
    - Calls the agent and returns StageResult with output written by manager
    """

    stage_id: str = "agent_stage"

    def run(self, ctx: StageContext) -> StageResult:
        cfg = ctx.stage_config or {}
        agent_name = (cfg.get("agent_name") or "").strip()
        if not agent_name:
            raise ValueError("AgentStage requires stage_config.agent_name")

        input_resources = cfg.get("input_resources") or {}
        if not isinstance(input_resources, dict):
            raise ValueError("stage_config.input_resources must be a dict")

        resources_payload: Dict[str, Any] = {}
        for key, filename in input_resources.items():
            if not filename:
                continue
            data = ctx.read_resource(str(filename))
            if data is not None:
                resources_payload[str(key)] = data
            else:
                # Missing resources are allowed, agents can handle defaults via schema logic
                resources_payload[str(key)] = None

        agent_input: Dict[str, Any] = {
            "time": {
                "now_utc": ctx.now_utc.isoformat(),
                "now_local": ctx.now_local.isoformat(),
            },
            "resources": resources_payload,
        }

        if ctx.new_chat_messages:
            agent_input["new_chat_messages"] = ctx.new_chat_messages

        agent = DI.agent_factory.create_agent(agent_name)
        msg = _make_message(agent_input)

        result_obj = agent.action_handler(msg)
        output: Dict[str, Any] = {}

        # Your agents often return ToolResult-like objects with .data, so prefer that.
        if hasattr(result_obj, "data") and isinstance(getattr(result_obj, "data"), dict):
            output = getattr(result_obj, "data")
        elif isinstance(result_obj, dict):
            output = result_obj
        else:
            # Last resort: string cast
            output = {"result": str(result_obj)}

        output_resource_file = cfg.get("output_resource_file")
        debug = {
            "agent_name": agent_name,
            "input_resource_keys": list(input_resources.keys()),
            "output_keys": list(output.keys())[:30],
        }

        return StageResult(
            output=output,
            output_resource_file=output_resource_file,
            debug=debug,
        )
