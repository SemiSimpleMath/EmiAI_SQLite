class ControlNode:
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        self.name = name
        self.blackboard = blackboard
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry

    def action_handler(self, message):
        """Each control node implements its own logic here."""
        # self.blackboard.update_state_value('next_agent', None) Don't forget this!
        raise NotImplementedError("ControlNode must define action_handler")
