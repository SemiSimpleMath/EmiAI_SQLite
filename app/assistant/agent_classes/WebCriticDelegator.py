from __future__ import annotations

# Note: This delegator is intentionally deterministic (no LLM).
# It is designed for the Playwright interactive manager to optionally insert a critic step
# before executing a pending tool call (shared::tool_arguments).

from typing import Optional

from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class WebCriticDelegator(Agent):
    """
    Delegator that can gate execution with a synchronous critic.

    Key behavior:
    - Normally, if next_agent is already set by previous nodes (planner/tool_result_handler),
      it will respect it.
    - If a pending tool call is about to be executed (next_agent == "shared::tool_arguments"),
      it may insert "shared::web_critic" first, based on manager_loop_count cadence.
    - After critic runs, this delegator decides whether to resume the pending tool call
      or force the planner to revise.

    This avoids adding parallelism and avoids modifying core control nodes.
    """

    CRITIC_AGENT = "shared::web_critic"
    TOOL_ARGUMENTS = "shared::tool_arguments"

    def action_handler(self, message: Message):
        flow_config = (message.data or {}).get("flow_config")
        if not isinstance(flow_config, dict):
            raise ValueError(f"[{self.name}] Missing flow_config in message.data")

        # Store flow_config for mapping fallback.
        self.flow_config = flow_config

        # Do NOT reset next_agent here; tool_result_handler may have set it.
        if message.content:
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
            must_revise = bool(self.blackboard.get_state_value("critic_must_revise_plan", False))
            resume = self.blackboard.get_state_value("web_critic_resume_next_agent")
            if not isinstance(resume, str) or not resume:
                resume = "mcp_playwright_interactive_test::planner"

            # Clear the resume marker either way.
            try:
                self.blackboard.update_state_value("web_critic_resume_next_agent", None)
            except Exception:
                pass

            if must_revise:
                # Cancel the pending tool call and send control back to planner.
                for k in ("selected_tool", "tool_arguments", "original_calling_agent"):
                    try:
                        self.blackboard.update_state_value(k, None)
                    except Exception:
                        pass

                self.blackboard.update_state_value("next_agent", "mcp_playwright_interactive_test::planner")
            else:
                # Resume the pending tool flow (typically shared::tool_arguments).
                self.blackboard.update_state_value("next_agent", resume)

            self.blackboard.update_state_value("last_agent", self.name)
            return

        # ------------------------------------------------------------
        # Case 2: Insert critic before executing pending tool call
        # ------------------------------------------------------------
        if isinstance(next_agent, str) and next_agent == self.TOOL_ARGUMENTS:
            if self._should_run_critic():
                # Capture latest screenshot filename (optional) for multimodal critique.
                img = self._latest_image_filename()
                try:
                    self.blackboard.update_state_value("web_critic_image", img)
                except Exception:
                    pass

                try:
                    self.blackboard.update_state_value("web_critic_trigger_reason", "cadence_or_loop_guard")
                except Exception:
                    pass

                # Remember what we were about to do, so we can resume if critic approves.
                try:
                    self.blackboard.update_state_value("web_critic_resume_next_agent", next_agent)
                except Exception:
                    pass

                self.blackboard.update_state_value("next_agent", self.CRITIC_AGENT)
                self.blackboard.update_state_value("last_agent", self.name)
                return

            # No critic: proceed with the pending tool call.
            self.blackboard.update_state_value("last_agent", self.name)
            return

        # ------------------------------------------------------------
        # Case 3: If next_agent already set (e.g., tool_result_handler), respect it
        # ------------------------------------------------------------
        if next_agent is not None:
            self.blackboard.update_state_value("last_agent", self.name)
            return

        # ------------------------------------------------------------
        # Case 4: Fallback: strict mapping from flow_config.state_map
        # ------------------------------------------------------------
        picked = self._pick_next_from_state_map(last_agent)
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
        Start conservative: run critic every 5 manager loops (after loop 0).
        This can be expanded later (e.g., loop detection, error-based triggers).
        """
        try:
            loops = int(self.blackboard.get_state_value("manager_loop_count", 0) or 0)
        except Exception:
            loops = 0
        if loops <= 0:
            return False
        return (loops % 5) == 0

    def _latest_image_filename(self) -> Optional[str]:
        """
        Find the most recent image attachment filename in the current scope messages.
        Returns a filename (not absolute path) so the system can resolve it to uploads/temp/.
        """
        try:
            scope_id = self.blackboard.get_current_scope_id()
            msgs = self.blackboard.get_messages_for_scope(scope_id)
        except Exception:
            msgs = []

        for m in reversed(msgs or []):
            meta = getattr(m, "metadata", None)
            if not isinstance(meta, dict):
                continue
            atts = meta.get("attachments")
            if not isinstance(atts, list):
                continue
            for att in atts:
                if not isinstance(att, dict):
                    continue
                if att.get("type") != "image":
                    continue
                fname = att.get("original_filename") or ""
                if isinstance(fname, str) and fname.strip():
                    return fname.strip()
        return None

