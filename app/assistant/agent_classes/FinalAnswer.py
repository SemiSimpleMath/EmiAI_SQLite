import json

from app.assistant.agent_classes.Agent import Agent  # Base Agent class
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import get_local_time_str

logger = get_logger(__name__)

class FinalAnswer(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)


    def process_llm_result(self, result):
        self._maybe_print_llm_result(result)
        logger.info(f"[{self.name}] Processing LLM Result: {result}")

        # Update last acting agent
        self.blackboard.update_state_value('last_agent', self.name)

        # Convert result to dictionary
        result_dict = result

        # Convert any datetime objects to ISO strings for JSON serialization
        def convert_datetime_to_iso(obj):
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {key: convert_datetime_to_iso(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime_to_iso(item) for item in obj]
            else:
                return obj
        
        # Convert any datetime objects in the result
        serializable_result = convert_datetime_to_iso(result_dict)

        self.blackboard.update_state_value("final_answer", serializable_result)

        response_message = Message(
            data_type="agent_response",
            sender=self.name,
            receiver="Blackboard",
            content=json.dumps(serializable_result)
        )
        self.blackboard.add_msg(response_message)
        logger.info(f"[{self.name}] Recorded final answer.")

        # optional debug print handled by _maybe_print_llm_result




    def generate_injections_block(self, prompt_injections, message=None):
        """
        Generates a context dictionary for prompt rendering.
        Pulls values from Blackboard state_dict and calls `self.get_tool_descriptions()` for tools.
        """
        if not isinstance(prompt_injections, list):
            raise ValueError(
                f"[{self.name}] 'context_items' must be a list, but got: {type(prompt_injections).__name__} ({prompt_injections})")

        context = {"date_time": get_local_time_str()}

        if message and message.content:
            context["incoming_message"] = message.content.strip()

        rag_fields = self.config.get("rag_fields", [])
        context['rag'] = ""
        for key in prompt_injections:
            if key in context:
                continue

            if key == "tool_descriptions":
                tool_desc = self.get_tool_descriptions() or {}
                if not isinstance(tool_desc, dict):
                    logger.error(f"[{self.name}] tool_descriptions must be a dictionary but got: {tool_desc}")
                    tool_desc = {}
                context[key] = tool_desc
                continue

            if key == "allowed_nodes":
                allowed = self.get_allowed_nodes()
                agent_descriptions = []
                for name in allowed:
                    agent_config = self.agent_registry.get_agent_config(name) or {}
                    prompts = agent_config.get('prompts')
                    if not prompts:
                        description = ""
                    else:
                        description = agent_config['prompts'].get('description', "")
                    agent_descriptions.append({
                        "name": name,
                        "description": description
                    })
                context[key] = agent_descriptions
                continue

            if key == "recent_history":
                # Get messages from the current scope (root scope for final_answer)
                current_scope_id = self.blackboard.get_current_scope_id()
                agent_messages = self.blackboard.get_messages_for_scope(current_scope_id)
                # Strip raw tool traffic to avoid huge prompts, but keep summaries and planner results.
                agent_messages = [
                    msg for msg in agent_messages
                    if (getattr(msg, "data_type", None) or "") not in {
                        "tool_result",
                        "tool_request",
                    }
                ]

                # IMPORTANT:
                # FinalAnswer can become extremely slow/expensive if we dump the full tool trace.
                # Prefer high-signal agent results only (planner/agent "result" messages), and fall back to a small,
                # agent-only tail if no explicit results are present.
                history_parts = []

                # Append any agent/planner result messages (final conclusions before exit).
                # Filter by tag "result" which marks final decisions.
                result_messages = [
                    msg for msg in agent_messages
                    if "result" in (getattr(msg, "sub_data_type", []) or [])
                    and (getattr(msg, "data_type", None) or "") in {
                        "agent_result",
                        "agent_response",
                        "agent_msg",
                        "planner_result",
                        "tool_result_summary",
                    }
                ]

                def _truncate(text: str, max_chars: int = 8000) -> str:
                    t = (text or "").strip()
                    if len(t) <= max_chars:
                        return t
                    return t[:max_chars] + "\n\n[truncated]"

                if result_messages:
                    for result_msg in result_messages:
                        content = getattr(result_msg, "content", None) or ""
                        if content.strip():
                            sender = getattr(result_msg, "sender", "Agent")
                            history_parts.append(f"=== {str(sender).upper()} FINAL RESULT ===\n{_truncate(content)}")
                else:
                    # No explicit result messages: include a small tail of agent responses (exclude tool calls/results).
                    # This still gives the final answer model enough context without huge prompt bloat.
                    agent_only = [
                        msg for msg in agent_messages
                        if (getattr(msg, "data_type", None) or "") in {"agent_response", "agent_msg"}
                    ]
                    tail = agent_only[-12:]
                    for msg in tail:
                        sender = getattr(msg, "sender", "Agent")
                        content = getattr(msg, "content", None) or ""
                        if content.strip():
                            history_parts.append(f"[{sender}] {_truncate(content, max_chars=2000)}")

                context[key] = "\n\n".join([p for p in history_parts if p]).strip()
                continue


            value = self.blackboard.get_state_value(key, None)

            if key in rag_fields:
                scopes = self.config['rag_fields'][key]
                retrieved_value = self.retrieve_rag_context(value, scopes)
                if retrieved_value:
                    context['rag'] += f"{retrieved_value}\n"

            context[key] = value

        #logger.info(f"\n\n[{self.name}] Injected context: {context}\n\n")
        # print(f"DEBUG \n\n[{self.name}] Injected context: {context}\n\n")
        return context
