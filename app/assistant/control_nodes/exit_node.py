import logging
from app.assistant.utils.pydantic_classes import Message
from app.assistant.control_nodes.control_node import ControlNode

logger = logging.getLogger(__name__)

class ExitNode(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message: Message):
        logger.info(f"[{self.name}] Returning control to calling agent.")
        
        # Check if we have a call stack to return to
        call_stack = self.blackboard.get_state_value('call_stack', [])
        if call_stack:
            # Pop the current call context and return to the calling agent
            popped_context = self.blackboard.pop_call_context()
            if popped_context:
                # Return control to the calling agent
                self.blackboard.update_state_value('next_agent', popped_context['calling_agent'])
                logger.info(f"[{self.name}] Returning control to calling agent: {popped_context['calling_agent']}")
            else:
                # No more call context, this shouldn't happen
                logger.error(f"[{self.name}] No call context found but call stack exists")
                self.blackboard.update_state_value('exit', True)
        else:
            # No call stack, this shouldn't happen for called agents
            logger.error(f"[{self.name}] No call stack found - agent should not be using exit_node")
            self.blackboard.update_state_value('exit', True)
        
        self.blackboard.update_state_value('last_agent', self.name)
