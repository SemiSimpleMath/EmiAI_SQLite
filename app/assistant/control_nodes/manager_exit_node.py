import logging
from app.assistant.utils.pydantic_classes import Message
from app.assistant.control_nodes.control_node import ControlNode

logger = logging.getLogger(__name__)

class ManagerExitNode(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message: Message):
        logger.info(f"[{self.name}] Manager exit - exiting the entire manager.")
        
        # Exit the manager
        self.blackboard.update_state_value('exit', True)
        self.blackboard.update_state_value('next_agent', None)
        self.blackboard.update_state_value('last_agent', self.name)
