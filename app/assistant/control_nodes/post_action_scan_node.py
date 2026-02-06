from __future__ import annotations

import time

from app.assistant.control_nodes.control_node import ControlNode
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class PostActionScanNode(ControlNode):
    """
    Deterministic "action + scan" accelerator for Playwright browsing.

    Goal:
    - After the planner executes an action tool (click/type/navigate/etc), immediately take ONE
      `browser_snapshot` before giving control back to the planner.
    - This avoids a wasted LLM cycle where the planner spends time deciding to scan.

    Contract:
    - ToolResultHandler schedules this node by setting:
        - next_agent = "post_action_scan_node"
        - playwright_auto_scan_in_progress = True
      and leaving original_calling_agent intact.
    - This node sets up the MCP snapshot tool call and routes to tool_caller.
    """

    SNAPSHOT_TOOL = "mcp::npm/playwright-mcp::browser_snapshot"

    def action_handler(self, message):  # noqa: ARG002
        # Always clear next_agent at start of control nodes
        try:
            self.blackboard.update_state_value("next_agent", None)
        except Exception:
            pass

        # If the tool isn't available, fail soft: just return to the calling agent.
        tool_cfg = None
        try:
            tool_cfg = self.tool_registry.get_tool(self.SNAPSHOT_TOOL)
        except Exception:
            tool_cfg = None

        calling_agent = None
        try:
            calling_agent = self.blackboard.get_state_value("original_calling_agent")
        except Exception:
            calling_agent = None

        if not tool_cfg:
            logger.warning("[%s] Snapshot tool missing; skipping auto-scan.", self.name)
            try:
                self.blackboard.update_state_value("playwright_auto_scan_in_progress", None)
                self.blackboard.update_state_value("next_agent", calling_agent)
                self.blackboard.update_state_value("last_agent", self.name)
            except Exception:
                pass
            return

        # Small deterministic settle delay before snapshot.
        # DoorDash (and many JS-heavy sites) update UI asynchronously after actions;
        # taking a snapshot immediately can capture the "old" state.
        try:
            trigger_tool = self.blackboard.get_state_value("playwright_auto_scan_trigger_tool")
        except Exception:
            trigger_tool = None

        # Default delays (seconds). Keep short to preserve speed.
        delay_s = 0.25
        if isinstance(trigger_tool, str) and trigger_tool.endswith("::browser_type"):
            delay_s = 0.8
        elif isinstance(trigger_tool, str) and trigger_tool.endswith("::browser_press_key"):
            delay_s = 0.6
        elif isinstance(trigger_tool, str) and trigger_tool.endswith("::browser_click"):
            delay_s = 0.4

        try:
            if delay_s and delay_s > 0:
                time.sleep(float(delay_s))
        except Exception:
            pass

        # Set up the tool call deterministically (no ToolArguments LLM step).
        try:
            prev = self.blackboard.get_state_value("selected_tool")
            self.blackboard.update_state_value("playwright_auto_scan_prev_tool", prev)
        except Exception:
            pass

        try:
            self.blackboard.update_state_value("selected_tool", self.SNAPSHOT_TOOL)
            # `browser_snapshot` has optional {filename}; default is fine.
            self.blackboard.update_state_value("tool_arguments", {})
            self.blackboard.update_state_value("next_agent", "tool_caller")
            self.blackboard.update_state_value("last_agent", self.name)
        except Exception as e:
            logger.warning("[%s] Failed to schedule snapshot tool call: %s", self.name, e)
            try:
                self.blackboard.update_state_value("next_agent", calling_agent)
                self.blackboard.update_state_value("last_agent", self.name)
            except Exception:
                pass

