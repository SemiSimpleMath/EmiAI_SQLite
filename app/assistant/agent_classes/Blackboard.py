from jinja2 import Template

from app.assistant.agent_classes.Agent import Agent  # Base Agent class
from app.assistant.utils.pydantic_classes import Message
from colorama import Fore
from app.assistant.utils.printing import print_standout_text, message_print
from app.assistant.utils.time_utils import get_local_time_str

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


class Blackboard(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)

    def action_handler(self, message: Message):
        """
        Handles blackboard summarization when enough messages have accumulated.
        """
        self._set_agent_busy()
        try:
            self._update_blackboard_state(message)

            if not self.blackboard.time_to_summarize():
                return None

            # Store the incoming message (typically from Planner)
            self._store_incoming_message(message)

            try:
                messages = self.construct_prompt(message)
            except Exception as e:
                print(f"[{self.name}] Error during prompt construction: {e}")
                logger.error(f"[{self.name}] Error during prompt construction: {e}")
                return None
            print("\n\n----- BLACKBOARD DEBUG -----")
            print(messages, f"{self.name} Summarization Input")

            print("\n\n\n\n")

            schema = self.config.get('structured_output')
            result = self._run_llm_with_schema(messages, schema)

            if result is None:
                return None

            try:
                self._process_summary_result(result)
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

    def _process_summary_result(self, result_dict):
        """
        Stores summary output and prunes pre-plan messages.
        """
        logger.debug(f"[{self.name}] Processing summary result")

        self.blackboard.update_state_value('last_agent', self.name)
        self._apply_llm_result_to_state(result_dict)
        self.blackboard.remove_messages_before_last_plan()

        logger.debug(f"[{self.name}] Recorded response in blackboard history.")
        print_standout_text(
            f"Summary: {result_dict.get('summary')}\nFinal Answer Content: {result_dict.get('final_answer_content')}",
            Fore.LIGHTMAGENTA_EX,
            title=f"{self.name} Output"
        )


    def get_user_prompt(self, message: Message = None):
        print("\n\n-- Blackboard: Creating user prompt --\n\n")
        user_prompt_template = self.config.get("prompts", {}).get("user", "")
        if not user_prompt_template:
            logger.error(f"[{self.name}] No user prompt found.")
            return f"No user prompt available for {self.name}."

        # default to [] not {}
        prompt_injections = self.config.get("user_context_items") or []

        print("PROMPT INJECTION AT USER PROMPT: ", prompt_injections)

        if prompt_injections:
            user_context = self.generate_injections_block(prompt_injections, message)
        else:
            user_context = {}

        if message and message.agent_input:
            user_context["agent_input"] = message.agent_input

        try:
            rendered = Template(user_prompt_template) \
                .render(**user_context) \
                .replace("\n\n", "\n")
            return rendered
        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering prompt: {e}\nContext was: {user_context}")
            raise


    def generate_injections_block(self, prompt_injections, message=None):
        """
        Generates a context dictionary for prompt rendering.
        Pulls values from Blackboard state_dict and calls `self.get_tool_descriptions()` for tools.
        """
        context = {"date_time": get_local_time_str()}


        if message and message.content:
            context["incoming_message"] = message.content.strip()

        rag_fields = self.config.get("rag_fields", [])

        for key in prompt_injections:
            print(key)
            if key in context:
                continue

            if key == "task":
                a = 1

            if key == "tool_descriptions":
                tool_desc = self.get_tool_descriptions() or {}
                if not isinstance(tool_desc, dict):
                    logger.error(f"[{self.name}] tool_descriptions must be a dictionary but got: {tool_desc}")
                    tool_desc = {}

                context[key] = tool_desc
                continue

            if key == "history_to_summarize":
                recent_history = self.blackboard.get_messages_before_last_plan()
                history_str = " ".join(msg.content for msg in recent_history if msg.content)
                context[key] = history_str
                continue

            else:
                value = self.blackboard.get_state_value(key, None)

                if key in rag_fields:
                    retrieved_value = self.retrieve_rag_context(value)
                    if retrieved_value:
                        value = (value or "") + f"\n\n[Retrieved Context]:\n{retrieved_value}"

                context[key] = value
                print(f"putting into context dict {key}, {value} ")
        print(f"[{self.name}] Injected context: {context}")
        #logger.info(f"[{self.name}] Injected context: {context}")
        return context
