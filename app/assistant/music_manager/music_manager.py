"""
Music Manager
=============
Handles Apple MusicKit integration including JWT token generation and playback state.
"""

import jwt
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

# Apple MusicKit credentials
MUSICKIT_KEY_ID = "XAX3GKSV7M"
MUSICKIT_TEAM_ID = "65WK889FT4"
MUSICKIT_P8_PATH = Path("E:/EmiAi_sqlite/musickit/AuthKey_XAX3GKSV7M.p8")

# Token validity
# Apple allows developer tokens up to 6 months. Using a long TTL prevents
# "Initialized with an expired token" during long-running browser sessions.
# 180 days = 15552000 seconds.
TOKEN_EXPIRY_SECONDS = 60 * 60 * 24 * 180


class MusicManager:
    """
    Manages Apple MusicKit integration.
    
    Responsibilities:
    - Generate JWT developer tokens for MusicKit
    - Track playback state
    - Handle WebSocket commands from agents/UI
    """
    
    def __init__(self):
        self._private_key: Optional[str] = None
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0
        
        # Playback state (updated by frontend via WebSocket)
        self.playback_state: Dict[str, Any] = {
            "is_playing": False,
            "current_track": None,
            "queue": [],
            "progress_seconds": 0,
            "duration_seconds": 0,
            "volume": 1.0,
            "last_update_utc": None,
        }
        
        self._load_private_key()

        # Logging throttles (reduce noisy state spam)
        self._last_logged_playing: Optional[bool] = None
        self._last_logged_track: Optional[str] = None  # "title|||artist"
    
    def _load_private_key(self) -> None:
        """Load the .p8 private key from disk."""
        try:
            if not MUSICKIT_P8_PATH.exists():
                logger.error(f"MusicKit private key not found at {MUSICKIT_P8_PATH}")
                return
            
            self._private_key = MUSICKIT_P8_PATH.read_text()
            logger.info(f"✅ Loaded MusicKit private key from {MUSICKIT_P8_PATH}")
        except Exception as e:
            logger.exception(f"Failed to load MusicKit private key: {e}")
    
    def generate_developer_token(self, origin: Optional[str] = None) -> Optional[str]:
        """
        Generate a JWT developer token for Apple MusicKit.
        
        Args:
            origin: Optional origin claim for web tokens (e.g., "http://localhost:5000")
        
        Returns:
            JWT token string or None if generation fails
        """
        if not self._private_key:
            logger.error("Cannot generate token: private key not loaded")
            return None
        
        # Check if we have a valid cached token (with 5 min buffer)
        if self._cached_token and time.time() < (self._token_expiry - 300):
            logger.debug("Using cached MusicKit token")
            return self._cached_token
        
        try:
            now = int(time.time())
            exp = now + TOKEN_EXPIRY_SECONDS
            
            # JWT claims per Apple MusicKit documentation
            claims = {
                "iss": MUSICKIT_TEAM_ID,
                "iat": now,
                "exp": exp,
            }
            
            # Add origin claim for web tokens if provided
            if origin:
                claims["origin"] = origin
            
            # JWT header
            headers = {
                "alg": "ES256",
                "kid": MUSICKIT_KEY_ID,
            }
            
            token = jwt.encode(
                claims,
                self._private_key,
                algorithm="ES256",
                headers=headers,
            )
            
            self._cached_token = token
            self._token_expiry = exp
            
            logger.info(f"🎵 Generated new MusicKit developer token (expires in {TOKEN_EXPIRY_SECONDS}s)")
            return token
            
        except Exception as e:
            logger.exception(f"Failed to generate MusicKit token: {e}")
            return None
    
    def update_playback_state(self, state: Dict[str, Any]) -> None:
        """
        Update the playback state from frontend.
        
        Args:
            state: Dictionary with playback state fields
        """
        self.playback_state.update(state)
        self.playback_state["last_update_utc"] = datetime.now(timezone.utc).isoformat()

        # Log only meaningful changes (track change / play-pause), not every heartbeat.
        try:
            playing = bool(state.get("is_playing")) if "is_playing" in state else None
            ct = state.get("current_track") if isinstance(state.get("current_track"), dict) else None
            title = (ct.get("title") or "").strip() if ct else ""
            artist = (ct.get("artist") or "").strip() if ct else ""
            track_key = f"{title}|||{artist}" if (title or artist) else ""

            if playing is not None and playing != self._last_logged_playing:
                logger.info(f"🎵 Playback {'playing' if playing else 'paused'}")
                self._last_logged_playing = playing

            if track_key and track_key != self._last_logged_track:
                logger.info(f"🎵 Now playing: {title} — {artist}")
                self._last_logged_track = track_key
        except Exception:
            # Never let logging logic break state updates
            pass
    
    def get_playback_state(self) -> Dict[str, Any]:
        """Get current playback state."""
        return self.playback_state.copy()
    
    def is_configured(self) -> bool:
        """Check if MusicKit is properly configured."""
        return self._private_key is not None


# Singleton instance
_music_manager: Optional[MusicManager] = None


def get_music_manager() -> MusicManager:
    """Get or create the MusicManager singleton."""
    global _music_manager
    if _music_manager is None:
        _music_manager = MusicManager()
    return _music_manager
