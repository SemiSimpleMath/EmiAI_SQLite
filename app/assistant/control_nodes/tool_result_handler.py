import json
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.control_nodes.control_node import ControlNode

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

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
        logger.debug(f"Processing tool result: {tool_result}")

        # Convert the tool result into a summarized format
        tool_result_msg = DI.data_conversion_module.convert(tool_result, "summary")

        # Convert summary to JSON string for logging and blackboard storage
        content_str = json.dumps(tool_result_msg, indent=4)
        logger.debug(f"Summarized tool result: {content_str}")

        # For tool calls, get the calling agent from blackboard
        calling_agent = self.blackboard.get_state_value('original_calling_agent')
        
        # Create a message object with the processed tool result
        # scope_id will be auto-tagged with current scope by add_msg
        message = Message(
            data_type="tool_result",
            sub_data_type=tool_result.result_type,
            sender="tool",  # Generic sender for tools
            receiver=calling_agent,
            content=content_str,
            data=tool_result_msg,
        )

        # Store processed tool result in blackboard
        # This will auto-tag with the current scope_id
        self.blackboard.add_msg(message)

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
