import json
from app.assistant.agent_classes.Agent import Agent  # Base Agent class
from app.assistant.utils.pydantic_classes import Message, ToolResult

from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.time_utils import get_local_time_str
from app.assistant.ServiceLocator.service_locator import DI

logger = get_logger(__name__)

# Differs from ordinary agent in 3 ways
# 1) records the message having plan_message subclass so we can tell apart messages before and after a plan
# 2) resets critique variables if any exist
# 3) Specifically references action variables to set next_agent or tool_call
class Planner(Agent):
    def __init__(self, name, blackboard, agent_registry, tool_registry, llm_params=None, parent=None):
        super().__init__(name, blackboard, agent_registry, tool_registry, llm_params, parent)

    def _create_response_message(self, result_dict: dict):
        """
        OVERRIDE: Creates the specific messages unique to the Planner.
        This replaces the generic message from the base Agent class.
        """
        # Determine if this is the final result (exit action) or intermediate plan
        action = result_dict.get("action", "")
        is_exit_action = "exit" in str(action).lower()
        
        # Tagging: use list-based subtypes for scalable routing.
        # Legacy "plan_message" is replaced by the tag "plan".
        sub_data_type = ["result"] if is_exit_action else ["plan"]
        
        # 1. Create the main planner_result message
        plan_message = Message(
            data_type="planner_result",
            sub_data_type=sub_data_type,
            sender=self.name,
            receiver="Blackboard",
            content=f"{self.name} created a plan: {json.dumps(result_dict)}"
        )
        self.blackboard.add_msg(plan_message)

        # 2. Create the optional summary message
        current_actions = self.blackboard.get_state_value(f'{self.name}_action_count', 0)
        summary_val = result_dict.get("summary")
        if summary_val and current_actions > 1:
            if not isinstance(summary_val, str):
                try:
                    summary_val = json.dumps(summary_val, ensure_ascii=False)
                except Exception as e:
                    logger.debug(f"[{self.name}] Could not JSON serialize summary, using str(): {e}")
                    summary_val = str(summary_val)

            summary_msg = Message(
                data_type="tool_result_summary",
                sub_data_type=["result_summary"],
                sender=self.name,
                receiver="Blackboard",
                content=summary_val.strip()
            )
            self.blackboard.add_msg(summary_msg)

    def process_llm_result(self, result):
        """
        The Planner's process method, which now cleanly integrates with the base class.
        """


        # ---  DEBUG Logging ---
        print(f"\n\n--- LLM RESULT for {self.name} ---")
        print(json.dumps(result, indent=2) if isinstance(result, dict) else result)
        print("---------------------------------\n")
        # --- End of New Code --


        # Step 1: Validate input (same as parent)
        if isinstance(result, str):
            logger.error(f"[{self.name}] LLM returned a string: {result}")
            result_dict = {"error": result, "action": "error"}
        elif not isinstance(result, dict):
            logger.error(f"[{self.name}] LLM result is not a dict: {type(result)}")
            result_dict = {"error": f"Invalid result type: {type(result)}", "action": "error"}
        else:
            result_dict = result

        # --- Call the shared logic from the parent class ---
        self._apply_llm_result_to_state(result_dict)

        # --- Call its own overridden and unique logic ---
        self._create_response_message(result_dict)

        # Update last acting agent in the local scope
        self.blackboard.update_state_value('last_agent', self.name)

        self._handle_flow_control(result_dict)

        # Increment action count for this agent (local scope)
        current_actions = self.blackboard.get_state_value(f'{self.name}_action_count', 0)
        new_action_count = current_actions + 1
        self.blackboard.update_state_value(f'{self.name}_action_count', new_action_count)
        logger.info(f"[{self.name}] Action count: {new_action_count}")

        # Best-effort: publish high-signal progress to an orchestrator (if this planner is running under one).
        try:
            self._publish_orchestrator_progress(result_dict)
        except Exception:
            pass


    def _publish_orchestrator_progress(self, result_dict: dict) -> None:
        if not isinstance(result_dict, dict):
            return

        # Gate: only publish if this manager was spawned by an orchestrator.
        orch_name = self.blackboard.get_state_value("orchestrator_name", None)
        job_id = self.blackboard.get_state_value("orchestrator_job_id", None)
        if not isinstance(orch_name, str) or not orch_name.strip():
            return
        if not isinstance(job_id, str) or not job_id.strip():
            return

        progress = result_dict.get("progress_report")
        if not isinstance(progress, list) or not progress:
            return

        # With append_fields + list-extend semantics, planners should emit ONLY newly discovered items each step.
        # Treat the current `progress_report` as a delta and publish it directly.
        major_impact = any(isinstance(x, dict) and bool(x.get("major_impact", False)) for x in progress)

        mgr_name = self.blackboard.get_state_value("manager_name", None)
        mgr_name = mgr_name if isinstance(mgr_name, str) else None

        DI.event_hub.publish(
            Message(
                sender=self.name,
                receiver=str(orch_name),
                event_topic="orchestrator_progress",
                data={
                    "orchestrator": str(orch_name),
                    "job_id": str(job_id),
                    "manager_name": mgr_name,
                    "agent": self.name,
                    "major_impact": bool(major_impact),
                    "progress_items": progress,
                },
            )
        )


