# app/assistant/agent_registry/agent_factory

from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


def get_agent_registry():
    from app.assistant.agent_registry.agent_registry import AgentRegistry
    return AgentRegistry()

def get_tool_registry():
    from app.assistant.lib.tool_registry.tool_registry import ToolRegistry
    return ToolRegistry()


class AgentFactory:
    def __init__(self, agent_registry, tool_registry):
        self.agent_registry = agent_registry
        self.tool_registry = tool_registry

    def create_agent(self, agent_name, blackboard=None):
        agent_class = self.agent_registry.get_agent_class(agent_name)
        if not agent_class:
            logger.error(f"❌ No class found for agent '{agent_name}'. Cannot instantiate.")
            return None

        logger.info(f"📥 Creating new instance of agent: {agent_name}")

        # Use the provided blackboard or create a new one
        blackboard = blackboard or Blackboard()

        agent = agent_class(
            name=agent_name,
            blackboard=blackboard,
            agent_registry=self.agent_registry,
            tool_registry=self.tool_registry,
            llm_params=self.agent_registry.get_agent_config(agent_name).get("llm_params", {}),
        )

        # Dynamically register events from config using DI.event_hub
        agent_config = self.agent_registry.get_agent_config(agent_name)
        events = agent_config.get('events', [])
        print("DEBUG EVENTS: ", events)
        for event in events:
            handler = getattr(agent, f"{event}_handler", None)
            if callable(handler):
                DI.event_hub.register_event(event, handler)
                logger.info(f"✅ Registered event '{event}' for agent {agent_name}")
            else:
                logger.warning(f"⚠️ Event '{event}' defined in config but no handler found in {agent_name}.")
        return agent



agent_input = """
From: John Doe <john.doe@example.com>
To: user@example.com
Subject: Project Deadline Extension
Date: Mon, 10 Mar 2025 14:45:00 -0800

Hi Team,

I wanted to inform you that the deadline for the Alpha Project has been extended by one week due to unexpected delays in the testing phase. The new deadline is now March 20, 2025.

Please ensure all outstanding tasks are completed by then. Let me know if there are any blockers.

Best,
John
"""


def main():
    agent = DI.agent_factory.create_agent('email_parser')
    msg = Message(
        data_type="task",
        sender="System",
        receiver=None,
        content="",
        agent_input=agent_input
    )
    agent.action_handler(msg)


if __name__ == "__main__":
    main()
