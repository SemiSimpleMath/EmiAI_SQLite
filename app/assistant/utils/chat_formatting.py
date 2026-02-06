from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.time_utils import utc_to_local


def messages_to_chat_excerpts(messages: List[Message]) -> List[Dict[str, Any]]:
    """
    Convert Message objects into stable, LLM-friendly excerpt dicts.

    Output keys intentionally match existing downstream expectations:
    - timestamp_utc: ISO string
    - time_local: human-readable local time
    - sender: sender string
    - content: message content
    """

    def _to_utc(ts: Optional[datetime]) -> Optional[datetime]:
        if not ts:
            return None
        try:
            if getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts.astimezone(timezone.utc)
        except Exception:
            return None

    out: List[Dict[str, Any]] = []
    for m in messages or []:
        try:
            ts_utc = _to_utc(getattr(m, "timestamp", None))
            if ts_utc is None:
                continue
            out.append(
                {
                    "timestamp_utc": ts_utc.isoformat(),
                    "time_local": utc_to_local(ts_utc).strftime("%I:%M %p"),
                    "sender": getattr(m, "sender", "") or "",
                    "content": getattr(m, "content", "") or "",
                }
            )
        except Exception:
            continue
    return out


def messages_to_chat_history_text(messages: List[Message]) -> str:
    """
    Convert Message objects into a compact multi-line chat history string.
    """

    excerpts = messages_to_chat_excerpts(messages)
    lines = [f"[{m['time_local']}] {m['sender']}: {m['content']}" for m in excerpts]
    return "\n".join(lines)

