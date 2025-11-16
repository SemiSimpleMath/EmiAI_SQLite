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
        print(f"At process_llm_result {self.name}")
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

        print("result dict at FinalAnswer: ", result_dict)




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
                
                # Build history of tool calls/results with intelligent summary preference
                history_str = self.build_recent_history(agent_messages)
                
                # Append any agent/planner result messages (final conclusions before exit)
                # Filter by sub_data_type="result" which marks final decisions
                result_messages = [msg for msg in agent_messages 
                                  if getattr(msg, "sub_data_type", None) == "result"]
                
                if result_messages:
                    # Include all result messages (could be multiple agents)
                    for result_msg in result_messages:
                        if hasattr(result_msg, 'content') and result_msg.content:
                            sender = getattr(result_msg, 'sender', 'Agent')
                            history_str += f"\n\n=== {sender.upper()} FINAL RESULT ===\n{result_msg.content}"
                
                context[key] = history_str
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
