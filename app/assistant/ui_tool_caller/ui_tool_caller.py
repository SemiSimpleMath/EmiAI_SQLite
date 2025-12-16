from datetime import datetime, timezone
import logging
import uuid

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import ToolMessage, Message, UserMessageData, UserMessage

import threading
logger = logging.getLogger(__name__)

def set_missing_fields_to_None(model_cls, data: dict) -> dict:
    """Ensure all required fields in model_cls are present in data, setting missing ones to None."""
    result = {}
    for field_name in model_cls.model_fields:
        result[field_name] = data.get(field_name, None)
    return result


class UIToolCaller():
    def __init__(self):
        DI.event_hub.register_event('ui_tool_caller', self.handle_ui_tool_event)


    def handle_ui_tool_event(self, event):
        print("event at tool_caller ", event)
        action = event.data.get("action")
        meta_data = event.data.get("meta_data")

        try:
            tool_name = event.data.get("tool_name")
            args = event.data.get("arguments", {})

            tool_config = DI.tool_registry.get_tool(tool_name)
            inner_args_class = tool_config['tool_args']['args']
            outer_args_class = tool_config['tool_args']['arguments']

            # Ensure all fields are present (missing ones set to None)
            safe_args = set_missing_fields_to_None(inner_args_class, args)

            inner_args_instance = inner_args_class(**safe_args)
            outer_args_instance = outer_args_class(tool_name=tool_name, arguments=inner_args_instance)

            tool_data = outer_args_instance.model_dump()
            tool_message = ToolMessage(tool_name=tool_name, tool_data=tool_data)

            print("tool_message is: ", tool_message)

            tool_class = tool_config["tool_class"]
            threading.Thread(
                target=self._execute_tool_async,
                args=(tool_class, tool_message),
                daemon=True
            ).start()

            msg = Message(
                agent_input=f"Action taken was {action}. Object metadata {meta_data}"
            )
            feedback_msg = DI.agent_factory.create_agent('tool_feedback').action_handler(msg)

            self.process_message(feedback_msg)

        except Exception as e:
            logger.exception(f"Error handling UI tool event: {e}")



    def _execute_tool_async(self, tool_class, tool_message):
        try:
            tool_instance = tool_class()
            result = tool_instance.execute(tool_message)

            if result and hasattr(result, "content"):
                logger.info(f"Tool execution result: {result.content}")
            else:
                logger.warning("Tool returned no result content.")

        except Exception as e:
            logger.exception(f"Error in async tool execution: {e}")




    def process_message(self, response):
        print("This is the LLM response\n\n\n")
        print(response)
        print("\n\n\n")
        
        # Debug logging
        logger.debug(f"Processing response: {response}")
        logger.debug(f"Response type: {type(response)}")
        logger.debug(f"Response attributes: {dir(response)}")
        
        # Agent returns structured output in response.data
        result = response.data
        
        logger.debug(f"response.data: {result}")
        
        if not result or not isinstance(result, dict):
            logger.error(f"Expected dict in response.data, got {type(result)}: {result}")
            return
            
        chat_str = result.get('chat_str')
        tts_str = result.get('tts_str')

        # Use chat_str if available, otherwise use a default message
        content = chat_str if chat_str else "Tool feedback processed"

        id_str = str(uuid.uuid4())
        user_msg_bb = Message(
            data_type='emi_msg',
            sender="ui_tool_caller",
            receiver=None,
            content=content,
            timestamp=datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            is_chat=True,
        )
        user_msg_data = UserMessageData(
            chat=chat_str,
            tts=True,
            tts_text=tts_str
        )

        user_msg_feed = UserMessage(
            data_type='user_msg',
            sender="ui_tool_caller",
            receiver=None,
            timestamp=datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            user_message_data=user_msg_data
        )


        DI.global_blackboard.add_msg(user_msg_bb)
        self.publish_chat_to_user(user_msg_feed)

    def publish_chat_to_user(self, message: Message):
        message.event_topic = 'socket_emit'
        DI.event_hub.publish(message)