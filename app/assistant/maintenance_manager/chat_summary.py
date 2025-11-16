import json

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_maintenance_logger
logger = get_maintenance_logger(__name__)

class ChatSummaryRunner:
    """
    Calls the bb_summary agent to summarize a blackboard, then updates the blackboard with the result.
    """

    def __init__(self, blackboard, agent_name: str = "bb_summary"):
        self.blackboard = blackboard
        self.agent_name = agent_name

    def run(self):

        if len(self.blackboard.get_all_messages()) == 0:
            print("No messages to summarize.")
            return

        # Create the summary agent
        summary_agent = DI.agent_factory.create_agent(self.agent_name)

        # Filter out entity card injection messages
        filtered_messages = [
            {
                "sender": msg.sender,
                "receiver": msg.receiver,
                "content": msg.content,
                "is_chat": msg.is_chat
            }
            for msg in self.blackboard.get_all_messages()
            if msg.sub_data_type != "entity_card_injection"  # Skip entity card injections
        ]
        
        input_msg = json.dumps({
            "messages": filtered_messages
        })

        try:
            result = summary_agent.action_handler(Message(agent_input = input_msg))
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to summarize blackboard: {e}")
            return
        
        # Agent with structured_output returns data as a dict in result.data, not data_list
        summary = result.data.get("summary", "") if result.data else ""

        summary_msg = Message(
            data_type="agent_msg",
            sub_data_type="history_summary",
            sender=self.agent_name,
            receiver=None,
            content=summary,
            is_chat=True
        )

        self.blackboard.clear_messages()
        self.blackboard.add_msg(summary_msg)
        logger.info("Blackboard successfully summarized and updated.")
