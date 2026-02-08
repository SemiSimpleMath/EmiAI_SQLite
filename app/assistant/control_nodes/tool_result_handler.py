import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
import fnmatch
import importlib

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message, ToolResult
from app.assistant.utils.pipeline_state import (
    get_pending_tool,
    set_pending_tool,
    clear_pending_tool,
    set_last_tool_result_ref,
    get_flag,
    set_flag,
)
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
        
        # Defensive: if a tool_result is present, handle it directly.
        # Some managers still route through this node via state_map after tool_caller,
        # but ToolCaller may also call process_tool_result_direct() inline. In that case
        # tool_result will be None and this block is a no-op.
        try:
            tr = self.blackboard.get_state_value("tool_result")
            if tr is not None:
                self._process_tool_result(tr)
                return
        except Exception:
            pass
        
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
            if result is not None:
                print(f"   Result preview: {str(result)[:200]}...")
            # If there is no agent result and no scope-level `result`, do NOT pop the call context.
            # This situation can happen if this handler is reached via state_map after a tool call.
            # Popping the root scope will corrupt the manager loop and can cause attempts to route
            # back to the manager name as if it were an agent.
            try:
                scope_result = self.blackboard.get_state_value("result")
            except Exception:
                scope_result = None

            if result is None and scope_result is None:
                # Route back to a real agent without mutating scopes.
                # Prefer calling_agent from the call context, otherwise fall back to called_agent.
                nxt = calling_agent if isinstance(calling_agent, str) else None
                if not isinstance(nxt, str) or not nxt.strip() or not self.agent_registry.get_agent_config(nxt.strip()):
                    nxt = called_agent if isinstance(called_agent, str) else None
                self.blackboard.update_state_value("last_agent", self.name)
                self.blackboard.update_state_value("next_agent", nxt)
                logger.warning(
                    "[%s] action_handler reached with call_context=%r but no agent result; "
                    "skipping pop_call_context and returning to %r",
                    self.name,
                    current_context,
                    nxt,
                )
                return

            self._process_agent_result(result, current_context)
        else:
            logger.warning(f"[{self.name}] action_handler called with no call context")
            # Clear next_agent to avoid stale routing when we cannot resolve a context.
            self.blackboard.update_state_value("next_agent", None)
    
    def process_tool_result_direct(self, tool_result: ToolResult | None = None):
        """
        Called directly by tool_caller after a tool executes.
        Handles tool results without needing to check call context.
        """
        self.blackboard.update_state_value('next_agent', None)

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
        pending = get_pending_tool(self.blackboard) or {}
        calling_agent = pending.get("calling_agent")
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
                        "tool": pending.get("name"),
                        "result_type": getattr(tool_result, "result_type", None),
                        "tool_result_id": (artifact_ref or {}).get("tool_result_id") if isinstance(artifact_ref, dict) else None,
                        "preview": preview,
                    },
                )
            )
        except Exception:
            pass

        # Update pipeline state with the latest tool_result reference.
        try:
            set_last_tool_result_ref(
                self.blackboard,
                artifact_ref if isinstance(artifact_ref, dict) else None,
                meta={
                    "tool_name": pending.get("name"),
                    "result_type": getattr(tool_result, "result_type", None),
                    "calling_agent": calling_agent,
                },
            )
        except Exception:
            pass

        # Clear pending tool now that its result has been processed.
        try:
            clear_pending_tool(self.blackboard)
        except Exception:
            pass

        # Update last agent to track execution
        self.blackboard.update_state_value('last_agent', self.name)

        # ------------------------------------------------------------
        # Tool pipeline (configurable): after-tool hooks (auto-scan, tab-follow, etc.)
        # ------------------------------------------------------------
        selected_tool = pending.get("name")
        def _tool_matches(name: str | None, patterns: list[str] | None) -> bool:
            if not isinstance(name, str) or not name:
                return False
            if not patterns:
                return False
            for pat in patterns:
                if not isinstance(pat, str) or not pat.strip():
                    continue
                if "*" in pat:
                    try:
                        if fnmatch.fnmatch(name, pat):
                            return True
                    except Exception:
                        pass
                else:
                    if name == pat:
                        return True
            return False

        def _sub_vars(obj, ctx: dict) -> object:
            if isinstance(obj, str) and obj.startswith("$"):
                key = obj[1:]
                return ctx.get(key, obj)
            if isinstance(obj, list):
                return [_sub_vars(x, ctx) for x in obj]
            if isinstance(obj, dict):
                return {k: _sub_vars(v, ctx) for k, v in obj.items()}
            return obj

        def _resolve_condition_handler(handler_path: str | None):
            if not isinstance(handler_path, str) or not handler_path.strip():
                return None
            try:
                mod_path, func_name = handler_path.rsplit(".", 1)
                mod = importlib.import_module(mod_path)
                fn = getattr(mod, func_name, None)
                if callable(fn):
                    return fn
            except Exception:
                return None
            return None

        def _apply_set_flags(flag_map: dict | None, ctx: dict):
            if not isinstance(flag_map, dict):
                return
            for key, val in flag_map.items():
                if not isinstance(key, str) or not key.strip():
                    continue
                resolved = _sub_vars(val, ctx)
                try:
                    set_flag(self.blackboard, key, resolved)
                except Exception:
                    continue

        def _run_tool_pipeline(raw_content: str) -> bool:
            try:
                pipeline = self.blackboard.get_state_value("tool_pipeline")
            except Exception:
                pipeline = None
            if not pipeline:
                return False
            rules = None
            if isinstance(pipeline, dict):
                rules = pipeline.get("rules")
            elif isinstance(pipeline, list):
                rules = pipeline
            if not isinstance(rules, list):
                return False

            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                if rule.get("when") != "after":
                    continue
                tools = rule.get("tools") or []
                unless_tools = rule.get("unless_tools") or []
                if not _tool_matches(selected_tool, tools):
                    continue
                if _tool_matches(selected_tool, unless_tools):
                    continue

                guard_key = rule.get("guard_key")
                if isinstance(guard_key, str) and guard_key.strip():
                    if bool(get_flag(self.blackboard, guard_key, False)):
                        continue
                ctx: dict = {"selected_tool": selected_tool, "calling_agent": calling_agent}
                handler_path = rule.get("condition_handler")
                if isinstance(handler_path, str) and handler_path.strip():
                    handler = _resolve_condition_handler(handler_path)
                    if not handler:
                        continue
                    try:
                        handler_ctx = handler(raw_content, self.blackboard)
                    except Exception:
                        handler_ctx = None
                    if handler_ctx is None:
                        continue
                    if isinstance(handler_ctx, dict):
                        ctx.update(handler_ctx)

                action = rule.get("action") or {}
                kind = action.get("kind")
                if kind == "control_node":
                    node = action.get("node")
                    if isinstance(node, str) and node.strip():
                        try:
                            if isinstance(guard_key, str) and guard_key.strip():
                                set_flag(self.blackboard, guard_key, True)
                            _apply_set_flags(action.get("set_flags"), ctx)
                            self.blackboard.update_state_value("next_agent", node)
                            # Clear tool_result so the follow-up node doesn't reprocess this same result.
                            self.blackboard.update_state_value("tool_result", None)
                            clear_pending_tool(self.blackboard)
                            return True
                        except Exception:
                            return False
                elif kind == "tool_call":
                    tool_name = action.get("tool")
                    args = action.get("arguments") or {}
                    if isinstance(tool_name, str) and tool_name.strip():
                        try:
                            if isinstance(guard_key, str) and guard_key.strip():
                                set_flag(self.blackboard, guard_key, True)
                            _apply_set_flags(action.get("set_flags"), ctx)

                            resolved_args = _sub_vars(args, ctx if isinstance(ctx, dict) else {})
                            set_pending_tool(
                                self.blackboard,
                                name=tool_name,
                                calling_agent=calling_agent,
                                action_input=None,
                                arguments=resolved_args if isinstance(resolved_args, dict) else {},
                                kind="tool",
                            )
                            self.blackboard.update_state_value("next_agent", "tool_caller")
                            # Clear tool_result so the follow-up call doesn't reprocess this same result.
                            self.blackboard.update_state_value("tool_result", None)
                            return True
                        except Exception:
                            return False
                else:
                    continue
            return False

        # If we just processed a click-like action tool result that opened a new tab, follow it now.
        try:
            raw_content = (getattr(tool_result, "content", "") or "").strip()
        except Exception:
            raw_content = ""
        if _run_tool_pipeline(raw_content):
            return

        # Default behavior: Return control to the calling agent
        self.blackboard.update_state_value('next_agent', calling_agent)
        logger.debug(f"[{self.name}] Returning control to calling agent: {calling_agent}")

        # Clear tool_result from blackboard
        self.blackboard.update_state_value("tool_result", None)
        clear_pending_tool(self.blackboard)
        
        # DO NOT pop call context - tool calls stay in the same scope

    def _process_agent_result(self, agent_result, current_context):
        """Process an agent result and record it in the calling agent's history."""
        # current_context is a tuple: (calling_agent, called_agent, scope_id)
        calling_agent, called_agent, scope_id = current_context if current_context else (None, None, None)
        logger.debug(f"Processing agent response from {called_agent}")

        # Capture callee-selected next_agent BEFORE popping scope.
        callee_next_agent = None
        try:
            callee_next_agent = self.blackboard.get_state_value("next_agent")
        except Exception:
            callee_next_agent = None

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
        
        # Set next_agent in the parent scope (so delegator will see it).
        # If the callee explicitly selected a next agent, respect it.
        logger.debug(f"[{self.name}] Current call context: {current_context}")
        next_agent = None
        if isinstance(callee_next_agent, str) and callee_next_agent.strip():
            # Validate that the target exists in this runtime.
            if self.agent_registry.get_agent_config(callee_next_agent.strip()):
                next_agent = callee_next_agent.strip()
            else:
                logger.warning(
                    "[%s] Callee requested next_agent '%s' but it is not available; "
                    "falling back to caller '%s'",
                    self.name,
                    callee_next_agent,
                    calling_agent,
                )
        if next_agent is None:
            next_agent = calling_agent

        self.blackboard.update_state_value("next_agent", next_agent)
        print(f"   ✅ Returning control: next_agent = '{next_agent}' (set in parent scope)")
        logger.debug(f"[{self.name}] Setting next_agent to: {next_agent}")
