# team_selector_manager.py
import sys
import traceback

from app.assistant.manager_classes.MultiAgentManager import MultiAgentManager

# Initialize logging
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class TeamSelectorManager(MultiAgentManager):
    def __init__(self, name, manager_config, tool_registry, agent_registry):
        """
        Initializes an instance of TeamSelectorManager with its specific configuration.
        """
        print("\n🔍 TeamSelectorManager instantiated")
        traceback.print_stack(limit=8)

        super().__init__(
            name=name,
            manager_config=manager_config,
            tool_registry=tool_registry,
            agent_registry=agent_registry
        )

    def set_manager_role_binding(self):
        self.blackboard.update_state_value('role_bindings', self.manager_config.get("role_bindings", {}))

    def resolve_role_binding(self, role_name):
        bindings = self.blackboard.get_state_value('role_bindings', {})
        return bindings.get(role_name, role_name)

    def team_selector_manager_request_handler(self, message):
        self.request_handler(message)

    def request_handler(self, user_message: Message):
        """
        Handles a new task request by setting up the blackboard and invoking Delegator.
        """
        logger.info(f"🛠️ {self.name} received task: {user_message.content}")

        try:
            self.blackboard.reset_blackboard()
            self.blackboard.update_state_value('task', user_message.task)
            self.blackboard.add_request_id(user_message.request_id)
            self.set_manager_role_binding()

            if user_message.information:
                self.blackboard.update_state_value('information', user_message.information)
            return self.run_agent_loop()
        except Exception as e:
            logger.error(f"❌ Error in request_handler: {e}")
            sys.exit(1)  # Hard exit on failure

    def run_agent_loop(self):
        """
        Runs the agent execution loop until the task is complete or max cycles are reached.
        """
        logger.info(f"🔄 Starting execution loop for {self.name}")

        max_cycles = self.manager_config.get("max_cycles", 30)
        cycles = 0
        self.delegator_name = self.resolve_role_binding('delegator')
        try:
            delegator = self.agent_registry.get_agent_instance(self.delegator_name)
            self.blackboard.update_state_value('last_agent', self.delegator_name)

            while cycles < max_cycles:
                if self.blackboard.get_state_value("complete", False):
                    logger.info(f"✅ Task completed by {self.name}. Exiting loop.")
                    return self.handle_exit()

                activation_message = Message(
                    data_type='agent_activation',
                    sender=self.name,
                    receiver='delegator',
                    data={"flow_config": self.flow_config}
                )
                delegator.action_handler(activation_message)

                next_agent_name = self.blackboard.get_state_value('next_agent')
                if not next_agent_name:
                    logger.error(f"❌ No next agent determined. Exiting program.")
                    sys.exit(1)  # Exit if no valid next agent is found

                if next_agent_name == "exit":
                    break
                next_agent = self.agent_registry.get_agent_instance(next_agent_name)
                if not next_agent:
                    logger.error(f"❌ Failed to retrieve agent: {next_agent_name}. Exiting program.")
                    sys.exit(1)  # Exit if the agent instance is missing

                activation_message = Message(
                    data_type='agent_activation',
                    sender=self.name,
                    receiver=next_agent_name,
                    data={}
                )
                next_agent.action_handler(activation_message)

                cycles += 1
            if cycles >= max_cycles:
                logger.warning(f"⚠️ {self.name} reached max cycles ({max_cycles}). Stopping execution.")
                sys.exit(1)  # Exit if max cycles are exceeded
            return


        except Exception as e:
            logger.error(f"❌ Fatal error in agent loop: {e}")
            sys.exit(1)  # Exit on any unexpected failure