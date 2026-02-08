from __future__ import annotations

# Deterministic delegator for Playwright MCP browsing.
# Inserts a screenshot capture step before running the critic, and then
# routes back to tool execution or forces planner revision based on critic output.

from typing import Optional
import json
import uuid

from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.pipeline_state import (
    get_pending_tool,
    set_pending_tool,
    clear_pending_tool,
    set_scratch,
    get_scratch,
    set_resume_target,
    get_resume_target,
    ensure_pipeline_state,
)
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class PlaywrightCriticDelegator(Agent):
    """
    Deterministic delegator used by `playwright_manager`.

    Behavior:
    - Respect an already-set `next_agent` (set by control nodes).

    - Optional pre-execution critic gate:
      After `shared::tool_arguments` has produced concrete `tool_arguments`, but before executing the
      tool via `tool_caller`, optionally run:
        delegator -> critic_capture_node (takes screenshot) -> playwright::critic -> delegator
      After critic runs, either resume the pending tool call or force the planner to revise by
      clearing pending tool state and returning to planner.
    """

    PLANNER_AGENT = "playwright::planner"
    CRITIC_AGENT = "playwright::critic"
    TOOL_ARGUMENTS = "shared::tool_arguments"
    CRITIC_CAPTURE_NODE = "critic_capture_node"

    CRITIC_HISTORY_TOOL_RESULT_ID_KEY = "playwright_last_critic_tool_result_id"
    PENDING_TOOL_SNAPSHOT_KEY = "critic_pending_tool_snapshot"
    CRITIC_LAST_PENDING_FP_KEY = "critic_last_pending_fingerprint"
    CRITIC_LAST_ACTION_COUNT_KEY = "critic_last_action_count"

    def action_handler(self, message: Message):
        flow_config = (message.data or {}).get("flow_config")
        if not isinstance(flow_config, dict):
            raise ValueError(f"[{self.name}] Missing flow_config in message.data")

        # Store flow_config for mapping fallback.
        self.flow_config = flow_config

        # Do NOT reset next_agent here; tool_result_handler / control nodes may have set it.
        if getattr(message, "content", None):
            try:
                self.blackboard.add_msg(message)
            except Exception:
                pass

        last_agent = self.blackboard.get_state_value("last_agent")
        next_agent = self.blackboard.get_state_value("next_agent")

        # ------------------------------------------------------------
        # Case 1: We just ran the critic -> decide resume vs revise
        # ------------------------------------------------------------
        if last_agent == self.CRITIC_AGENT:
            # Persist the critic output into the normal message history stream so the planner
            # can see it chronologically (like any other agent result), and therefore infer when it has
            # already started acting on it.
            #
            # This is intentionally "hacky but explicit": the critic is triggered by the
            # delegator, not the tool_caller, so we synthesize a normal `agent_result` Message.
            try:
                self._append_critic_history_message()
            except Exception:
                # Never break routing due to logging/histry injection issues.
                pass

            must_revise = bool(self.blackboard.get_state_value("critic_must_revise_plan", False))
            resume = get_resume_target(self.blackboard)

            # If there is no explicit resume marker, infer it from pending tool state.
            if not isinstance(resume, str) or not resume:
                pending = get_pending_tool(self.blackboard) or {}
                pending_tool = pending.get("name")
                pending_args = pending.get("arguments")
                if isinstance(pending_tool, str) and pending_tool.strip() and isinstance(pending_args, dict):
                    resume = "tool_caller"
                else:
                    resume = self.PLANNER_AGENT

            # Clear resume marker either way.
            try:
                set_resume_target(self.blackboard, None)
            except Exception:
                pass

            if must_revise:
                # Cancel the pending tool call and send control back to planner.
                try:
                    clear_pending_tool(self.blackboard)
                except Exception:
                    pass
                try:
                    set_scratch(self.blackboard, self.PENDING_TOOL_SNAPSHOT_KEY, None)
                except Exception:
                    pass
                self.blackboard.update_state_value("next_agent", self.PLANNER_AGENT)
            else:
                # Resume the pending flow.
                # If pending tool state was lost mid-critic, restore it from snapshot.
                snapshot = get_scratch(self.blackboard, self.PENDING_TOOL_SNAPSHOT_KEY)
                if isinstance(snapshot, dict):
                    pending = get_pending_tool(self.blackboard) or {}
                    if not pending:
                        set_pending_tool(
                            self.blackboard,
                            name=snapshot.get("name"),
                            calling_agent=snapshot.get("calling_agent"),
                            action_input=snapshot.get("action_input"),
                            arguments=snapshot.get("arguments") if isinstance(snapshot.get("arguments"), dict) else {},
                            kind=snapshot.get("kind"),
                        )

                pending = get_pending_tool(self.blackboard) or {}
                pending_tool = pending.get("name")
                pending_args = pending.get("arguments")
                if isinstance(pending_tool, str) and pending_tool.strip() and isinstance(pending_args, dict):
                    self.blackboard.update_state_value("next_agent", resume)
                else:
                    self.blackboard.update_state_value("next_agent", self.PLANNER_AGENT)

            self.blackboard.update_state_value("last_agent", self.name)
            return

        # ------------------------------------------------------------
        # Case 2: If next_agent already set (e.g., tool_result_handler), respect it
        # ------------------------------------------------------------
        if next_agent is not None:
            self.blackboard.update_state_value("last_agent", self.name)
            return

        # ------------------------------------------------------------
        # Case 3: Fallback: strict mapping from flow_config.state_map
        # ------------------------------------------------------------
        picked = self._pick_next_from_state_map(last_agent)

        # Insert critic BETWEEN ToolArguments and ToolCaller so the critic sees
        # both `selected_tool` and the generated `tool_arguments`.
        #
        # This avoids the "untargeted click" confusion caused by running critic
        # before ToolArguments has produced arguments.
        if (
            picked == "tool_caller"
            and isinstance(last_agent, str)
            and last_agent == self.TOOL_ARGUMENTS
            and self._should_run_critic()
        ):
            # Snapshot pending tool state so we can reliably resume after critic.
            try:
                pending = get_pending_tool(self.blackboard) or {}
                set_scratch(self.blackboard, self.PENDING_TOOL_SNAPSHOT_KEY, pending)
            except Exception:
                pass
            try:
                set_resume_target(self.blackboard, picked)
            except Exception:
                pass
            try:
                self.blackboard.update_state_value("playwright_critic_trigger_reason", "pre_tool_exec_gate")
            except Exception:
                pass
            try:
                fingerprint = self._pending_tool_fingerprint()
                if fingerprint:
                    set_scratch(self.blackboard, self.CRITIC_LAST_PENDING_FP_KEY, fingerprint)
                steps = int(self.blackboard.get_state_value(f"{self.PLANNER_AGENT}_action_count", 0) or 0)
                set_scratch(self.blackboard, self.CRITIC_LAST_ACTION_COUNT_KEY, steps)
            except Exception:
                pass
            self.blackboard.update_state_value("next_agent", self.CRITIC_CAPTURE_NODE)
            self.blackboard.update_state_value("last_agent", self.name)
            return

        if picked:
            self.blackboard.update_state_value("next_agent", picked)
        self.blackboard.update_state_value("last_agent", self.name)

    def _pick_next_from_state_map(self, last_agent: Optional[str]) -> Optional[str]:
        if last_agent is None:
            last_agent = "NO_PREVIOUS_AGENT"
        state_map = (self.flow_config or {}).get("state_map", {}) if hasattr(self, "flow_config") else {}
        if not isinstance(state_map, dict):
            return None
        nxt = state_map.get(last_agent)
        return nxt if isinstance(nxt, str) and nxt else None

    def _should_run_critic(self) -> bool:
        """
        Conservative default cadence: run critic periodically, and on error-y tool results.

        Critic is useful but expensive; don't run it every loop.
        """
        try:
            steps = int(self.blackboard.get_state_value(f"{self.PLANNER_AGENT}_action_count", 0) or 0)
        except Exception:
            steps = 0

        if steps <= 0:
            return False

        # Dedupe: avoid re-running critic on the exact same pending tool in back-to-back loops.
        try:
            fingerprint = self._pending_tool_fingerprint()
            last_fp = get_scratch(self.blackboard, self.CRITIC_LAST_PENDING_FP_KEY)
            last_steps = get_scratch(self.blackboard, self.CRITIC_LAST_ACTION_COUNT_KEY)
            if (
                fingerprint
                and last_fp == fingerprint
                and isinstance(last_steps, int)
                and (steps - last_steps) < 2
            ):
                return False
        except Exception:
            pass

        # If last tool result was an error, run critic on the next pre-exec gate.
        try:
            ps = ensure_pipeline_state(self.blackboard)
            meta = ps.get("last_tool_result_meta") if isinstance(ps, dict) else None
            if isinstance(meta, dict) and meta.get("result_type") == "error":
                return True
        except Exception:
            pass

        # Otherwise, cadence.
        return (steps % 5) == 0

    def _pending_tool_fingerprint(self) -> Optional[str]:
        try:
            pending = get_pending_tool(self.blackboard) or {}
            if not isinstance(pending, dict) or not pending:
                return None
            return json.dumps(pending, sort_keys=True, default=str)
        except Exception:
            return None

    def _append_critic_history_message(self) -> None:
        """
        Append a synthetic `agent_result` message into history for the critic output.

        Why: planner prompt history is built from the blackboard message log and only includes
        a fixed set of message types. The critic is an agent, but it is invoked by the delegator,
        so we explicitly emit an `agent_result` message here to make it visible chronologically.
        """
        actionable = self.blackboard.get_state_value("critic_actionable_change", None)
        diagnosis = self.blackboard.get_state_value("critic_diagnosis", None)
        conf = self.blackboard.get_state_value("critic_confidence", None)
        must_revise = bool(self.blackboard.get_state_value("critic_must_revise_plan", False))

        # If there is nothing meaningful, skip.
        if not any(x for x in (actionable, diagnosis, conf, must_revise)):
            return

        # Create a stable id marker so this appears like other tool results.
        tool_result_id = f"critic_{uuid.uuid4().hex}"
        try:
            self.blackboard.update_state_value(self.CRITIC_HISTORY_TOOL_RESULT_ID_KEY, tool_result_id)
        except Exception:
            pass

        lines: list[str] = []
        lines.append("CRITIC RESULT:")
        if isinstance(diagnosis, str) and diagnosis.strip():
            lines.append(f"- critic_diagnosis: {diagnosis.strip()}")
        if isinstance(actionable, str) and actionable.strip():
            lines.append(f"- critic_actionable_change: {actionable.strip()}")
        lines.append(f"- critic_must_revise_plan: {must_revise}")
        if conf is not None:
            lines.append(f"- critic_confidence: {conf}")

        msg = Message(
            data_type="agent_result",
            sender=self.CRITIC_AGENT,
            receiver=self.PLANNER_AGENT,
            content="\n".join(lines).strip(),
            metadata={
                "tool_result_id": tool_result_id,
                "critic": {
                    "critic_diagnosis": diagnosis,
                    "critic_actionable_change": actionable,
                    "critic_must_revise_plan": must_revise,
                    "critic_confidence": conf,
                },
            },
        )
        self.blackboard.add_msg(msg)

