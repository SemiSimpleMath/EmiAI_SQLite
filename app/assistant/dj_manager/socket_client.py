from __future__ import annotations

from typing import Any, Dict, Optional

from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI

logger = get_logger(__name__)


class MusicSocketClient:
    """
    Thin adapter around your socket manager.
    Keeps the DJ logic free of socket lookup details.
    """

    def send_command(self, command: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        try:
            socket_manager = DI.socket_manager
            if socket_manager is None:
                logger.warning("Socket manager not available")
                return False

            socket_id, socket_io = socket_manager.get_music_connection()
            if not socket_id or not socket_io:
                logger.warning("No music client connected, is the music tab open?")
                return False

            data = {"command": command, "payload": payload or {}}
            socket_io.emit("music_command", data, room=socket_id)
            logger.debug(f"Sent music command: {command}")
            return True
        except Exception as e:
            logger.exception(f"Failed to send music command: {e}")
            return False
