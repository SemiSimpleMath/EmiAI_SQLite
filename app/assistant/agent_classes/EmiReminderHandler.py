from datetime import datetime, timezone
import uuid

from jinja2 import Template

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
from app.assistant.agent_classes.Agent import Agent


from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class EmiReminderHandler(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)
        self.blackboard = Blackboard() # make sure we use local blackboard

    def scheduler_event_interval_handler(self, message):
        #print("At emi scheduler event handler" , message)
        self.action_handler(message)

    def scheduler_event_one_time_event_handler(self, message):
        #print("At emi scheduler event handler" , message)
        self.action_handler(message)

    def action_handler(self, message: Message):
        # Check if scheduler/reminders feature is enabled
        from app.assistant.user_settings_manager.user_settings import can_run_feature, get_settings_manager
        if not can_run_feature('scheduler'):
            logger.info("⏸️ Scheduler feature disabled in settings - skipping reminder")
            return None

        # Check if quiet mode is active for scheduler/reminders using user's configured quiet hours
        from zoneinfo import ZoneInfo
        settings_manager = get_settings_manager()
        if settings_manager.is_quiet_mode_active('scheduler'):
            now_local = datetime.now(ZoneInfo("America/Los_Angeles"))
            logger.info(f"⏸️ Quiet hours active for scheduler - skipping reminder (current time: {now_local.strftime('%H:%M %Z')})")
            return None

        self._set_agent_busy()
        try:
            event_payload = message.data.get('event_payload')
            payload_content = event_payload.get('payload_message')

            reminder_dict = {"reminder_data": payload_content}

            self.blackboard.reset_blackboard()
            # Populate local blackboard with reminder data
            for key, value in reminder_dict.items():
                self.blackboard.update_state_value(key, value)

            try:
                messages = self.construct_prompt(message)
            except Exception as e:
                logger.error(f"[{self.name}] Error during prompt construction: {e}")
                print(f"\n{'=' * 80}")
                print(f"🛑 FATAL: EmiReminderHandler failed to construct prompt")
                print(f"   Error: {e}")
                print(f"{'=' * 80}\n")
                exit(1)

            schema = self.config.get('structured_output')

            result = self._run_llm_with_schema(messages, schema)

            result = self.process_llm_result(result)

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
                print(f"\n{'=' * 80}")
                print(f"🛑 FATAL: EmiReminderHandler failed to generate injections block")
                print(f"   Error: {e}")
                print(f"{'=' * 80}\n")
                exit(1)
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
            print(f"\n{'=' * 80}")
            print(f"🛑 FATAL: EmiReminderHandler failed to render user prompt")
            print(f"   Error: {e}")
            print(f"{'=' * 80}\n")
            exit(1)


    def process_llm_result(self, response):

        tts_str = response.get('tts_str')
        feed_str = response.get('feed_str')
        content = "Reminder came from scheduler: " + tts_str


        id_str = str(uuid.uuid4())
        user_msg_bb = Message(
            data_type='emi_msg',
            sender=self.name,
            receiver=None,
            content=content,
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            is_chat=True,
        )
        user_msg_data = UserMessageData(
            feed=feed_str,
            tts=True,
            tts_text=tts_str
        )

        user_msg_feed = UserMessage(
            data_type='user_msg',
            sender=self.name,
            receiver=None,
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            user_message_data=user_msg_data
        )


        self.blackboard.add_msg(user_msg_bb)
        self.publish_chat_to_user(user_msg_feed)

        return


    def publish_chat_to_user(self, message: Message):
        message.event_topic = 'socket_emit'
        DI.event_hub.publish(message)



