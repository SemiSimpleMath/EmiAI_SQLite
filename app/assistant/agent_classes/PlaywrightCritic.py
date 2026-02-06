from __future__ import annotations

from app.assistant.agent_classes.Agent import Agent
from app.assistant.utils.history_formatting import format_recent_history


class PlaywrightCritic(Agent):
    """
    Playwright critic agent with bounded recent_history injection.

    The critic benefits from context, but unbounded history makes it slow and noisy.
    We keep only the last N message items in `recent_history`.
    """

    HISTORY_LIMIT = 20

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

        return format_recent_history(msgs)

