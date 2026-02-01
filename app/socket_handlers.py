# app/socket_handlers.py
from flask import request, current_app
from app.assistant.utils.logging_config import get_logger
import threading

logger = get_logger(__name__)

def register_socket_handlers(socketio):
    @socketio.on('connect')
    def socket_connection_handler():
        from app.assistant.utils import thread_debug
        logger.info(f"Active threads count: {threading.active_count()}")
        #thread_debug.print_thread_info()
        # Don't auto-register here - let clients identify themselves
    
    @socketio.on('register_chat_client')
    def handle_chat_registration(data):
        """Chat tab registers itself as the chat client."""
        try:
            socket_id = request.sid
            if not socket_id:
                logger.error("Missing socket_id during chat registration.")
                return
            DI = current_app.DI
            socket_manager = DI.socket_manager
            socket_manager.update_connection(socket_id, "chat")
            logger.info(f"💬 Chat client registered: {socket_id[:8]}...")
        except Exception as e:
            logger.exception(f"Error registering chat client: {e}")
    
    @socketio.on('register_music_client')
    def handle_music_registration(data):
        """Music tab registers itself as the music client."""
        try:
            socket_id = request.sid
            if not socket_id:
                logger.error("Missing socket_id during music registration.")
                return
            DI = current_app.DI
            socket_manager = DI.socket_manager
            socket_manager.update_connection(socket_id, "music")
            logger.info(f"🎵 Music client registered: {socket_id[:8]}...")
        except Exception as e:
            logger.exception(f"Error registering music client: {e}")
    
    # Music state update handler
    @socketio.on('music_state_update')
    def handle_music_state_update(data):
        """Handle playback state updates from the music player frontend."""
        try:
            from app.assistant.music_manager import get_music_manager
            from app.assistant.dj_manager import get_dj_manager
            
            # Update music manager state
            music_manager = get_music_manager()
            music_manager.update_playback_state(data)
            
            # Notify DJ of track change (for logging/stats)
            #
            # IMPORTANT: We intentionally do NOT let backend auto-queue based on
            # music_state_update. The frontend owns queue timing and requests picks.
            # This avoids double-queueing and excessive Apple API traffic.
            dj_manager = get_dj_manager()
            current_track = data.get("current_track")
            dj_manager.on_track_changed(current_track)
            
        except Exception as e:
            logger.exception(f"Error handling music state update: {e}")
    
    # Music song queued notification
    @socketio.on('music_song_queued')
    def handle_song_queued(data):
        """Handle notification that a song was queued."""
        try:
            from app.assistant.dj_manager import get_dj_manager
            
            dj_manager = get_dj_manager()
            dj_manager.on_frontend_queued(data)
            
        except Exception as e:
            logger.exception(f"Error handling song queued: {e}")
    
    # Frontend requests DJ to pick a song
    @socketio.on('music_pick_request')
    def handle_pick_request(data):
        """Handle request from frontend to pick a new song."""
        try:
            from app.assistant.dj_manager import get_dj_manager
            
            dj_manager = get_dj_manager()

            # Log full context for debugging "thinking but nothing happens".
            try:
                logger.info(
                    "🎵 Pick request event: enabled=%s continuous=%s pick_in_progress=%s data=%s",
                    dj_manager.is_enabled(),
                    dj_manager.is_continuous_mode(),
                    dj_manager.is_pick_in_progress(),
                    data,
                )
            except Exception:
                pass

            # If a pick is already in progress, skip
            if dj_manager.is_pick_in_progress():
                logger.debug("🎵 Pick request ignored - already picking")
                return

            queue_length = data.get('queue_length', 0)
            logger.info(f"🎵 Pick request received (queue: {queue_length})")
            
            # Enqueue pick request (DJ thread handles it).
            #
            # IMPORTANT: Do NOT drop requests just because enable/continuous mode
            # hasn't been applied yet on the DJ thread; the enable event and this
            # request are queued FIFO and will self-resolve.
            dj_manager.request_pick_and_queue(reason="frontend_request")
            
        except Exception as e:
            logger.exception(f"Error handling pick request: {e}")
    
    # Frontend requests backup song (when primary wasn't found)
    @socketio.on('music_backup_request')
    def handle_backup_request(data):
        """Handle request for a backup song when primary wasn't found."""
        try:
            from app.assistant.dj_manager import get_dj_manager
            from app.assistant.dj_manager.query_utils import build_search_query
            
            dj_manager = get_dj_manager()
            failed_query = data.get('failed_query', 'unknown')
            logger.info(f"🎵 Backup request received (failed: {failed_query})")
            
            backup = dj_manager.get_backup_song()
            if backup:
                title = (backup.get("title") or "").strip()
                artist = (backup.get("artist") or "").strip()
                search_query = (backup.get("search_query") or build_search_query(title, artist)).strip()
                logger.info(f"🎵 Sending backup: {search_query}")
                
                # Send backup song to frontend
                DI = current_app.DI
                socket_manager = DI.socket_manager
                socket_id, socket_io = socket_manager.get_music_connection()
                if socket_id and socket_io:
                    socket_io.emit("music_command", {
                        "command": "queue_next",
                        "payload": {"query": search_query, "is_backup": True}
                    }, room=socket_id)
            else:
                logger.warning("🎵 No backups available, frontend will need to request new pick")
            
        except Exception as e:
            logger.exception(f"Error handling backup request: {e}")
