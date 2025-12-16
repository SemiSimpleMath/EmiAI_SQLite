import queue
import threading
from concurrent.futures import ThreadPoolExecutor

from app.assistant.utils.pydantic_classes import Message, UserMessage
from app.assistant.ServiceLocator.service_locator import DI
from app.services import text_to_speech
from queue import Empty

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class EmiEventRelay:
    """Handles WebSocket events, TTS processing, and UI updates for the Emi system."""

    def __init__(self):
        # Event-driven setup
        self.blackboard = DI.global_blackboard
        self.waiting_for_user_response = False
        self.message_queue = queue.Queue()
        self.tts_executor = ThreadPoolExecutor(max_workers=2)  # Reduced from 5 to 2 workers
        self.socket_lock = threading.Lock()

        # Start background message processor
        threading.Thread(target=self.process_queue, daemon=True).start()

        # Register event handlers
        DI.event_hub.register_event('socket_emit', self.socket_emit_handler)
        DI.event_hub.register_event('socket_emit_all_done', self.socket_emit_all_done_handler)
        DI.event_hub.register_event('repo_update', self.notify_ui_of_repo_update)
        DI.event_hub.register_event('proactive_suggestion', self.proactive_suggestion_handler)


    def socket_emit_handler(self, message: UserMessage):
        """Queue messages for WebSocket emission, processing TTS if needed."""
        print("\nAt socket_emit_handler")  # Debugging

        payload = message.user_message_data

        # Handle TTS processing
        if payload.tts:
            if payload.tts_text:
                logger.info("TTS flag detected. Generating audio.")
                self.tts_executor.submit(self._process_tts, payload.tts_text)
            else:
                logger.warning("TTS flag set but 'tts_text' is missing.")
                self._emit_error('audio_file_error', "Missing 'tts_text' in payload.")

        # Queue the message for WebSocket emission
        self.message_queue.put((message, payload))

    def notify_ui_of_repo_update(self, msg: Message):
        """Notifies the UI about repository updates via WebSocket."""
        print("At notify_ui_of_repo_update -- DEBUG")
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()

        if not socket_io or not socket_id:
            logger.warning("SocketIO or Socket ID is missing. Cannot notify UI.")
            return

        data = msg.data
        with self.socket_lock:
            socket_io.emit("repo_update_notification", data, room=socket_id)
            logger.info(f"Sent UI update notification: {data}")

    def socket_emit_all_done_handler(self, event_data):
        """Notify the client that all messages have been sent."""
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()
        print(f"WebSocketHandler: Notifying socket_id {socket_id} that streaming is complete")
        with self.socket_lock:
            socket_io.emit('all_done', room=socket_id)
    
    def proactive_suggestion_handler(self, message: Message):
        """Emit proactive suggestion to frontend via WebSocket."""
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()
        
        if not socket_io or not socket_id:
            logger.warning("❌ Cannot emit proactive suggestion — socket not available.")
            return
        
        # The message.data should contain the ticket dict
        suggestion_data = message.data if hasattr(message, 'data') else {}
        
        with self.socket_lock:
            socket_io.emit('proactive_suggestion', suggestion_data, room=socket_id)
            logger.info(f"📋 Emitted proactive_suggestion to socket_id {socket_id}")

    def process_queue(self):
        """Continuously process messages from the queue and emit via WebSocket."""
        while True:
            try:
                message, payload = self.message_queue.get(timeout=1)
                self._emit_message(message, payload)
            except Empty:
                continue

    def _emit_message(self, message, payload):
        """Handles actual WebSocket emission of messages."""
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()

        if not socket_io or not socket_id:
            logger.warning("❌ Cannot emit — socket_io or socket_id is missing.")
            return

        data = {
            "chat": payload.chat,
            "feed": payload.feed,
            "widget_data": payload.widget_data,
            "sound": payload.sound
        }


        with self.socket_lock:
            socket_io.emit('user_message_data', data, room=socket_id)
            logger.info(f"Emitted response to socket_id {socket_id}")

        self.socket_emit_all_done_handler(message)

    def _process_tts(self, text):
        """Handles text-to-speech processing."""
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()

        if not socket_io or not socket_id:
            logger.warning("❌ Cannot emit — socket_io or socket_id is missing.")
            return

        try:
            text_to_speech.process_text(text, socket_id, socket_io)
        except Exception as e:
            logger.error(f"Failed to generate TTS audio: {e}")
            self._emit_error('audio_file_error', "Failed to generate TTS audio.", str(e))

    def _emit_error(self, event, message, details=""):
        """Emit error messages to WebSocket."""
        socket_manager = DI.socket_manager
        socket_id, socket_io = socket_manager.get_connection()

        if not socket_io or not socket_id:
            logger.warning("❌ Cannot emit — socket_io or socket_id is missing.")
            return
        error_data = {"error": message, "details": details}
        with self.socket_lock:
            socket_io.emit(event, error_data, room=socket_id)
