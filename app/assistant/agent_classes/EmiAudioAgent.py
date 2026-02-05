# Note to coding agents: This file should not be modified without user permission.
from datetime import datetime, timezone
import os
import uuid
from typing import Any, Dict, List, Optional, Union

from jinja2 import Template

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.time_utils import get_local_time_str
from app.assistant.entity_management.entity_card_injector import EntityCardInjector
from app.assistant.utils.assistant_name import get_assistant_name
from app.services.llm_factory import LLMFactory

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class EmiAudioAgent(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)

    def _get_first_image_attachment(self, message: Optional[Message]) -> Optional[Dict[str, Any]]:
        if not message:
            return None
        meta = getattr(message, "metadata", None)
        if not isinstance(meta, dict):
            return None
        attachments = meta.get("attachments")
        if not isinstance(attachments, list):
            return None
        for att in attachments:
            if isinstance(att, dict) and att.get("type") == "image" and att.get("path"):
                return att
        return None

    def emi_chat_speaking_mode_request_handler(self, message):
        # Check if test mode
        if getattr(message, 'test_mode', False):
            logger.info("🧪 Processing in TEST MODE - no database storage")
            # Process normally but skip database storage
            self.action_handler(message)
        else:
            # Normal processing with database storage
            self.action_handler(message)


    def _add_extra_msgs(self, message: Message):
        content = message.agent_input
        att = self._get_first_image_attachment(message)
        if att:
            fname = att.get("original_filename") or os.path.basename(str(att.get("path") or "image"))
            marker = f"[image attached: {fname}]"
            if isinstance(content, str) and content.strip():
                content = f"{content}\n{marker}"
            else:
                content = marker

        user_chat_msg = Message(
            data_type="user_msg",
            content=content,
            is_chat=True,
            role='user',  # Set the role for user messages
            test_mode = message.test_mode
        )
        # EmiAgent uses global blackboard natively, so only add once
        self.blackboard.add_msg(user_chat_msg)

    def construct_prompt(self, message: Message = None) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = super().construct_prompt(message)
        att = self._get_first_image_attachment(message)
        if not att:
            return msgs

        try:
            image_path = str(att.get("path"))
            fname = att.get("original_filename") or os.path.basename(image_path)
            marker = f"\n\n[image attached: {fname}]"
            user_text = msgs[1].get("content", "")
            if not isinstance(user_text, str):
                user_text = str(user_text)
            msgs[1]["content"] = [
                {"type": "input_text", "text": f"{user_text}{marker}"},
                {"type": "image_path", "path": image_path},
            ]
        except Exception as e:
            logger.error(f"[{self.name}] Failed to build multimodal prompt: {e}")

        return msgs

    def call_llm(
        self,
        messages: List[Dict[str, Any]],
        response_format: Optional[Union[dict, str]] = None,
        use_json: bool = False,
    ) -> Any:
        image_paths: List[str] = []
        try:
            for msg in messages or []:
                content = msg.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "image_path" and part.get("path"):
                            image_paths.append(str(part["path"]))

            params = dict(self.llm_params)
            if response_format is not None:
                params["response_format"] = response_format

            if image_paths:
                params["llm_provider"] = "openai"
                params["engine"] = "gpt-5.2"
                llm_interface = LLMFactory.get_llm_interface(llm_provider="openai")
            else:
                if self.llm_interface is None:
                    self.llm_interface = self.get_llm_interface()
                llm_interface = self.llm_interface

            response = llm_interface.structured_output(messages, use_json=use_json, **params)
            self._check_for_quota_error(response)
            return response
        finally:
            for p in image_paths:
                try:
                    if p and os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass

    def get_user_prompt(self, message: Message = None):
        user_prompt_template = self.config.get("prompts", {}).get("user", "")
        if not user_prompt_template:
            logger.error(f"[{self.name}] No user prompt found.")
            print(f"\n{'=' * 80}")
            print(f"🛑 FATAL: EmiAudioAgent '{self.name}' has no user prompt configured")
            print(f"   Check the agent's config.yaml for 'prompts.user'")
            print(f"{'=' * 80}\n")
            exit(1)
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

        try:
            template = Template(user_prompt_template)
            rendered_output = template.render(**user_context or {}).replace('\n\n', '\n')
            return rendered_output
        except Exception as e:
            logger.error(f"[{self.name}] ERROR while rendering user prompt: {e}")
            raise


    def process_llm_result(self, response: dict):
        think_carefully = response.get("think_carefully")
        msg_for_user = response.get("msg_for_user")
        reason = response.get("reason")
        have_all_info = response.get("have_all_info")
        call_team = response.get("call_team")
        msg_for_agent = response.get("msg_for_agent")
        information_for_agent = response.get("information_for_agent")

        print(
            f"Think Carefully: {think_carefully}\n\nMSG for user: \n{msg_for_user} \n\n {reason}, "
            f"\n\nMSG for Agent: \n{msg_for_agent}, \n\nHave all info: \n{have_all_info}\n\n{information_for_agent}, Call Team: \n{call_team}"
        )

        id_str = str(uuid.uuid4())
        user_msg_bb = Message(
            data_type='emi_msg',
            sender=self.name,
            receiver=None,
            content=msg_for_user,
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            is_chat=True,
        )
        user_msg_data = UserMessageData(
            chat=msg_for_user,
            tts=True,
            tts_text=msg_for_user
        )


        user_msg_chat = UserMessage(
            data_type='user_msg',
            sender=self.name,
            receiver=None,
            timestamp= datetime.now(timezone.utc),
            id=id_str,
            role='assistant',
            user_message_data=user_msg_data
        )

        if call_team:
            agent_msg = Message(
                task=msg_for_agent,
                data_type='agent_msg',
                sender=self.name,
                receiver=None,
                content=msg_for_agent,
                information=information_for_agent,
                role='assistant',
            )
            task_notification_msg = Message(
                task=msg_for_agent,
                data_type='agent_msg',
                sub_data_type=['agent_notification'],
                sender=self.name,
                receiver=None,
                content=f"Following message was sent to the team: [{msg_for_agent}] \nThis is now in progress and no further action is necessary until we hear from the team. REPEAT Do not take action again unless specifically told to do so!\n",
                information=information_for_agent,
                role='user',
                is_chat=True,
            )

            self.blackboard.add_msg(user_msg_bb)
            self.blackboard.add_msg(task_notification_msg)
            # Also add to global blackboard for persistence
            DI.global_blackboard.add_msg(user_msg_bb)
            DI.global_blackboard.add_msg(task_notification_msg)

            self.publish_chat_to_user(user_msg_chat)
            assistant_name = get_assistant_name()
            self.notify_user_of_agent_call(f"{assistant_name} is working on it.")
            self.publish_message_to_tool(agent_msg)
        else:

            self.blackboard.add_msg(user_msg_bb)
            # Also add to global blackboard for persistence
            DI.global_blackboard.add_msg(user_msg_bb)
            self.publish_chat_to_user(user_msg_chat)

        return

    def publish_message_to_tool(self, message: Message):
        message.event_topic = 'team_selector_manager_request'
        DI.event_hub.publish(message)

    def publish_chat_to_user(self, message: Message):
        message.event_topic = 'socket_emit'
        DI.event_hub.publish(message)
    def notify_user_of_agent_call(self, message_text: str):
        """
        Sends a brief notification message to the user UI.

        Args:
            message_text (str): The notification content.
        """
        assistant_name = get_assistant_name()
        notification_message = UserMessage(
            data_type="agent_msg",
            sender=assistant_name,
            receiver=None,
            content=message_text,
            user_message_data=UserMessageData(chat=message_text)
        )
        self.publish_chat_to_user(notification_message)



    def generate_injections_block(self, prompt_injections, message=None):
        """
        Generates a context dictionary for prompt rendering.
        Modified to use entity card injection instead of RAG.
        """
        context = {"date_time": get_local_time_str()}

        if message and message.content:
            context["incoming_message"] = message.content.strip()

        # Check if any entity_* fields are requested (like entity_summary, entity_aliases, etc.)
        entity_keys = [key for key in prompt_injections if key.startswith("entity_")]
        
        # If entity fields requested, detect entities and create persistent injection messages
        if entity_keys:
            user_input = message.content.strip() if message and message.content else None
            if user_input:
                # Get the user's input from message.content (the actual user chat)
                # Find entities in the user's input using EntityCatalog
                injector = EntityCardInjector()
                detected_entities = injector.detect_entities_in_text(user_input)
                if detected_entities:
                    logger.info(f"Found entities in user input: {detected_entities}")
                    
                    # Check which entities are already in history to avoid duplicates
                    existing_entities = set()
                    for msg in self.blackboard.get_messages():
                        if "entity_card_injection" in (getattr(msg, "sub_data_type", []) or []):
                            # Get entity name from message metadata if available
                            if hasattr(msg, 'metadata') and msg.metadata and 'entity_name' in msg.metadata:
                                existing_entities.add(msg.metadata['entity_name'])
                            # Fallback: extract from content (for backward compatibility)
                            elif msg.content and msg.content.startswith("[Entity Context -"):
                                try:
                                    entity_name_start = msg.content.find("[Entity Context - ") + 17
                                    entity_name_end = msg.content.find("]:", entity_name_start)
                                    if entity_name_end > entity_name_start:
                                        existing_entity = msg.content[entity_name_start:entity_name_end]
                                        existing_entities.add(existing_entity)
                                except Exception as e:
                                    logger.debug(f"[{self.name}] Could not parse entity name from message: {e}")
                    
                    # Create separate injection messages for each entity (avoiding duplicates)
                    for entity_name in detected_entities:
                        if entity_name in existing_entities:
                            logger.info(f"Skipping duplicate injection for entity: {entity_name}")
                            continue
                            
                        # Get entity card content
                        card_content = injector.get_entity_card_content(entity_name)
                        if card_content:
                            injection_msg = Message(
                                data_type="agent_msg",
                                sub_data_type=["entity_card_injection"],
                                sender=self.name,
                                receiver=None,
                                content=f"[Entity Context - {entity_name}]:\n{card_content}",
                                timestamp=datetime.now(timezone.utc),
                                role='assistant',
                                is_chat=True,
                                metadata={'entity_name': entity_name}
                            )
                            # Add to both local and global blackboard for history construction
                            self.blackboard.add_msg(injection_msg)
                            DI.global_blackboard.add_msg(injection_msg)
                            logger.info(f"Created injection message for entity: {entity_name}")
        
        # Now process all context items
        for key in prompt_injections:
            # Skip entity_* keys - they don't go in context, entities are in history
            if key.startswith("entity_"):
                continue
            
            # Continue with normal processing
            if False:  # Old code removed
                pass
            
            # Normal context processing continues below
            print(key)
            if key in context:
                continue

            if key == "tool_descriptions":
                tool_desc = self.get_tool_descriptions() or {}
                if not isinstance(tool_desc, dict):
                    logger.error(f"[{self.name}] tool_descriptions must be a dictionary but got: {tool_desc}")
                    tool_desc = {}

                context[key] = tool_desc
                continue

            if key == "history":
                history = self.blackboard.get_messages()
                history_str = "Old messages (from oldest to newest):"

                # Include the latest chat summary (if present), then include only
                # messages that have NOT been marked as summarized.
                latest_summary = None
                for msg in reversed(history):
                    try:
                        if "history_summary" in (getattr(msg, "sub_data_type", []) or []) and getattr(msg, "content", None):
                            latest_summary = msg.content
                            break
                    except Exception:
                        continue

                if latest_summary:
                    history_str += f"\n[Chat Summary]: {latest_summary}\n"

                for msg in history:
                    if not msg.is_chat:
                        print("skipping non chat message")
                        continue

                    # Skip chat messages already summarized (but keep entity injections and the summary itself).
                    try:
                        sub = getattr(msg, "sub_data_type", None)
                        sub_set = set(sub or [])
                        if "history_summary" in sub_set:
                            continue
                        # Slash commands are handled out-of-band; keep them out of general chat history.
                        if "slash_command" in sub_set:
                            continue
                        meta = getattr(msg, "metadata", None)
                        if (
                            "entity_card_injection" not in sub_set
                            and isinstance(meta, dict)
                            and bool(meta.get("summarized", False))
                        ):
                            continue
                    except Exception as e:
                        logger.warning(f"[{self.name}] Failed to apply history filters: {e}", exc_info=True)

                    # Include ALL messages in history for LLM context (including entity card injections)
                    role = "User" if msg.data_type == 'user_msg' else "Emi"
                    history_str += f" {role}: {msg.content}"
                context[key] = history_str
                continue
            else:
                value = self.blackboard.get_state_value(key, None)
                if key not in context and value is not None:
                    context[key] = value
                print(f"putting into context dict {key}, {value} ")
        
        print(f"[{self.name}] Injected context: {context}")
        return context
