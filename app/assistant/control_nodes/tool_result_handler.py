import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.control_nodes.control_node import ControlNode

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


def _repo_root_from_here() -> Path:
    # app/assistant/control_nodes/tool_result_handler.py -> repo root
    return Path(__file__).resolve().parents[3]


def _tool_results_dir() -> Path:
    return _repo_root_from_here() / "uploads" / "temp" / "tool_results"


def _persist_tool_result_artifact(*, tool_result, calling_agent: str | None, scope_id: str | None) -> dict[str, str] | None:
    """
    Persist a full ToolResult payload to disk and return a small reference dict.
    Intended to keep future prompts small while preserving the full payload for on-demand retrieval.
    """
    try:
        tool_results_dir = _tool_results_dir()
        tool_results_dir.mkdir(parents=True, exist_ok=True)

        tool_result_id = uuid.uuid4().hex
        filename = f"tool_result_{tool_result_id}.json"
        path = tool_results_dir / filename

        payload = {
            "tool_result_id": tool_result_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "calling_agent": calling_agent,
            "scope_id": scope_id,
            "tool_result": tool_result.model_dump() if hasattr(tool_result, "model_dump") else str(tool_result),
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return {"tool_result_id": tool_result_id, "path": str(path)}
    except Exception as e:
        logger.warning(f"[tool_result_handler] Failed to persist tool result artifact: {e}")
        return None


class ToolResultHandler(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message):
        """
        Main entry point - determines if this is a tool result or agent result.
        This is called by the delegator for agent results.
        For tool results, tool_caller should call process_tool_result_direct() instead.
        """
        print(f"\n📬 [TOOL_RESULT_HANDLER] action_handler called")
        self.blackboard.update_state_value('next_agent', None)
        
        # This should only be called for agent results now
        # Tool results should use process_tool_result_direct()
        current_context = self.blackboard.get_current_call_context()
        print(f"   Current call context: {current_context}")
        
        if current_context:
            # current_context is a tuple: (calling_agent, called_agent, scope_id)
            calling_agent, called_agent, scope_id = current_context
            print(f"   Looking for result: {called_agent}_result (in global blackboard)")
            # Agent results are stored in GLOBAL blackboard by Agent._handle_flow_control()
            # get_state_value searches from current scope down to global, so it will find it
            result = self.blackboard.get_state_value(f"{called_agent}_result")
            print(f"   Found result: {result is not None}")
            if result:
                print(f"   Result preview: {str(result)[:200]}...")
            self._process_agent_result(result, current_context)
        else:
            logger.warning(f"[{self.name}] action_handler called with no call context")
    
    def process_tool_result_direct(self):
        """
        Called directly by tool_caller after a tool executes.
        Handles tool results without needing to check call context.
        """
        self.blackboard.update_state_value('next_agent', None)
        
        tool_result = self.blackboard.get_state_value("tool_result")
        if tool_result:
            self._process_tool_result(tool_result)
        else:
            logger.error(f"[{self.name}] process_tool_result_direct called but no tool_result found")


    def _process_tool_result(self, tool_result):
        """
        Process a tool result and record it in the calling agent's history.
        This is only called for actual tool calls (not agent calls).
        """
        # NOTE: tool_result.data can include very large payloads (e.g., base64 screenshots from MCP).
        # Avoid logging the full object to keep logs readable and prevent huge terminal output.
        try:
            data = getattr(tool_result, "data", None) if tool_result else None
            backend = data.get("backend") if isinstance(data, dict) else None
            server_id = data.get("server_id") if isinstance(data, dict) else None
            mcp_tool = data.get("mcp_tool_name") if isinstance(data, dict) else None
            content_preview = (getattr(tool_result, "content", "") or "")[:300]
            attachments = []
            if isinstance(data, dict) and isinstance(data.get("attachments"), list):
                attachments = data.get("attachments") or []
            logger.debug(
                "Processing tool result: result_type=%r backend=%r server_id=%r mcp_tool=%r attachments=%d content_preview=%r",
                getattr(tool_result, "result_type", None),
                backend,
                server_id,
                mcp_tool,
                len(attachments),
                content_preview,
            )
        except Exception:
            logger.debug("Processing tool result (preview failed)")

        # Convert the tool result into a summarized format
        tool_result_msg = DI.data_conversion_module.convert(tool_result, "summary")

        # Convert summary to JSON string for logging and blackboard storage
        content_str = json.dumps(tool_result_msg, indent=4)
        logger.debug(f"Summarized tool result: {content_str}")

        # For tool calls, get the calling agent from blackboard
        calling_agent = self.blackboard.get_state_value('original_calling_agent')
        scope_id = None
        try:
            scope_id = self.blackboard.get_current_scope_id()
        except Exception:
            scope_id = None
        
        # Attachments: allow tools (including MCP) to surface image/file outputs.
        attachments = []
        try:
            if isinstance(getattr(tool_result, "data", None), dict):
                atts = tool_result.data.get("attachments")
                if isinstance(atts, list):
                    attachments = [a for a in atts if isinstance(a, dict)]
        except Exception:
            attachments = []

        # Persist the full tool result payload to disk (artifact store) so agents can
        # later retrieve it without bloating their prompt context.
        artifact_ref = _persist_tool_result_artifact(
            tool_result=tool_result,
            calling_agent=calling_agent,
            scope_id=scope_id,
        )

        # Create a message object with the processed tool result
        # scope_id will be auto-tagged with current scope by add_msg
        metadata = {}
        if attachments:
            metadata["attachments"] = attachments
        if artifact_ref:
            metadata.update(artifact_ref)

        message = Message(
            data_type="tool_result",
            sub_data_type=[tool_result.result_type] if getattr(tool_result, "result_type", None) else [],
            sender="tool",  # Generic sender for tools
            receiver=calling_agent,
            content=content_str,
            data=tool_result_msg,
            metadata=metadata or None,
        )

        # Store processed tool result in blackboard
        # This will auto-tag with the current scope_id
        self.blackboard.add_msg(message)

        # Emit a progress fact for UI (short, curated later).
        try:
            preview = ""
            try:
                if isinstance(tool_result_msg, dict):
                    preview = str(tool_result_msg.get("tool_result") or "")[:400]
            except Exception:
                preview = ""

            DI.event_hub.publish(
                Message(
                    sender=self.name,
                    receiver=None,
                    event_topic="agent_progress_fact",
                    data={
                        "kind": "tool_result",
                        "agent": calling_agent,
                        "tool": self.blackboard.get_state_value("selected_tool"),
                        "result_type": getattr(tool_result, "result_type", None),
                        "tool_result_id": (artifact_ref or {}).get("tool_result_id") if isinstance(artifact_ref, dict) else None,
                        "preview": preview,
                    },
                )
            )
        except Exception:
            pass

        # Update last agent to track execution
        self.blackboard.update_state_value('last_agent', self.name)

        # Return control to the calling agent
        self.blackboard.update_state_value('next_agent', calling_agent)
        logger.debug(f"[{self.name}] Returning control to calling agent: {calling_agent}")

        # Clear tool_result and original_calling_agent from blackboard
        self.blackboard.update_state_value("tool_result", None)
        self.blackboard.update_state_value("original_calling_agent", None)
        
        # DO NOT pop call context - tool calls stay in the same scope

    def _process_agent_result(self, agent_result, current_context):
        """Process an agent result and record it in the calling agent's history."""
        # current_context is a tuple: (calling_agent, called_agent, scope_id)
        calling_agent, called_agent, scope_id = current_context if current_context else (None, None, None)
        logger.debug(f"Processing agent response from {called_agent}")

        # IMPORTANT: Retrieve 'result' from the current scope BEFORE popping
        # This allows any agent in the flow (not just the originally called agent) to set the result
        scope_result = self.blackboard.get_state_value("result")
        
        # Use scope_result if available, otherwise fall back to agent_result parameter
        final_result = scope_result if scope_result is not None else agent_result
        
        print(f"   📦 Retrieved result from scope: {scope_result is not None}")
        if scope_result is not None:
            logger.debug(f"Using scope-based result instead of agent_result parameter")

        # Convert final_result to string for Message content
        if isinstance(final_result, dict):
            content_str = json.dumps(final_result)
        else:
            content_str = str(final_result) if final_result else ""

        # Create a message object with the agent response
        message = Message(
            data_type="agent_result",
            sender=called_agent,
            receiver=calling_agent,
            content=content_str,
            data=final_result  # Use final_result (scope-based if available)
        )

        # Pop the call context so we're back in the parent scope
        print(f"   🔙 Popping call context: {current_context}")
        self.blackboard.pop_call_context()
        
        # NOW add the message to the parent scope (so planner will see it in history)
        print(f"   📝 Adding agent_result message to parent scope")
        self.blackboard.add_msg(message)

        # Update last agent to track execution (in parent scope)
        self.blackboard.update_state_value('last_agent', self.name)
        
        # Set next_agent in the parent scope (so delegator will see it)
        logger.debug(f"[{self.name}] Current call context: {current_context}")
        self.blackboard.update_state_value('next_agent', calling_agent)
        print(f"   ✅ Returning control: next_agent = '{calling_agent}' (set in parent scope)")
        logger.debug(f"[{self.name}] Setting next_agent to calling agent: {calling_agent}")
