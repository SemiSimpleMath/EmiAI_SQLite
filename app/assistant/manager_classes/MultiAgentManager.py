import json
import sys
import traceback
import uuid

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.agent_registry.agent_loader import AgentLoader
from app.assistant.utils.pydantic_classes import Message, ToolResult
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class MultiAgentManager:
    def __init__(self, name: str, manager_config: dict, tool_registry, agent_registry):
        """
        Base class for multi-agent managers.

        Manages agent execution flow, blackboard state, and tool registry.

        Parameters:
        - name: Name of the manager instance.
        - manager_config: Configuration for the manager.
        - tool_registry: Shared tool registry.
        - agent_registry: Registry containing agent definitions.
        """
        self.name = name
        self.blackboard = Blackboard()
        self.tool_registry = tool_registry
        self.agent_registry = agent_registry
        self.manager_config = manager_config

        # Load agents from config
        self.agent_loader = AgentLoader(
            config_source=self.manager_config,
            blackboard=self.blackboard,
            agent_registry=self.agent_registry,
            tool_registry=self.tool_registry,
            parent=self
        )
        self.agent_loader.load_agents()

        self.busy = True  # Used to determine manager availability

        self.flow_config = manager_config.get("flow_config")
        self._register_configured_events()
        self.set_manager_role_binding()

    def set_manager_role_binding(self):
        self.blackboard.update_state_value('role_bindings', self.manager_config.get("role_bindings", {}))

    def resolve_role_binding(self, role_name):
        bindings = self.blackboard.get_state_value('role_bindings', {})
        return bindings.get(role_name, role_name)

    def is_busy(self) -> bool:
        """Check if this manager is currently processing tasks."""
        return self.busy

    def _register_configured_events(self):
        events = self.manager_config.get("events", [])
        for event_name in events:
            handler_name = f"{event_name}_handler"
            handler = getattr(self, handler_name, None)
            if handler is None:
                raise ValueError(f"Handler '{handler_name}' not found in manager '{self.name}' for event '{event_name}'")
            event_hub = DI.event_hub
            try:
                event_hub.register_event(event_name, handler)
            except Exception as e:
                # Duplicate registration or conflicting handler
                print(f"❌ Event registration failed in manager '{self.name}'")
                print(f"Event: {event_name}")
                print(f"Handler: {handler} (ID: {id(handler)})")
                print("🔍 Stack trace of registration attempt:")
                traceback.print_stack(limit=10)
                raise e

    def request_handler(self, user_message: Message):
        """
        Handles a new task request by setting up the blackboard and invoking Delegator.
        """
        logger.info(f"🛠️ {self.name} received task: {user_message.content}")

        try:
            self.blackboard.reset_blackboard()
            self.blackboard.update_state_value('task', user_message.task)
            self.blackboard.update_state_value('information', user_message.information)

            # Manager loop counters (reset every request).
            # These are useful for delegator-gated behaviors (e.g., run critic every N loops).
            try:
                self.blackboard.update_global_state_value("manager_name", self.name)
                self.blackboard.update_global_state_value("manager_loop_count", 0)    # 0-based
                self.blackboard.update_global_state_value("manager_loop_number", 1)   # 1-based (next loop number)
                self.blackboard.update_global_state_value(
                    "manager_max_cycles",
                    int(self.manager_config.get("max_cycles", 30)),
                )
            except Exception:
                # Keep request startup resilient; counters are optional.
                pass


            if user_message.data is not None:
                if isinstance(user_message.data, dict):
                    for key, value in user_message.data.items():
                        self.blackboard.update_state_value(key, value)
            self.blackboard.add_request_id(user_message.request_id)
            self.set_manager_role_binding()  # put role bindings back

            return self.run_agent_loop()
        except Exception as e:
            logger.error(f"❌ Error in request_handler: {e}")
            sys.exit(1)  # Hard exit on failure

    def _run_loop(self, max_cycles, delegator, delegator_data):
        cycles = 0
        while True:
            print(f"\n{'='*80}")
            print(f"🔄 MANAGER LOOP - Cycle {cycles + 1}/{max_cycles}")
            print(f"{'='*80}")

            # Expose current loop counters on the blackboard BEFORE delegator runs.
            # This makes them visible to delegator/planner logic without relying on local variables.
            try:
                self.blackboard.update_state_value("manager_loop_count", cycles)       # 0-based completed loops so far
                self.blackboard.update_state_value("manager_loop_number", cycles + 1) # 1-based current loop number
                # Also update global so nested scopes can always read it.
                self.blackboard.update_global_state_value("manager_loop_count", cycles)
                self.blackboard.update_global_state_value("manager_loop_number", cycles + 1)
            except Exception:
                pass

            # Cooperative cancellation hook (used by orchestrators).
            if self.blackboard.get_state_value("cancelled", False) or self.blackboard.get_state_value("cancel", False):
                logger.warning(f"⚠️ {self.name} cancelled. Exiting loop.")
                return "cancelled"
            
            if cycles >= max_cycles:
                logger.warning(f"⚠️ {self.name} reached max cycles ({max_cycles}).")
                return "max_cycles"
            if self.blackboard.get_state_value("exit", False):
                logger.info(f"✅ Task completed by {self.name}. Exiting loop.")
                return "success"
            if self.blackboard.get_state_value('error'):
                logger.warning(f"⚠️ {self.name} detected error state. Exiting loop.")
                return "error"

            # 1. Always call delegator to handle routing logic
            delegator.action_handler(Message(data_type='agent_activation', data=delegator_data))
            next_agent_name = self.blackboard.get_state_value('next_agent')
            
            print(f"\n🎯 [MANAGER LOOP] After delegator, next_agent = '{next_agent_name}'")

            if not next_agent_name:
                logger.error("❌ Delegator did not determine a next agent. Exiting.")
                sys.exit(1)

            next_agent_name = self.resolve_role_binding(next_agent_name)
            next_agent = self.agent_registry.get_agent_instance(next_agent_name)
            if not next_agent:
                logger.error(f"❌ Failed to retrieve agent: {next_agent_name}. Exiting.")
                sys.exit(1)

            # ---Root Scope Creation Logic ---
            is_root_scope = False
            if not self.blackboard.get_current_call_context():
                # 2. If we are at the top level, create a temporary "root" scope.
                is_root_scope = True
                root_scope_id = f"root_scope_{uuid.uuid4()}"
                logger.info(f"[{self.name}] Creating root scope '{root_scope_id}' for '{next_agent_name}'")
                self.blackboard.push_call_context(self.name, next_agent_name, root_scope_id)

            # 3. Activate the agent (it now runs within a guaranteed scope).
            next_agent.action_handler(Message(data_type='agent_activation'))


            cycles += 1

    def run_agent_loop(self):
        """
        Runs the agent execution loop until the task is complete or max cycles are reached.
        """
        logger.info(f"🔄 Starting execution loop for {self.name}")
        max_cycles = self.manager_config.get("max_cycles", 30)
        self.delegator_name = self.resolve_role_binding('delegator')

        try:
            delegator = self.agent_registry.get_agent_instance(self.delegator_name)
            if delegator is None:
                logger.error(f"❌ No delegator found in manager: {self.name}")
            self.blackboard.update_state_value('last_agent', self.delegator_name)

            exit_reason = self._run_loop(max_cycles, delegator, {"flow_config": self.flow_config})
            return self.handle_exit_reason(exit_reason)

        except Exception as e:
            logger.error(f"❌ Fatal error in agent loop: {e}")
            sys.exit(1)  # Exit on any unexpected failure

    def handle_exit_reason(self, exit_reason):
        if exit_reason == "success":
            return self.handle_exit()
        elif exit_reason == "max_cycles":
            return self.handle_exit_max_limit()
        elif exit_reason == "error":
            return self.handle_exit_error()
        else:
            return self.handle_unknown_exit()

    def handle_exit(self):
        print(f"[{self.name}] Exiting via control node.")

        final_raw = self.blackboard.get_state_value("final_answer")
        final_data = final_raw
        if final_raw is None:
            final_raw = ""

        content = final_raw if isinstance(final_raw, str) else json.dumps(final_raw)
        self.busy = False

        return ToolResult(
            result_type="final_answer",
            content=content,
            data_list=[{}],
            data=final_data
        )

    def handle_exit_max_limit(self):
        if self.flow_config.get("state_map", {}).get("max_limit"):
            exit_state = "max_limit"
        elif self.flow_config.get("state_map", {}).get("graceful_exit"):
            exit_state = "graceful_exit"
        elif self.flow_config.get("state_map", {}).get("error_exit"):
            exit_state = "error_exit"
        else:
            exit_state = "default_error_exit"
        return self.handle_graceful_exit(exit_state)

    def handle_exit_error(self):
        if self.flow_config.get("state_map", {}).get("error_exit"):
            exit_state = "error_exit"
        elif self.flow_config.get("state_map", {}).get("graceful_exit"):
            exit_state = "graceful_exit"
        else:
            exit_state = "default_error_exit"
        return self.handle_graceful_exit(exit_state)

    def handle_unknown_exit(self):
        if self.flow_config.get("state_map", {}).get("graceful_exit"):
            exit_state = "graceful_exit"
        elif self.flow_config.get("state_map", {}).get("error_exit"):
            exit_state = "error_exit"
        else:
            exit_state = "default_error_exit"
        return self.handle_graceful_exit(exit_state)

    def handle_graceful_exit(self, exit_state):
        """
        Runs the agent execution loop in graceful exit mode.
        """
        logger.info(f"🔄 Starting graceful exit loop for {self.name}, for state {exit_state}")
        max_cycles = self.manager_config.get("max_exit_cycles", 10)
        self.delegator_name = self.resolve_role_binding('delegator')
        self.blackboard.update_state_value('last_agent', exit_state)
        self.blackboard.update_state_value('error', False)  # Reset error for exit flow

        try:
            delegator = self.agent_registry.get_agent_instance(self.delegator_name)
            exit_reason = self._run_loop(max_cycles, delegator, {"flow_config": self.flow_config})
            return self.handle_graceful_exit_reason(exit_reason)
        except Exception as e:
            logger.error(f"❌ Fatal error in graceful exit loop: {e}")
            sys.exit(1)  # Exit on any unexpected failure

    def handle_graceful_exit_reason(self, exit_reason):
        if exit_reason == "success":
            return self.handle_exit()
        if exit_reason == "max_cycles" or exit_reason == "error":
            return self.handle_default_error_exit()

    def handle_default_error_exit(self):
        print(f"[{self.name}] Exiting via control node.")
        final_raw = self.blackboard.get_state_value("final_answer")
        final_raw_error = final_raw if isinstance(final_raw, str) else json.dumps(final_raw)
        final = (f"Something has gone wrong during {self.name} execution. "
                 f"Possible error: {self.blackboard.get_state_value('error', False)} "
                 f"Debug info: {final_raw_error}")

        self.busy = False

        return ToolResult(
            result_type="final_answer",
            content=final,
            data_list=[{}]
        )
