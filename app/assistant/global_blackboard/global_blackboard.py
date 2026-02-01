from datetime import datetime, timezone
from typing import List, Optional, Iterable, Set
import threading
from app.assistant.utils.pydantic_classes import Message


class GlobalBlackBoard():
    def __init__(self):

        self.socket_io = None
        self.socket_id = None

        self.messages: List[Message] = []
        self.messages_lock = threading.RLock()  # Thread safety for messages

        self.task = ""

        self.system_state_summary = {
            "news": [],
            "weather": [],
            "calendar": [],
            "scheduler": [],
            "email": [],
            "todo_task": []
        }
        self.system_state_timestamps = {  # Track last update time
            "news": None,
            "weather": None,
            "calendar": None,
            "scheduler": None,
            "email": None,
            "todo_task": None
        }

        self.state_dict = {}

    def set_socket(self, socket_io, socket_id):
        self.socket_io = socket_io
        self.socket_id = socket_id

    def get_socket_io(self):
        return self.socket_io

    def get_socket_id(self):
        return self.socket_id

    def add_msg(self, msg: Message):
        """
        Add a new message to the messages list and push it onto the state stack.
        """
        with self.messages_lock:
            # Check DI mode flags and apply to message
            from app.assistant.ServiceLocator.service_locator import ServiceLocator
            
            if ServiceLocator.test_mode:
                msg.test_mode = True
            elif ServiceLocator.memo_mode:
                msg.memo_mode = True
                
            print("\nAdding a message to the global blackboard:", msg)
            self.messages.append(msg)

    def clear_chat_messages(self):
        with self.messages_lock:
            new_messages = []
            for msg in self.messages:
                if not msg.is_chat:
                    new_messages.append(msg)
            self.messages = new_messages

    def clear_messages(self):
        """
        Clear all messages from the messages list.
        """
        with self.messages_lock:
            self.messages = []

    def get_all_messages(self):
        with self.messages_lock:
            return self.messages.copy()  # Return copy to prevent external modification

    def get_messages(
            self,
            data_types: Optional[List[str]] = None,
            senders: Optional[List[str]] = None,
            receivers: Optional[List[str]] = None,
            last_n: Optional[int] = None
    ) -> List[Message]:
        """
        Retrieve messages filtered by data_type, sender, receiver, and limit.

        Parameters:
        - data_types (List[str], optional): List of data_type strings to filter messages.
        - senders (List[str], optional): List of sender identifiers to filter messages.
        - receivers (List[str], optional): List of receiver identifiers to filter messages.
        - last_n (int, optional): If specified, return only the last n messages matching the criteria.

        Returns:
        - List[Message]: List of filtered Message objects.
        """
        with self.messages_lock:
            filtered_messages = []
            for msg in self.messages:
                if data_types and msg.data_type not in data_types:
                    continue
                if senders and msg.sender not in senders:
                    continue
                if receivers and msg.receiver not in receivers:
                    continue
                filtered_messages.append(msg)
            if last_n:
                return filtered_messages[-last_n:]
            else:
                return filtered_messages

    def get_messages_str(self, N: int = -1) -> str:
        """
        Concatenate the content of the last N messages into a single string.

        Parameters:
        - N (int): Number of recent messages to include. If N is negative, include all messages.

        Returns:
        - str: Concatenated string of message contents.
        """
        with self.messages_lock:
            print("\nGetting messages at global blackboard: ", self.messages)
            if N > len(self.messages):
                N = len(self.messages)
            if N > 0:
                hist_items = self.messages[-N:]
            else:
                hist_items = self.messages
            hist_str = ""
            for item in hist_items:
                hist_str += " " + item.content if item.content else ""
            return hist_str

    def get_messages_by_type(self, hist_types: List[str], last_n: Optional[int] = None) -> List[Message]:
        """
        Retrieve messages filtered by their data_type.

        Parameters:
        - hist_types (List[str]): List of data_type strings to filter messages.
        - last_n (int, optional): If specified, return only the last n messages matching the criteria.

        Returns:
        - List[Message]: List of filtered Message objects.
        """
        with self.messages_lock:
            hist_grab = [hist for hist in self.messages if hist.data_type in hist_types]
            if last_n is not None:
                return hist_grab[-last_n:]
            return hist_grab

    def get_messages_by_sub_type(self, sub_types: List[str], last_n: Optional[int] = None) -> List[Message]:
        """
        Retrieve messages filtered by their sub_data_type.

        Parameters:
        - sub_types (List[str]): List of sub_data_type strings to filter messages.
        - last_n (int, optional): If specified, return only the last n messages matching the criteria.

        Returns:
        - List[Message]: List of filtered Message objects.
        """
        with self.messages_lock:
            want = set(sub_types or [])
            hist_grab = [
                hist for hist in self.messages
                if want.intersection(set(getattr(hist, "sub_data_type", []) or []))
            ]
            if last_n is not None:
                return hist_grab[-last_n:]
            return hist_grab

    def get_recent_chat_since_utc(
        self,
        cutoff_utc: datetime,
        *,
        limit: Optional[int] = None,
        content_limit: Optional[int] = None,
        # Defaults: "clean human chat" only (opt-in for special message classes).
        include_tags: Optional[Iterable[str]] = None,
        exclude_tags: Optional[Iterable[str]] = None,
        include_command_scopes: Optional[Iterable[str]] = None,
        include_summarized: bool = False,
    ) -> List[Message]:
        """
        Canonical chat retrieval for routing/history building.

        Defaults are intentionally conservative:
        - Includes only `is_chat=True`
        - Excludes common non-chat / meta messages by tag
        - Excludes messages marked metadata["summarized"]=True (unless include_summarized=True)
        - Excludes slash commands unless explicitly allowed via include_command_scopes

        Notes:
        - Returned list is chronological (oldest -> newest).
        - Does NOT mutate stored messages; applies content_limit via shallow copies.
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

        def _copy_with_content(m: Message, new_content: str) -> Message:
            # Pydantic v1: .copy(update=...); v2: .model_copy(update=...)
            if hasattr(m, "model_copy"):
                return m.model_copy(update={"content": new_content})
            return m.copy(update={"content": new_content})

        cutoff = _to_utc(cutoff_utc)
        if cutoff is None:
            # If caller passed a bad timestamp, return nothing instead of leaking full chat.
            return []

        default_excluded: Set[str] = {
            "history_summary",
            "entity_card_injection",
            "agent_notification",
            "slash_command",
        }
        excluded = set(exclude_tags) if exclude_tags is not None else default_excluded
        required_any = {t for t in (include_tags or []) if isinstance(t, str) and t}
        allowed_scopes = {s for s in (include_command_scopes or []) if isinstance(s, str) and s}

        with self.messages_lock:
            msgs = self.messages.copy()

        selected: List[tuple[datetime, Message]] = []
        for m in msgs:
            try:
                if not getattr(m, "is_chat", False):
                    continue

                tags = set(getattr(m, "sub_data_type", []) or [])

                # Allow per-scope opt-in for slash commands (e.g. /music).
                if "slash_command" in tags and allowed_scopes:
                    meta = getattr(m, "metadata", None)
                    scope = meta.get("command_scope") if isinstance(meta, dict) else None
                    if scope in allowed_scopes:
                        # Treat as included: remove the tag that would otherwise be excluded by default.
                        tags.discard("slash_command")
                    else:
                        continue

                # If include_tags is specified, require at least one matching tag.
                if required_any and not tags.intersection(required_any):
                    continue

                # Exclude by tag set overlap
                if tags.intersection(excluded):
                    continue

                if not include_summarized:
                    meta = getattr(m, "metadata", None)
                    if isinstance(meta, dict) and bool(meta.get("summarized", False)):
                        continue

                ts_utc = _to_utc(getattr(m, "timestamp", None))
                if ts_utc is None or ts_utc <= cutoff:
                    continue

                if content_limit is not None:
                    c = getattr(m, "content", "") or ""
                    if len(c) > content_limit:
                        m = _copy_with_content(m, c[:content_limit])

                selected.append((ts_utc, m))
            except Exception:
                continue

        if not selected:
            return []

        selected.sort(key=lambda x: x[0])
        out = [m for _, m in selected]

        if limit is not None and limit > 0 and len(out) > limit:
            out = out[-limit:]

        return out

    def get_task(self):
        return self.task

    def get_latest_system_state_summary(self, category: str) -> Optional[dict]:
        """
        Retrieve the latest state for a given category.
        """
        if category in self.system_state_summary and self.system_state_summary[category]:
            return self.system_state_summary[category][-1]
        return None

    def get_latest_system_state_summary_time(self, category: str) -> Optional[str]:
        """
        Retrieve the last update timestamp for a given category.
        """
        return self.system_state_timestamps.get(category)

    def add_system_state_summary(self, category: str, message: dict):
        """
        Add a new system state summary entry and update the timestamp.
        """
        if category not in self.system_state_summary:
            print(f"Invalid category: {category}")
            return

        self.system_state_summary[category].append(message)
        self.system_state_timestamps[category] = datetime.now(timezone.utc)

        print(f"Updated {category} state at {self.system_state_timestamps[category]}")

    def update_state_value(self, key, value):
        """Overwrites the value of the given key in state_dict."""
        self.state_dict[key] = value

    def append_state_value(self, key, value):
        """
        Appends a value to the list stored at the given key.
        Initializes the key as a list if not present or not already a list.
        """
        current = self.state_dict.get(key)
        if current is None or not isinstance(current, list):
            self.state_dict[key] = []
        self.state_dict[key].append(value)

    def get_state_value(self, key, default=None):
        """Retrieve a value from the blackboard's state_dict safely."""
        return self.state_dict.get(key, default)
