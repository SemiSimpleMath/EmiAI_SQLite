
import threading


from app.assistant.utils.pydantic_classes import Message, ToolMessage
from app.assistant.utils.pipeline_state import get_pending_tool
from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.entity_management.entity_card_injector import entity_card_injector

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class EmiTeamSelectorToolCaller(ControlNode):
    def __init__(self, name, blackboard, agent_registry, tool_registry):
        super().__init__(name, blackboard, agent_registry, tool_registry)

    def action_handler(self, message):
        """Executes the selected tool asynchronously and moves on."""
        self.blackboard.update_state_value('next_agent', None) ## all agents start by setting this to None so the only way this will ever be not None at delegator is if some agent just set it.
        pending = get_pending_tool(self.blackboard) or {}
        selected_tool = pending.get("name")
        arguments = pending.get("arguments") if isinstance(pending.get("arguments"), dict) else {}
        if not selected_tool or not isinstance(arguments, dict):
            logger.error("ToolCaller: Missing or invalid tool selection or arguments.")
            return

        logger.info(f"🔧 Asynchronously executing tool: {selected_tool} with arguments: {arguments}")

        # Log the tool request
        tool_call_msg = Message(
            data_type='agent_msg',
            sender="ToolCaller",
            receiver='All',
            content=f"{selected_tool} was called asynchronously with arguments {arguments}",
            task=self.blackboard.get_state_value('task'),
            information=self.blackboard.get_state_value('information'),
            role='assistant',
        )
        self.blackboard.add_msg(tool_call_msg)

        # Apply entity card injection to arguments if they contain text content
        enhanced_arguments = self._enhance_tool_data_with_entity_cards(arguments)

        tool_data = {
            "tool_name": selected_tool,
            "arguments": enhanced_arguments,
        }

        tool_request_message = ToolMessage(
            data_type='tool_request',
            sender=self.name,
            receiver='ToolManager',
            tool_name=selected_tool,
            tool_data=tool_data,
            content=f"Arguments for tool {selected_tool} are ready.",
            request_id= "42222"  # request id is used as a flag to do this async elsewhere.
        )

        selected_tool_entry = self.tool_registry.get_tool(selected_tool)
        if not selected_tool_entry or "tool_class" not in selected_tool_entry:
            logger.error(f"ToolCaller: Tool '{selected_tool}' not found in registry.")
            return

        tool_class = selected_tool_entry["tool_class"]

        # Run the tool in a separate thread to avoid blocking
        threading.Thread(target=self._execute_tool_async, args=(tool_class, tool_request_message), daemon=True).start()
        self.blackboard.update_state_value('last_agent', self.name)
        print(f"✅ Tool '{tool_request_message.tool_name}' started asynchronously.")
        logger.info(f"✅ Tool '{tool_request_message.tool_name}' started asynchronously.")

    def _enhance_tool_data_with_entity_cards(self, tool_data: dict) -> dict:
        """
        Enhance tool data with entity card injections for relevant text fields
        """
        if not tool_data:
            return tool_data
        
        enhanced_data = tool_data.copy()
        
        # Fields that might contain text that could benefit from entity card injection
        text_fields = ['task', 'information', 'content', 'message', 'description', 'query']
        
        for field in text_fields:
            if field in enhanced_data and enhanced_data[field]:
                field_value = str(enhanced_data[field])
                enhanced_value, injected_entities = entity_card_injector.inject_entity_cards_into_text(
                    field_value, context_type="team_call"
                )
                if injected_entities:
                    logger.info(f"Enhanced tool data field '{field}' with entity cards: {injected_entities}")
                    enhanced_data[field] = enhanced_value
        
        return enhanced_data

    def _execute_tool_async(self, tool_class, tool_request_message):
        """Executes the tool asynchronously without waiting for a response."""
        try:
            tool_instance = tool_class()  # instantiate the class
            tool_instance.execute(tool_request_message)
            logger.info(f"✅ Tool '{tool_request_message.tool_name}' executed asynchronously.")
        except Exception as e:
            logger.error(f"❌ ToolCaller: Error executing tool {tool_request_message.tool_name}: {e}. With request {tool_request_message}")

