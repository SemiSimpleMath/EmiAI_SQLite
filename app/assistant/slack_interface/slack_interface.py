import json
import threading
import time
import os
from typing import Optional, Any

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.lib.blackboard.Blackboard import Blackboard
from app.assistant.utils.pydantic_classes import Message, ToolMessage, ToolResult
from app.assistant.lib.core_tools.slack.slack import SlackTool

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)


class SlackInterface:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if not cls._instance:
                cls._instance = super(SlackInterface, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.tool = SlackTool()
        self.channel_id = os.getenv("SLACK_CHANNEL_ID", "C08AB0R54HM")
        self.poll_interval = 20  # seconds
        self.last_ts: Optional[str] = None  # kept for backward compatibility
        self._stop_flag = threading.Event()

        self.seen_ts = set()  # For deduplication of messages

        self.blackboard = Blackboard()

        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

        self.last_considered_ts: Optional[str] = None

    def _poll_loop(self):
        while not self._stop_flag.is_set():
            try:
                self.poll_once()
            except Exception as e:
                logger.exception(f"[SlackInterface] Polling error: {e}")
            time.sleep(self.poll_interval)

    def poll_once(self):
        # Step 1: Pull new messages from Slack with a limit of 100
        try:
            result = self.tool.execute(ToolMessage(
                tool_name="get_messages",
                tool_data={
                    "tool_name": "get_messages",
                    "arguments": {
                        "channel_id": self.channel_id,
                        "limit": 100,
                    }
                }
            ))
        except Exception as e:
            logger.info(f"Something went wrong at slack_interface: {e}")
            print(f"Something went wrong at slack_interface: {e}")
            raise e

        # Extract messages from ToolResult
        if hasattr(result, 'data_list') and result.data_list:
            messages = result.data_list
        elif hasattr(result, 'data') and result.data:
            messages = result.data if isinstance(result.data, list) else []
        elif isinstance(result, list):
            messages = result
        else:
            messages = []
            
        # Sort messages by timestamp to ensure correct order
        try:
            messages = sorted(messages, key=lambda x: float(x.get("ts", 0)) if isinstance(x, dict) else 0)
        except Exception:
            pass

        # Step 2: If no new messages, exit
        if not messages:
            return

        # Step 3: Add new messages to blackboard with deduplication
        for m in messages:
            # Skip if m is not a dict (e.g., tuple or other type)
            if not isinstance(m, dict):
                logger.warning(f"Skipping non-dict message: {type(m)} - {m}")
                continue
                
            ts = m.get("ts")
            if not ts or ts in self.seen_ts:
                continue
            self.seen_ts.add(ts)

            role = "assistant" if m.get("name") == "Emi" else "user"
            msg_obj = Message(
                role=role,
                sender=m.get("name"),
                receiver=None,
                content=m.get("text", "").strip(),
                data_type="message",
                sub_data_type="slack_message",
                timestamp=ts,
                is_chat=True,
            )
            self.blackboard.add_msg(msg_obj)

        # Step 4: Build task and invoke manager based on blackboard context
        task_msg, new_latest_ts = self._build_task_message()

        # Skip if nothing new since last consideration
        if self.last_considered_ts and new_latest_ts and new_latest_ts <= self.last_considered_ts:
            logger.debug("[SlackInterface] No new messages since last consideration. Skipping.")
            self.last_ts = new_latest_ts
            return

        self.last_considered_ts = new_latest_ts

        if not task_msg.task.strip():
            logger.debug("[SlackInterface] No new messages after Emi. Skipping manager call.")
            self.last_ts = new_latest_ts
            return

        manager = DI.multi_agent_manager_factory.create_manager("slack_manager")
        result = manager.request_handler(task_msg)
        data = result.data

        # Step 5: Post reply to Slack (if any)
        if data:
            if isinstance(data, dict):
                message_text = "\n".join(str(v) for v in data.values() if v)
            else:
                message_text = str(data)

            if message_text.strip():
                post_msg = ToolMessage(
                    tool_name="send_message",
                    tool_data={
                        "tool_name": "send_message",
                        "arguments": {
                            "channel_id": self.channel_id,
                            "text": message_text,
                        }
                    }
                )
                self.tool.execute(post_msg) # comment this line to disable for debug.
            else:
                logger.debug("[SlackInterface] Emi returned only empty values.")
        else:
            logger.debug("[SlackInterface] Emi had nothing to say.")

        # Step 6: Advance window
        self.last_ts = new_latest_ts

    def _build_task_message(self) -> Any:
        """
        Builds the Message object to provide to the SlackManager.
        - If Emi has spoken:
            - info =  last 10 messages up to and including Emi's last message
            - task = all messages after that
        - If Emi has never spoken:
            - info = empty
            - task = last 10 messages total
        """

        def format_msgs(msgs):
            # Sort by timestamp then enumerate for clarity
            try:
                msgs = sorted(msgs, key=lambda m: float(m.timestamp or 0))
            except Exception:
                pass
            lines = []
            for idx, m in enumerate(msgs, start=1):
                ts = m.timestamp or ""
                lines.append(f"[{idx}] {ts} {m.sender}: {m.content.strip()}")
            return "\n".join(lines)

        all_msgs = self.blackboard.get_messages(20)
        # Ensure ordering in case blackboard returns unsorted
        try:
            all_msgs = sorted(all_msgs, key=lambda m: float(m.timestamp or 0))
        except Exception:
            pass

        last_emi_index = None
        for i in range(len(all_msgs) - 1, -1, -1):
            if all_msgs[i].sender == "Emi":
                last_emi_index = i
                break

        if last_emi_index is not None:
            info_msgs = all_msgs[max(0, last_emi_index - 9): last_emi_index + 1]
            task_msgs = all_msgs[last_emi_index + 1:]
        else:
            task_msgs = all_msgs[-10:]
            info_msgs = []

        task_text = format_msgs(task_msgs)
        info_text = format_msgs(info_msgs)

        latest_ts = task_msgs[-1].timestamp if task_msgs else None

        return Message(
            sender="slack_interface",
            receiver=None,
            data_type="message",
            sub_data_type="task",
            task=task_text,
            information=info_text
        ), latest_ts

    def stop(self):
        self._stop_flag.set()
        self.thread.join()


if __name__ == "__main__":
    interface = SlackInterface()
    print("[Test] SlackInterface started. Waiting for a couple polling cycles...")

    try:
        time.sleep(60)  # let it poll a few times
    finally:
        interface.stop()
        print("[Test] SlackInterface stopped.")
