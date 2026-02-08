from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.utils.pipeline_state import get_pending_tool, set_pending_tool_arguments
from app.assistant.utils.logging_config import get_logger
import re

logger = get_logger(__name__)


class EmiTeamSelectorArgumentsNode(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message):
        """
        Lightweight argument builder for team selector routing.
        For manager tools in this flow, we pass task/information through verbatim.
        """
        self.blackboard.update_state_value("next_agent", None)
        self.blackboard.update_state_value("last_agent", self.name)

        pending = get_pending_tool(self.blackboard) or {}
        selected_tool = pending.get("name")
        if not isinstance(selected_tool, str) or not selected_tool.strip():
            logger.error("[%s] Missing pending tool name; cannot build arguments.", self.name)
            return

        task = self.blackboard.get_state_value("task")
        information = self.blackboard.get_state_value("information")

        if selected_tool == "run_task_spec":
            arguments = {
                "task_query": task,
                "information": information,
            }
            if isinstance(task, str):
                match = re.search(r"(tasks/[A-Za-z0-9_\-./]+\.md)", task)
                if match:
                    arguments["task_file"] = match.group(1)
        else:
            arguments = {
                "task": task,
                "information": information,
            }

        set_pending_tool_arguments(self.blackboard, arguments)
