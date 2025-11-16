from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.utils.pydantic_classes import Message
import logging

logger = logging.getLogger(__name__)


class GracefulExitControlNode(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message):
        """Each control node implements its own logic here."""
        content = """Graceful exit has been triggered.  This means that something unexpected has happened.  It could be that max task length
            has been reached or there was more serious error.  At this point recovery is impossible and we need to exit the task and write down
            our partial findings.  Be sure to note what was found, but also what we did not get to look at.  If there are indications in the logs for
            errors, please report those as well.
            """
        msg = Message(
            sender = "graceful_exit_node",
            content = content
        )
        self.blackboard.append_state_value('final_answer_content', content)
        self.blackboard.add_msg(msg)
        
        # Check if we have a call stack to return to
        call_stack = self.blackboard.get_state_value('call_stack', [])
        if call_stack:
            # Pop the current call context and return to the calling agent
            popped_context = self.blackboard.pop_call_context()
            if popped_context:
                # Return control to the calling agent
                self.blackboard.update_state_value('next_agent', popped_context['calling_agent'])
                logger.info(f"[{self.name}] Graceful exit - returning control to calling agent: {popped_context['calling_agent']}")
            else:
                # No more call context, exit the manager
                self.blackboard.update_state_value('exit', True)
                self.blackboard.update_state_value('next_agent', None)
        else:
            # No call stack, exit the manager
            self.blackboard.update_state_value('exit', True)
            self.blackboard.update_state_value('next_agent', None)
        
        self.blackboard.update_state_value('last_agent', self.name)
