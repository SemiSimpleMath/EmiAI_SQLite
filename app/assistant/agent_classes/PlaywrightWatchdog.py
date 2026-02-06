from __future__ import annotations

from app.assistant.agent_classes.Agent import Agent


class PlaywrightWatchdog(Agent):
    """
    Lightweight monitor agent for Playwright browsing runs.

    Key behavior:
    - Limits `recent_history` injection to the last few items to keep prompts fast.
    - Emits a small structured result that can set `next_agent` to `critic_capture_node`
      when the planner appears stuck (repeats, errors, snapshot/read loops).
    """

    # Give watchdog enough context to see 2-3 "tool → auto snapshot" pairs.
    # Too small makes it falsely interpret the auto-snapshot as repetition/no-progress.
    HISTORY_LIMIT = 12

    def build_recent_history(self, agent_messages):
        try:
            msgs = list(agent_messages or [])
        except Exception:
            msgs = agent_messages

        try:
            if isinstance(msgs, list) and len(msgs) > self.HISTORY_LIMIT:
                msgs = msgs[-self.HISTORY_LIMIT :]
        except Exception:
            pass

        return super().build_recent_history(msgs)

