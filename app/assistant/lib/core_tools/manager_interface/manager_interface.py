# File: assistant/lib/core_tools/manager_interface.py

from app.assistant.utils.pydantic_classes import ToolMessage, Message, ToolResult
from app.assistant.ServiceLocator.service_locator import DI

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


"""
When a manager calls another manager it does it as a tool call in a sync manner.

When a manager is called via async manner with event hub, it will return the result via event hub.
"""

class ManagerInterface:
    """
    Generic interface for executing manager requests, handling both direct calls and event hub requests.
    """

    def __init__(self, manager_name: str):
        """
        Initializes the manager interface.

        Args:
        - manager_name (str): The name of the manager to interact with.
        """
        self.manager_name = manager_name

    def execute(self, tool_message: ToolMessage) -> ToolResult:
        """
        Handles execution of the manager request.

        Args:
        - tool_message (ToolMessage): Incoming request message.

        Returns:
        - ToolResult: The result of the manager execution.
        """
        try:

            print(f"DEBUG: Creating manager for: {self.manager_name}")
            manager_instance_handler = DI.manager_instance_handler
            name, instance = manager_instance_handler.find_available_instance(self.manager_name)

            if not instance:
                new_name = manager_instance_handler.get_unique_name(self.manager_name)
                instance = DI.multi_agent_manager_factory.create_manager(self.manager_name, name=new_name)
                manager_instance_handler.register(new_name, instance, self.manager_name)

            self.manager = instance

        except Exception as e:
            raise RuntimeError(f"Failed to create a manager for {self.manager_name}: {e}")

        tool_data = tool_message.tool_data or {}
        args = tool_data.get('arguments', {}) if isinstance(tool_data.get('arguments'), dict) else {}
        task = args.get('task')
        information = args.get('information')
        data = tool_data.get('data') if isinstance(tool_data.get('data'), dict) else {}

        task_file = args.get('task_file')
        if isinstance(task_file, str) and task_file.strip():
            data = dict(data)
            data["task_file"] = task_file.strip()
        request_id = tool_message.request_id

        # Determine the content for the manager message
        # Priority: task > content > question > information
        manager_content = None
        if task:
            manager_content = task
        elif tool_message.content:
            manager_content = tool_message.content
        elif tool_message.tool_data.get('arguments', {}).get('question'):
            manager_content = tool_message.tool_data.get('arguments', {}).get('question')
        elif information:
            manager_content = information
        else:
            # If no content is available, use a default message
            manager_content = f"Process request for {self.manager_name}"

        # Create a standardized manager request message
        manager_message = Message(
            event_topic="task_request",
            sender=self.manager_name,
            receiver=None,
            content=manager_content,
            task=task,  # Keep task if provided, otherwise None
            information=information,
            request_id=None,
            data=data
        )
        logger.info(f"{self.manager_name.capitalize()}: Processing content '{manager_content[:50]}...' with ID {request_id}")

        try:
            print("Sending off the manager message", manager_message)

            result = self.manager.request_handler(manager_message) # here we actually send to the manager and get a response back

            print(f"back from manager {self.manager_name.capitalize()}: Received result.")
            logger.info(f"{self.manager_name.capitalize()}: Received result.")

            if request_id:
                print("REQUEST ID FOUND")
                tool_message = ToolMessage(
                    tool_name=self.manager_name,
                    sender=self.manager_name,
                    receiver="emi_result_handler",
                    content=result.content,  # Pass content from ToolResult
                    tool_result=result,  # Embed ToolResult
                    request_id=request_id,
                    tool_data={}  # Can be empty or include additional context
                )
                event_hub = DI.event_hub
                tool_message.event_topic = "emi_result_request"
                event_hub.publish(tool_message)
                return None  # Do not return result when broadcasting

            else:
                return result

        except Exception as e:
            print("Something went horribly wrong....")
            logger.error(f"{self.manager_name.capitalize()} execution failed: {e}")
            error_result = ToolResult(result_type="error", content=str(e))
            return error_result


