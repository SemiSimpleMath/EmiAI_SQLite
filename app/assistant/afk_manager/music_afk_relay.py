from __future__ import annotations

from typing import Any, Dict

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class MusicAfkRelay:
    """
    Relay AFK transitions to the music frontend.

    This keeps AFK pause/resume policy in the frontend:
    - Backend always emits AFK state changes to the music client (if connected)
    - Frontend decides whether to pause/resume based on its own toggle/state
    """

    EVENT_TOPIC = "afk_state_changed"
    SOCKET_EVENT = "music_afk_state"

    def __init__(self) -> None:
        DI.event_hub.register_event(self.EVENT_TOPIC, self.afk_state_changed_handler)
        logger.info(f"✅ MusicAfkRelay subscribed to event: {self.EVENT_TOPIC}")

    def afk_state_changed_handler(self, msg: Any) -> None:
        """
        msg.data expected shape:
          { is_afk: bool, just_went_afk: bool, just_returned: bool, snapshot: {...} }
        """
        try:
            data = getattr(msg, "data", None)
            if not isinstance(data, dict):
                return

            payload: Dict[str, Any] = {
                "is_afk": bool(data.get("is_afk", False)),
                "just_went_afk": bool(data.get("just_went_afk", False)),
                "just_returned": bool(data.get("just_returned", False)),
                "snapshot": data.get("snapshot", {}) if isinstance(data.get("snapshot"), dict) else {},
            }

            socket_manager = DI.socket_manager
            if socket_manager is None:
                return

            socket_id, socket_io = socket_manager.get_music_connection()
            if not socket_id or not socket_io:
                # Music tab not open/registered; nothing to do.
                return

            socket_io.emit(self.SOCKET_EVENT, payload, room=socket_id)
        except Exception as e:
            logger.warning(f"MusicAfkRelay failed to emit {self.SOCKET_EVENT}: {e}", exc_info=True)

