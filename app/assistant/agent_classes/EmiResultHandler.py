from datetime import datetime, timezone
import json
import uuid
from jinja2 import Template
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
from app.assistant.agent_classes.Agent import Agent

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class EmiResultHandler(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)

    def emi_result_request_handler(self, message: Message):
        logger.info(f"[{self.name}] Handling external EMI result message")
        self.action_handler(message)

    def action_handler(self, message: Message):
        self._set_agent_busy()
        try:
            self.blackboard = Blackboard() # make sure we use local blackboard

            tool_result = message.tool_result
            content = tool_result.content
            self.blackboard.reset_blackboard()
            
            # Populate local blackboard with result data
            try:
                data = json.loads(content)
                for key, value in data.items():
                    self.blackboard.update_state_value(key, value)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"[{self.name}] Content is not JSON, using as-is: {e}")
                # Content might be a plain string, that's okay
                self.blackboard.update_state_value("content", content)

            try:
                messages = self.construct_prompt(message)
            except Exception as e:
                logger.error(f"[{self.name}] Error during prompt construction: {e}")
                return None

            schema = self.config.get('structured_output')
            result = self._run_llm_with_schema(messages, schema)

            # Add the original user message to the global blackboard for history
            user_chat_msg = Message(
                data_type="user_msg", 
                content=message.agent_input, 
                is_chat=True,
                role='user'  # Set the role for user messages
            )
            DI.global_blackboard.add_msg(user_chat_msg)

            try:
                result = self.process_llm_result(result)
            except Exception as e:
                logger.error(f"[{self.name}] Error processing LLM result: {e}")
                raise

            return result
        except Exception as e:
            logger.error(f"[{self.name}] Unhandled exception in action_handler: {e}")
            print(f"🛑 [{self.name}] action_handler exception: {e}")
            raise
        finally:
            # ALWAYS release the busy lock, even on exceptions
            try:
                self._set_agent_idle()
            except Exception as e:
                logger.error(f"[{self.name}] Failed to release busy lock: {e}")
                print(f"🛑 [{self.name}] Failed to release busy lock: {e}")



    def get_user_prompt(self, message: Message = None):
        user_prompt_template = self.config.get("prompts", {}).get("user", "")
        if not user_prompt_template:
            logger.error(f"[{self.name}] No user prompt found.")
            return f"No user prompt available for {self.name}."
        prompt_injections = self.config.get("user_context_items", {})
        print("DEBUG EMI ", prompt_injections)
        if prompt_injections is not None:
            try:
                user_context = self.generate_injections_block(prompt_injections, message)
            except Exception as e:
                logger.error(f"[{self.name}] Error generating injections: {e}")
                print(f"🛑 [{self.name}] Error generating injections: {e}")
                raise e
        else:
            user_context = {}
        agent_input = None
        if message:
            agent_input = message.agent_input
        if agent_input:
            user_context["agent_input"] = agent_input

        try:
            template = Template(user_prompt_template)
            rendered_output = template.render(**user_context or {}).replace('\n\n', '\n')
            return rendered_output
        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering user prompt: {e}")
            raise


    def process_llm_result(self, response):

        task = response.get("task")
        answer = response.get("answer")
        interesting_info = response.get("interesting_info")
        methods = response.get("methods")
        sources = response.get("sources")
        meta_data = response.get("meta_data")
        feed = response.get("feed")
        chat_str = task + answer + interesting_info + methods + sources + meta_data
        feed_str = feed
        content = {"chat": chat_str, "feed": feed_str }


        id_str = str(uuid.uuid4())
        user_msg_bb = Message(
            data_type='emi_msg',
            sender=self.name,
            receiver=None,
            content=json.dumps(content),
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            is_chat=True,
        )
        user_msg_data = UserMessageData(chat=chat_str, feed=feed_str)  # i guess usermessagedata needs strings?
        user_msg_chat = UserMessage(
            data_type='user_msg',
            sender=self.name,
            receiver=None,
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            user_message_data=user_msg_data
        )

        global_blackboard = DI.global_blackboard

        global_blackboard.add_msg(user_msg_bb)
        self.publish_chat_to_user(user_msg_chat)

        return


    def publish_chat_to_user(self, message: Message):
        message.event_topic = 'socket_emit'
        DI.event_hub.publish(message)



