import queue
import random
import sys
import threading
import time

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

class EventHandlerHub:
    def __init__(self):
        self.queue = queue.Queue()  # Thread-safe queue
        self.running = True

        # Event routing table (maps event keys to handler functions)
        self.event_registry = {}

        # Track agent busy status: agent_name -> bool (True if busy)
        self.agent_status = {}

        # Store pending messages per agent: agent_name -> list of messages
        self.pending_messages = {}

        # Track when an agent's message was first requeued: agent_name -> timestamp
        self.requeued_timestamps = {}

        # Maximum wait time (seconds) before force-releasing an agent
        self.max_wait_time = 200

        # Start a worker thread for processing messages
        self.worker_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.worker_thread.start()
        logger.info("✅ EventHandlerHub initialized and worker thread started.")

    def register_event(self, event_key, handler):
        """Registers an event with a unique key and its handler. Raises on duplicate."""
        if event_key in self.event_registry:
            existing_handler = self.event_registry[event_key]
            if existing_handler == handler:
                logger.critical(
                    f"❌ Duplicate registration attempt for event '{event_key}' "
                    f"with the same handler: {handler} (id: {id(handler)})"
                )
                sys.exit(f"🛑 Fatal: duplicate handler registration for '{event_key}'")
            else:
                logger.critical(
                    f"❌ Conflicting handlers for event '{event_key}'!\n"
                    f"- Existing: {existing_handler} (id: {id(existing_handler)})\n"
                    f"- New: {handler} (id: {id(handler)})"
                )
                sys.exit(f"🛑 Fatal: handler conflict on '{event_key}'")

        self.event_registry[event_key] = handler
        logger.info(f"✅ Registered event: {event_key} with handler {handler}")

    def set_agent_status(self, agent_name, is_busy):
        """Marks an agent as busy or available. When an agent becomes available, dispatch any pending messages."""
        previous_status = self.agent_status.get(agent_name, None)
        self.agent_status[agent_name] = is_busy
        status = "BUSY" if is_busy else "AVAILABLE"

        logger.debug(f"🔄 Agent '{agent_name}' changed from {previous_status} to {status}")

        if not is_busy and agent_name in self.pending_messages:
            while self.pending_messages[agent_name]:
                pending_message = self.pending_messages[agent_name].pop(0)
                logger.debug(f"🚀 Dispatching pending message for agent '{agent_name}'")
                self.dispatch_message(pending_message)

            # Clear the requeue timestamp if present
            if agent_name in self.requeued_timestamps:
                del self.requeued_timestamps[agent_name]

    def is_agent_busy(self, agent_name):
        """Returns whether an agent is currently busy."""
        busy_status = self.agent_status.get(agent_name, False)
        logger.debug(f"🔍 Agent '{agent_name}' busy status: {busy_status}")
        return busy_status

    def publish(self, message: Message):
        """Handles incoming events, warning if no subscribers exist but still allowing late registrations."""
        logger.debug(f"🔵 Received event: {message.event_topic} for agent '{message.receiver}' with content: {message.content}")

        if message.event_topic not in self.event_registry:
            logger.warning(f"⚠️ Event '{message.event_topic}' was published but has NO registered subscribers yet.")

        logger.debug(f"📥 Putting message for '{message.receiver}' into the queue")
        # print("JUKKA DEBUG In queue:")
        # for item in list(self.queue.queue):  # copy to avoid race conditions
        #     print("  •", item)

        self.queue.put(message)

    def process_queue(self):
        logger.info("🔄 EventHandlerHub worker thread running...")

        empty_queue_wait = 0.01  # Reduced from 0.1 to 0.01 seconds
        max_empty_queue_wait = 0.5  # Reduced from 2.0 to 0.5 seconds

        while self.running:
            try:
                queue_size = self.queue.qsize()
                #logger.debug(f"🟢 Queue size: {queue_size}")
                # print(f"print statement says Queue size: {queue_size}")

                if queue_size == 0:
                    #logger.debug(f"⏳ Queue is empty. Sleeping for {empty_queue_wait} seconds...")
                    #print(f"print statement says: Queue is empty. Sleeping for {empty_queue_wait} seconds...")
                    time.sleep(empty_queue_wait)
                    empty_queue_wait = min(max_empty_queue_wait, empty_queue_wait * 1.2)  # Reduced multiplier from 1.5 to 1.2
                    continue
                else:
                    empty_queue_wait = 0.01  # Reset wait time when messages arrive

                messages_to_requeue = []
                messages = []

                while not self.queue.empty():
                    msg = self.queue.get()
                    logger.debug(f"📤 Processing message from queue: {msg.event_topic} for {msg.receiver}")
                    messages.append(msg)

                logger.debug(f"📌 Processing {len(messages)} messages from queue")
                random.shuffle(messages)

                for message in messages:
                    agent_name = message.receiver

                    if agent_name is not None and agent_name not in DI.agent_registry.list_agents():
                        logger.error(f"🚨 Message has an invalid agent_name: {agent_name}. Message: {message} ")
                        continue

                    logger.debug(f"📬 Processing message for agent '{agent_name}'")

                    if agent_name is not None and self.agent_status.get(agent_name, False):
                        logger.warning(f"⚠️ Agent '{agent_name}' is busy. Requeuing message.")
                        messages_to_requeue.append(message)
                    else:
                        handler = self.event_registry.get(message.event_topic, self.default_handler)
                        logger.debug(f"📨 Dispatching message to handler {handler}")

                        try:
                            threading.Thread(target=handler, args=(message,), daemon=True).start()
                        except Exception as e:
                            logger.critical(f"🔥 Handler for event '{message.event_topic}' crashed for agent '{agent_name}': {e}", exc_info=True)
                            sys.exit(f"💥 Fatal error in handler '{handler.__name__}' for agent '{agent_name}' — exiting for debug.")

                for msg in messages_to_requeue:
                    logger.debug(f"🔁 Re-queuing message for agent '{msg.receiver}'")
                    self.queue.put(msg)

                time.sleep(0.01)  # Reduced from 0.05 to 0.01 seconds

            except Exception as e:
                logger.error(f"🚨 Uncaught exception in process_queue: {e}", exc_info=True)

    def dispatch_message(self, message: Message):
        """Routes messages to the correct handler based on registered events."""
        agent_name = message.receiver

        if message.receiver is not None:
            if message.receiver not in DI.agent_registry.list_all_agent_names():
                logger.warning(f"🚨 Message has receiver='{message.receiver}', but it's not a known agent. "
                               f"This may be a handler misusing receiver or a namespacing bug.")
                exit(1)

        if agent_name is not None and agent_name not in DI.agent_registry.list_all_agent_names():
            logger.error(f"🚨 Received a message with an invalid agent_name: {message}")
            return

        if self.is_agent_busy(agent_name):
            current_time = time.time()
            logger.warning(f"⚠️ Agent '{agent_name}' is busy. Queuing message.")

            if agent_name not in self.requeued_timestamps:
                self.requeued_timestamps[agent_name] = current_time
            else:
                elapsed = current_time - self.requeued_timestamps[agent_name]
                if elapsed >= self.max_wait_time:
                    logger.error(f"🚨 Agent '{agent_name}' has been busy for {self.max_wait_time} seconds. Forcing release.")
                    self.set_agent_status(agent_name, False)
                else:
                    logger.warning(f"⚠️ Agent '{agent_name}' still busy (waited {elapsed:.2f}s).")

            self.pending_messages.setdefault(agent_name, []).append(message)
            return

        # Clear requeue timestamp if present
        self.requeued_timestamps.pop(agent_name, None)

        handler = self.event_registry.get(message.event_topic, self.default_handler)

        if handler == self.default_handler:
            logger.warning(f"⚠️ No handler registered for event: {message.event_topic}. Using default handler.")

        logger.debug(f"🚀 Dispatching message with event key '{message.event_topic}' to handler {handler}")
        handler(message)


    def default_handler(self, message: Message):
        """Handles unknown or unregistered events."""
        logger.warning(f"⚠️ No handler registered for event: {message.event_topic}")

    def list_registered_events(self):
        """Lists all registered events and their handlers."""
        logger.debug("=== Registered Events in Hub ===")
        if not self.event_registry:
            logger.debug("No events have been registered yet.")
        else:
            for event_key, handler in self.event_registry.items():
                logger.debug(f"Event: {event_key}, Handler: {handler}")
        logger.debug("==================================")


    def unregister_event(self, event_key, handler=None):
        """
        Unregisters a previously registered event. If a handler is provided, it must match the registered one.
        Logs a warning if the event wasn't found or the handler doesn't match.
        """
        if event_key in self.event_registry:
            if handler is None or self.event_registry[event_key] == handler:
                removed_handler = self.event_registry.pop(event_key)
                logger.info(f"🗑️ Unregistered event: {event_key} (Handler: {removed_handler})")
            else:
                logger.warning(
                    f"⚠️ Handler mismatch while trying to unregister event '{event_key}'. "
                    f"Expected: {self.event_registry[event_key]}, Got: {handler}"
                )
        else:
            logger.warning(f"⚠️ Attempted to unregister unknown event: {event_key}")


    def stop(self):
        """Stops the message processing thread gracefully."""
        self.running = False
        self.queue.put(None)
        self.worker_thread.join()
        logger.info("🛑 EventHandlerHub stopped gracefully.")
