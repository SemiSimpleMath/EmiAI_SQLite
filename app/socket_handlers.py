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

        try:
            socket_id = request.sid
            if not socket_id:
                logger.error("Missing socket_id during connection.")
                return

            DI = current_app.DI
            socket_manager = DI.socket_manager
            socket_manager.update_connection(socket_id)

        except Exception as e:
            logger.exception(f"Error during socket connection handling: {e}")
