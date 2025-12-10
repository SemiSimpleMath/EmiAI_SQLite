from datetime import datetime, timezone
from jinja2 import Template
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
from app.assistant.agent_classes.Agent import Agent

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class AskUser(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)
        self.question_id = None
    def ask_user_request_handler(self, message: Message):
        print("At ask user request handler")
        logger.info(f"[{self.name}] Handling ask_user request message")
        self.action_handler(message)

    def action_handler(self, message: Message):
        self._set_agent_busy()
        try:
            self.blackboard = Blackboard() # make sure we use local blackboard

            tool_result = message.tool_result
            print(tool_result)
            question = tool_result.content
            print(question)
            data_list = tool_result.data_list
            self.question_id = data_list[0].get('question_id', None)
            print(self.question_id)

            self.blackboard.update_state_value('question', question)

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

        tts_str = response.get('tts_str')
        formatted_str = response.get('formatted_str')


        user_msg_data = UserMessageData(
            feed=formatted_str,
            tts=True,
            tts_text=tts_str
        )

        user_msg_feed = UserMessage(
            data_type='user_msg',
            sender=self.name,
            receiver=None,
            timestamp= datetime.now(timezone.utc),
            id=self.question_id,
            role='assistant',
            user_message_data=user_msg_data
        )


        question_msg = UserMessage(
            data_type='user_msg',
            sender=self.name,
            receiver=None,
            timestamp=datetime.now(timezone.utc),
            id=self.question_id,
            role='assistant',
            user_message_data=UserMessageData(
                widget_data=[{
                    "data_type": "ask_user",
                    "question": formatted_str,
                    "question_id": self.question_id
                }]
            )
        )


        self.publish_to_user(user_msg_feed)
        self.publish_to_user(question_msg)

        return


    def publish_to_user(self, message: UserMessage):
        message.event_topic = 'socket_emit'
        DI.event_hub.publish(message)

