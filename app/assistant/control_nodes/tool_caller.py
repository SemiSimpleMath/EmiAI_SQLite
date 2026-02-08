import json
import sys
import uuid  # Import the uuid library to generate unique scope IDs

from app.assistant.utils.pydantic_classes import Message, ToolResult, ToolMessage
from app.assistant.utils.pipeline_state import get_pending_tool
from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.mcp.tool_runner import (
    mcp_stdio_call_tool,
    format_mcp_tool_result_content,
    sanitize_mcp_call_response_for_history,
)

logger = get_logger(__name__)


class ToolCaller(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message):
        """
        Executes the selected tool or agent, creating a new execution scope
        for agent-to-agent calls.
        """
        # Read the desired action from the agent's local scope
        pending = get_pending_tool(self.blackboard) or {}
        selected_tool = pending.get("name")
        tool_arguments = pending.get("arguments") if isinstance(pending.get("arguments"), dict) else {}


        self.blackboard.update_state_value("next_agent", None)

        if not selected_tool:
            logger.error(f"[{self.name}] Missing tool selection from blackboard.")
            self.blackboard.update_state_value("last_agent", self.name)
            return

        logger.info(f"[{self.name}] Executing: '{selected_tool}' with arguments: {tool_arguments}")
        # Emit a progress fact so UI can show "Now calling X".
        try:
            calling_agent = pending.get("calling_agent")
            DI.event_hub.publish(
                Message(
                    sender=self.name,
                    receiver=None,
                    event_topic="agent_progress_fact",
                    data={
                        "kind": "tool_call",
                        "agent": calling_agent,
                        "manager": getattr(getattr(self, "parent", None), "name", "") if getattr(self, "parent", None) else "",
                        "tool": selected_tool,
                        "next_action": selected_tool,
                    },
                )
            )
        except Exception:
            pass

        # --- Determine if the target is an agent, a tool, or a control node ---
        is_agent = False
        selected_config = self.tool_registry.get_tool(selected_tool)
        if not selected_config:
            selected_config = self.agent_registry.get_agent_config(selected_tool)
            if selected_config:
                if selected_config.get("type") == "control_node":
                    logger.info(f"[{self.name}] Transitioning to control node: {selected_tool}")
                    self.blackboard.update_state_value('next_agent', selected_tool)
                    self.blackboard.update_state_value("last_agent", self.name)
                    return
                else:
                    is_agent = True
                    # Fail fast with a clear dev error if an agent is configured but not instantiated.
                    # Agents can only be called if they are registered within the current manager runtime
                    # (or exposed via a tool wrapper). Otherwise ToolCaller will crash on None.action_handler.
                    if self.agent_registry.get_agent_instance(selected_tool) is None:
                        msg = (
                            f"Agent '{selected_tool}' is configured but not instantiated/registered in this manager runtime. "
                            f"Add it under the manager's `agents:` list (so AgentLoader registers an instance), "
                            f"or expose it via a tool wrapper if it must be callable cross-manager."
                        )
                        logger.error(f"[{self.name}] {msg}")
                        self.blackboard.update_state_value("last_agent", self.name)
                        self.blackboard.update_state_value("error_message", msg)
                        # Force the manager loop to exit via error path rather than crash.
                        self.blackboard.update_state_value("error", True)
                        return
            else:
                logger.error(f"[{self.name}] '{selected_tool}' not found in tool, agent, or manager registry.")
                self.blackboard.update_state_value("last_agent", self.name)
                # Force the manager loop to exit via error path rather than spin forever.
                self.blackboard.update_state_value("error", True)
                return

        try:
            # This is read from the current local scope
            calling_agent = pending.get("calling_agent")

            if is_agent:
                self._execute_agent_call(calling_agent, selected_tool, tool_arguments)
            else:
                self._execute_tool_call(calling_agent, selected_tool, selected_config, tool_arguments)

        except Exception as e:
            logger.error(f"[{self.name}] Fatal error executing '{selected_tool}': {e}", exc_info=True)
            # Consider setting an error state on the blackboard for graceful exit
            sys.exit(1)

    def _execute_agent_call(self, calling_agent, called_agent_name, arguments):
        """Handles the logic for an agent calling another agent, including scope creation."""
        print(f"\n📞 [TOOL_CALLER] Agent call: '{calling_agent}' → '{called_agent_name}'")
        print(f"   Arguments: {json.dumps(arguments) if arguments else 'None'}")

        # 1. Log the agent call request within the CALLER's current scope.
        logger.info(f"[{self.name}] Logging agent call from '{calling_agent}' to '{called_agent_name}'")
        tool_request_msg = Message(
            data_type='tool_request',
            sender=calling_agent,
            content=f"Calling agent '{called_agent_name}' with arguments: {json.dumps(arguments)}."
        )
        self.blackboard.add_msg(tool_request_msg)

        # 2. Generate a new, unique ID for the CALLEE's execution scope.
        new_scope_id = f"scope_{uuid.uuid4()}"
        logger.info(f"[{self.name}] Creating new scope '{new_scope_id}' for call: {calling_agent} -> {called_agent_name}")
        print(f"   Creating new scope: {new_scope_id}")

        # 3. Push the new scope_id onto the call stack. The Blackboard will
        #    automatically create a new local scope for state variables.
        self.blackboard.push_call_context(calling_agent, called_agent_name, new_scope_id)

        # 4. Invoke the agent. Any messages it creates will be auto-tagged
        #    with the new_scope_id by the Blackboard.
        agent_instance = self.agent_registry.get_agent_instance(called_agent_name)
        if agent_instance is None:
            msg = (
                f"Cannot invoke agent '{called_agent_name}': no instance registered in AgentRegistry. "
                f"This usually means the current manager did not load it under `agents:` "
                f"(or it was expected to be called via a tool wrapper instead)."
            )
            logger.error(f"[{self.name}] {msg}")
            print(f"   ❌ {msg}")
            # Undo the pushed call context so the manager doesn't get stuck with a leaked scope.
            try:
                self.blackboard.pop_call_context()
            except Exception:
                pass
            # Mark error for the manager loop.
            try:
                self.blackboard.update_state_value("error_message", msg)
                self.blackboard.update_state_value("error", True)
                self.blackboard.update_state_value("last_agent", self.name)
            except Exception:
                pass
            return
        agent_input_msg = Message(agent_input=arguments)
        print(f"   ▶️ Invoking {called_agent_name}...")
        agent_tool_result = agent_instance.action_handler(agent_input_msg)
        print(f"   ◀️ {called_agent_name} finished")

        # Store agent result where ToolResultHandler can find it, then process it immediately.
        # ToolResultHandler will pop the call context and return control to the calling agent.
        try:
            agent_result_payload = None
            if isinstance(agent_tool_result, ToolResult):
                agent_result_payload = agent_tool_result.data if isinstance(agent_tool_result.data, dict) else agent_tool_result.content
            elif isinstance(agent_tool_result, dict):
                agent_result_payload = agent_tool_result
            else:
                agent_result_payload = str(agent_tool_result) if agent_tool_result is not None else None

            # Store in the current scope (callee scope) so handler can retrieve it via get_state_value().
            self.blackboard.update_state_value(f"{called_agent_name}_result", agent_result_payload)
        except Exception:
            pass

        tool_result_handler = self.agent_registry.get_agent_instance('tool_result_handler')
        if tool_result_handler:
            tool_result_handler.action_handler(Message())
        else:
            logger.error(f"[{self.name}] Could not find tool_result_handler for agent result handling")

    def _execute_tool_call(self, calling_agent, tool_name, tool_config, arguments):
        """Handles the logic for calling a standard, non-agent tool (or non-intra manager agent)."""
        logger.info(f"[{self.name}] Calling standard tool: {tool_name}")

        # Log the request in the current scope
        tool_request_msg = Message(
            data_type="tool_request",
            sender=calling_agent,
            content=f"Calling tool {tool_name} with arguments {json.dumps(arguments)}",
        )
        self.blackboard.add_msg(tool_request_msg)

        # MCP tools: dispatch via MCP client (no local tool_class).
        if tool_config.get("backend") == "mcp":
            tool_result = self._execute_mcp_tool_call(
                calling_agent=calling_agent,
                tool_name=tool_name,
                tool_config=tool_config,
                arguments=arguments or {},
            )
            self.blackboard.update_state_value('last_agent', self.name)

            tool_result_handler = self.agent_registry.get_agent_instance('tool_result_handler')
            if tool_result_handler:
                tool_result_handler.process_tool_result_direct(tool_result)
            else:
                logger.error(f"[{self.name}] Could not find tool_result_handler")
            return

        tool_class = tool_config.get("tool_class")
        if not tool_class:
            logger.error(f"[{self.name}] Tool '{tool_name}' has no valid tool_class.")
            exit(1)
            return

        tool_instance = tool_class()
        allowed_read_files = self.blackboard.get_state_value("allowed_read_files")
        allowed_write_files = self.blackboard.get_state_value("allowed_write_files")
        # Wrap arguments in a ToolMessage for the tool
        tool_data = arguments or {}
        if isinstance(tool_data, dict):
            tool_data = dict(tool_data)
            if allowed_read_files is not None:
                tool_data["allowed_read_files"] = allowed_read_files
            if allowed_write_files is not None:
                tool_data["allowed_write_files"] = allowed_write_files
        tool_message = ToolMessage(
            tool_name=tool_name,
            tool_data=tool_data
        )
        # Use run() if available (goes through approval check), otherwise execute()
        if hasattr(tool_instance, 'run'):
            tool_result = tool_instance.run(tool_message)
        else:
            tool_result = tool_instance.execute(tool_message)

        self.blackboard.update_state_value('last_agent', self.name)
        
        # Directly call tool_result_handler to process the result
        # This keeps tool calls in the same scope (no delegator routing needed)
        tool_result_handler = self.agent_registry.get_agent_instance('tool_result_handler')
        if tool_result_handler:
            tool_result_handler.process_tool_result_direct(tool_result)
        else:
            logger.error(f"[{self.name}] Could not find tool_result_handler")

    def _execute_mcp_tool_call(self, calling_agent, tool_name: str, tool_config: dict, arguments: dict) -> ToolResult:
        """
        Execute an MCP-backed tool call and convert the result into EmiAi's ToolResult.
        """
        server_id = tool_config.get("mcp_server_id")
        mcp_tool_name = tool_config.get("mcp_tool_name")
        if not server_id or not mcp_tool_name:
            return ToolResult(
                result_type="error",
                content=f"MCP tool misconfigured: missing mcp_server_id or mcp_tool_name for {tool_name}",
                data={"tool_name": tool_name, "tool_config": tool_config},
            )

        server_entry = self.tool_registry.get_mcp_server_entry(server_id)
        if not server_entry:
            return ToolResult(
                result_type="error",
                content=f"MCP server entry not loaded: {server_id}",
                data={"tool_name": tool_name, "server_id": server_id},
            )

        # Unwrap EmiAi tool envelope -> MCP arguments object.
        args_obj = arguments.get("arguments") if isinstance(arguments.get("arguments"), dict) else arguments
        # If structured outputs forced nullable-but-required fields, drop nulls before sending
        # to the MCP server so it receives only explicitly provided arguments.
        if isinstance(args_obj, dict):
            args_obj = {k: v for k, v in args_obj.items() if v is not None}
            # Some search APIs treat `order` as meaningful only when `sort` is provided.
            # Avoid passing `order` alone (can trigger server-side validation bugs).
            if ("sort" not in args_obj or not args_obj.get("sort")) and "order" in args_obj:
                args_obj.pop("order", None)

        # Timeout policy
        timeout_s = 20.0
        try:
            pol = server_entry.get("policy") if isinstance(server_entry, dict) else None
            if isinstance(pol, dict) and isinstance(pol.get("call_timeout_seconds"), int):
                timeout_s = float(pol["call_timeout_seconds"])
        except Exception:
            pass

        try:
            call_resp = mcp_stdio_call_tool(
                server_entry=server_entry,
                tool_name=str(mcp_tool_name),
                arguments=args_obj or {},
                timeout_s=timeout_s,
            )
            text, is_error, attachments = format_mcp_tool_result_content(call_resp)
            call_resp_history = sanitize_mcp_call_response_for_history(call_resp, attachments)
            return ToolResult(
                result_type="error" if is_error else "tool_result",
                content=text,
                data={
                    "backend": "mcp",
                    "server_id": server_id,
                    "mcp_tool_name": mcp_tool_name,
                    "arguments_sent": args_obj,
                    # IMPORTANT: store sanitized response (no base64 blobs) so planner history stays small.
                    "call_response": call_resp_history,
                    "attachments": attachments,
                },
            )
        except Exception as e:
            return ToolResult(
                result_type="error",
                content=f"MCP call failed ({server_id}/{mcp_tool_name}): {e}",
                data={"backend": "mcp", "server_id": server_id, "mcp_tool_name": mcp_tool_name},
            )
