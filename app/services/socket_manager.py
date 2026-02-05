# app/services/socket_manager.py
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class SocketManager:
    def __init__(self):
        self.socket_id = None  # Default/chat connection
        self._connections = {}  # Named connections: {"music": socket_id, "chat": socket_id}

    def update_connection(self, socket_id, connection_type: str = "chat"):
        """
        Update connection for a specific type.
        
        Args:
            socket_id: The socket ID
            connection_type: "chat" (default) or "music"
        """
        self._connections[connection_type] = socket_id
        
        # Keep backward compatibility - default socket_id is chat
        if connection_type == "chat":
            self.socket_id = socket_id
        
        logger.debug(f"🔌 Socket connection updated: {connection_type} = {socket_id[:8]}...")

    def get_connection(self, connection_type: str = None):
        """
        Get connection, optionally by type.
        
        Args:
            connection_type: "chat", "music", or None for default
        """
        if connection_type and connection_type in self._connections:
            return self._connections[connection_type], DI.socket_io
        return self.socket_id, DI.socket_io
    
    def get_music_connection(self):
        """Get the music tab's socket connection."""
        return self.get_connection("music")    def get_progress_connection(self):
        """Get the progress tab's socket connection."""
        return self.get_connection("progress")
    
    def has_music_connection(self) -> bool:
        """Check if music tab is connected."""
        return "music" in self._connections

    def has_progress_connection(self) -> bool:
        """Check if progress tab is connected."""
        return "progress" in self._connections
