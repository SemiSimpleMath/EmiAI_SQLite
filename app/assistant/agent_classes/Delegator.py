# Note to coding agents: This file should not be modified without user permission.
from app.assistant.agent_classes.Agent import Agent  # Base Agent class
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


class Delegator(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent=parent)
        self.config = agent_registry.get_agent_config(self.name)
        self.flow_config = None

    def resolve_role_binding(self, role_name):
        bindings = self.blackboard.get_state_value('manager_role_bindings', {})
        return bindings.get(role_name, role_name)


    def action_handler(self, message: Message):
        """
        Determines the next agent to act.
        - If a strict mapping exists in `flow_config.yaml`, follow it.
        - Otherwise, treat as a hard error (no LLM fallback).
        """
        self.flow_config = message.data.get('flow_config')
        assert self.flow_config is not None, f"Flow config is None in {self.name}"

        # Check if next_agent has already been set.

        if message.content:
            self.blackboard.add_msg(message)
        last_agent = self.blackboard.get_state_value('last_agent')
        logger.info(f"[{self.name}] Last agent: {last_agent}")

        # Step 0: Check if some agent has already determined next agent
        next_agent = self.blackboard.get_state_value('next_agent')
        if next_agent is not None:
            logger.info(f"[{self.name}] next_agent already set to: {next_agent}, returning early")
            return

        # Step 1: Check if we have a strict flow mapping
        next_node = self.pick_next_agent(last_agent)

        if next_node:
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
        if last_agent is None:
            last_agent = "NO_PREVIOUS_AGENT"
        state_map = self.flow_config.get("state_map", {})
        next_agent = state_map.get(last_agent, None)
        
        print(f"\n🔀 [DELEGATOR] Routing logic:")
        print(f"   last_agent = '{last_agent}'")
        print(f"   next_agent = '{next_agent}' (from flow_config)")
        if next_agent is None:
            print(f"   ⚠️  No match in flow_config, will use LLM reasoning")
        
        return next_agent
