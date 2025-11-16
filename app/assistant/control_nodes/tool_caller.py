import json
import sys
import uuid  # Import the uuid library to generate unique scope IDs

from app.assistant.utils.pydantic_classes import Message, ToolResult, ToolMessage
from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.utils.logging_config import get_logger

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
        selected_tool = self.blackboard.get_state_value("selected_tool")
        tool_arguments = self.blackboard.get_state_value("tool_arguments")


        self.blackboard.update_state_value("next_agent", None)

        if not selected_tool:
            logger.error(f"[{self.name}] Missing tool selection from blackboard.")
            return

        logger.info(f"[{self.name}] Executing: '{selected_tool}' with arguments: {tool_arguments}")

        # --- Determine if the target is an agent, a tool, or a control node ---
        is_agent = False
        selected_config = self.tool_registry.get_tool(selected_tool)
        if not selected_config:
            selected_config = self.agent_registry.get_agent_config(selected_tool)
            if selected_config:
                if selected_config.get("type") == "control_node":
                    logger.info(f"[{self.name}] Transitioning to control node: {selected_tool}")
                    self.blackboard.update_state_value('next_agent', selected_tool)
                    return
                else:
                    is_agent = True
            else:
                logger.error(f"[{self.name}] '{selected_tool}' not found in tool or agent registry.")
                return

        try:
            # This is read from the current local scope
            calling_agent = self.blackboard.get_state_value('original_calling_agent')

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
        agent_input_msg = Message(agent_input=arguments)
        print(f"   ▶️ Invoking {called_agent_name}...")
        agent_instance.action_handler(agent_input_msg)
        print(f"   ◀️ {called_agent_name} finished")

        # The call context is intentionally NOT popped here. A result handler will do that.

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

        tool_class = tool_config.get("tool_class")
        if not tool_class:
            logger.error(f"[{self.name}] Tool '{tool_name}' has no valid tool_class.")
            exit(1)
            return

        tool_instance = tool_class()
        # Wrap arguments in a ToolMessage for the tool
        tool_message = ToolMessage(
            tool_name=tool_name,
            tool_data=arguments or {}
        )
        tool_result = tool_instance.execute(tool_message)

        # Store the tool result in blackboard
        self.blackboard.update_state_value("tool_result", tool_result)
        self.blackboard.update_state_value('last_agent', self.name)
        
        # Directly call tool_result_handler to process the result
        # This keeps tool calls in the same scope (no delegator routing needed)
        tool_result_handler = self.agent_registry.get_agent_instance('tool_result_handler')
        if tool_result_handler:
            tool_result_handler.process_tool_result_direct()
        else:
            logger.error(f"[{self.name}] Could not find tool_result_handler")

