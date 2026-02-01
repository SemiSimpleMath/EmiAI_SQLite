import json
from datetime import datetime, timezone

from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.pydantic_classes import Message

from app.assistant.utils.logging_config import get_maintenance_logger
logger = get_maintenance_logger(__name__)

class ChatSummaryRunner:
    """
    Calls the bb_summary agent to summarize a blackboard, then updates the blackboard with the result.
    """

    def __init__(self, blackboard, agent_name: str = "bb_summary"):
        self.blackboard = blackboard
        self.agent_name = agent_name

    def run(self):

        if len(self.blackboard.get_all_messages()) == 0:
            print("No messages to summarize.")
            return

        now_utc = datetime.now(timezone.utc)

        # ------------------------------------------------------------------
        # Build the list of chat messages eligible for summarization.
        #
        # We do NOT delete anything and we do NOT change `is_chat`.
        # We only add a metadata flag: metadata["summarized"] = True
        #
        # Emi agents can then exclude summarized messages from their prompt history
        # while other pipelines can still treat these as chat for their own needs.
        # ------------------------------------------------------------------
        all_msgs = self.blackboard.get_all_messages()

        def _ts_utc(m):
            ts = getattr(m, "timestamp", None)
            if not ts:
                return None
            try:
                # Some producers may store naive timestamps; treat as UTC.
                if getattr(ts, "tzinfo", None) is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                return ts.astimezone(timezone.utc)
            except Exception:
                return None

        # Eligible chat messages (exclude injections, notifications, summary messages)
        eligible = []
        for m in all_msgs:
            if not getattr(m, "is_chat", False):
                continue
            sub = set(getattr(m, "sub_data_type", []) or [])
            if sub.intersection({"entity_card_injection", "agent_notification", "history_summary"}):
                continue
            ts = _ts_utc(m)
            if ts is None:
                continue
            eligible.append((ts, m))

        if not eligible:
            logger.info("No eligible chat messages to summarize.")
            return

        eligible.sort(key=lambda x: x[0])
        eligible_msgs = [m for _, m in eligible]

        # Keep a tail of recent chat *unsummarized* (these remain available to Emi as raw recent history).
        KEEP_UNSUMMARIZED_TAIL = 30
        if len(eligible_msgs) <= KEEP_UNSUMMARIZED_TAIL:
            logger.info("Chat history below tail threshold; skipping summarization.")
            return

        to_summarize = eligible_msgs[:-KEEP_UNSUMMARIZED_TAIL]

        # Only summarize messages that haven't already been summarized.
        def _is_summarized(m) -> bool:
            meta = getattr(m, "metadata", None)
            return isinstance(meta, dict) and bool(meta.get("summarized", False))

        new_chunk = [m for m in to_summarize if not _is_summarized(m)]
        if not new_chunk:
            logger.info("No new chat messages to summarize (already labeled).")
            return

        # Find existing summary (we keep at most one and update it)
        existing_summary_msg = None
        for m in reversed(all_msgs):
            if "history_summary" in (getattr(m, "sub_data_type", []) or []):
                existing_summary_msg = m
                break

        # Create the summary agent
        summary_agent = DI.agent_factory.create_agent(self.agent_name)

        # Build summarizer input: existing summary (if any) + new chunk messages
        summarized_payload = []
        if existing_summary_msg and getattr(existing_summary_msg, "content", None):
            summarized_payload.append(
                {
                    "sender": "history_summary",
                    "receiver": None,
                    "content": existing_summary_msg.content,
                    "is_chat": True,
                }
            )

        for msg in new_chunk:
            summarized_payload.append(
                {
                    "sender": getattr(msg, "sender", None),
                    "receiver": getattr(msg, "receiver", None),
                    "content": getattr(msg, "content", None),
                    "is_chat": True,
                }
            )

        input_msg = json.dumps({"messages": summarized_payload})

        try:
            result = summary_agent.action_handler(Message(agent_input = input_msg))
        except Exception as e:
            logger.error(f"[{self.agent_name}] Failed to summarize blackboard: {e}")
            return
        
        # Agent with structured_output returns data as a dict in result.data, not data_list
        summary = result.data.get("summary", "") if result.data else ""

        summary_msg = Message(
            data_type="agent_msg",
            sub_data_type=["history_summary"],
            sender=self.agent_name,
            receiver=None,
            content=summary,
            is_chat=True,
            timestamp=now_utc,
            metadata={
                "summary_kind": "chat_history",
                "summarized_through_utc": _ts_utc(new_chunk[-1]).isoformat() if new_chunk else None,
            },
        )

        # IMPORTANT:
        # - Do NOT delete messages from the message system (global blackboard).
        # - Summarization should NOT change message semantics (e.g., do not flip is_chat).
        #
        # So the only safe action here is to append/update a summary message. Any
        # pruning/filtering for LLM prompt history must be done at the injection layer.

        # Update/append the summary message and mark the summarized chunk with metadata.
        try:
            if existing_summary_msg is not None:
                existing_summary_msg.content = summary_msg.content
                existing_summary_msg.sender = summary_msg.sender
                existing_summary_msg.timestamp = summary_msg.timestamp
                existing_summary_msg.metadata = summary_msg.metadata
                logger.info("Chat summary updated in-place (single summary retained).")
            else:
                self.blackboard.add_msg(summary_msg)
                logger.info("Chat summary appended to blackboard.")

            # Mark summarized messages (do not change is_chat)
            for m in new_chunk:
                meta = getattr(m, "metadata", None)
                if not isinstance(meta, dict):
                    meta = {}
                meta["summarized"] = True
                meta["summarized_at_utc"] = now_utc.isoformat()
                m.metadata = meta

            logger.info(f"Marked {len(new_chunk)} chat message(s) as summarized.")

        except Exception as e:
            logger.error(f"Failed to finalize chat summarization labeling: {e}")
