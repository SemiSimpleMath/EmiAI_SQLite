# File: app/assistant/lib/global_tools/base_tool.py

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

from abc import ABC, abstractmethod

from app.assistant.utils.pydantic_classes import ToolMessage, Message, ToolResult


class BaseTool(ABC):
    """
    Abstract base class for all tools.
    """
    name: str

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def execute(self, tool_message: 'ToolMessage') -> ToolResult:
        """
        Executes the tool with the given tool message.

        Parameters:
        - tool_message (ToolMessage): The message triggering the tool execution.

        Returns:
        - Message: The result of the tool execution.
        """
        pass
