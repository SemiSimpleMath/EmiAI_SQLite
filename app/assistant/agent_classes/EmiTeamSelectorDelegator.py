
from app.assistant.agent_classes.Agent import Agent  # Base Agent class
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


class EmiTeamSelectorDelegator(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent=parent)
        self.config = agent_registry.get_agent_config(self.name)
        self.flow_config = None

    def action_handler(self, message: Message):
        """
        Determines the next agent to act.
        - If a strict mapping exists in `flow_config.yaml`, follow it.
        - Otherwise, treat as a hard error (no LLM fallback).
        """

        self.blackboard.update_state_value('next_agent', None) ## all agents start by setting this to None so the only way this will ever be not None at delegator is if some agent just set it.
        if message.content:
            self.blackboard.add_msg(message)

        data = message.data
        self.flow_config = data.get('flow_config')

        assert self.flow_config is not None, print(f"Flow config is none in {self.name}")

        last_agent = self.blackboard.get_state_value('last_agent')
        logger.info(f"[{self.name}] Last agent: {last_agent}")

        # Step 1: Check if we have a strict flow mapping
        next_node = self.pick_next_agent(last_agent)

        if next_node:
            if next_node == "exit":
                self.blackboard.update_state_value('complete', True)
            logger.info(f"[{self.name}] Delegating to: {next_node}")
            self.blackboard.update_state_value('next_agent', next_node)
            return
        logger.error(f"[{self.name}] No explicit mapping found in flow_config.state_map for last_agent={last_agent}")
        self.blackboard.update_state_value("error_message", "Delegator routing failed: missing state_map entry")
        self.blackboard.update_state_value("error", True)
        self.blackboard.update_state_value("last_agent", self.name)

    def pick_next_agent(self, last_agent: str) -> str:
        """
        Picks the next agent based on the flow config.
        If no explicit mapping or fallback exists, returns None (which triggers LLM reasoning).
        """
        # Override for planner agent
        planner_agent_recommends = self.blackboard.get_state_value('planner_recommends_agent', None)
        if planner_agent_recommends:
            return planner_agent_recommends
        if last_agent is None:
            last_agent = "NO_PREVIOUS_AGENT"
        state_map = self.flow_config.get("state_map", {})
        return state_map.get(last_agent, None)
