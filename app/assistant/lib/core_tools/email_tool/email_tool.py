# app/assistant/lib/core_tools/email_tool/email_tool.py

from app.assistant.lib.core_tools.base_tool.base_tool import BaseTool
from app.assistant.lib.core_tools.email_tool.utils.email_utils import EmailUtils
from app.assistant.utils.pydantic_classes import ToolResult, ToolMessage

import os
from datetime import datetime, timezone, timedelta

from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class EmailTool(BaseTool):
    """
    High-level tool for managing emails.
    - Fetches emails based on time range.
    - Summarizes emails using an LLM.
    - Stores results in EventRepositoryManager.
    """

    def __init__(self):
        super(EmailTool, self).__init__('email_tool')
        self.email_utils = None
        self.init_done = False
        self.agent_factory = None

    def init(self):
        """Initialize email handling with Gmail API."""
        if self.init_done:
            return

        # No longer need IMAP credentials - Gmail API uses OAuth
        self.email_utils = EmailUtils()
        self.init_done = True

    # app/assistant/lib/core_tools/email_tool/email_tool.py

    @staticmethod
    def format_imap_date(date_str: str) -> str:
        """
        Convert an ISO 8601 string (with or without timezone) or a YYYY-MM-DD string
        to the IMAP format (DD-MMM-YYYY), using UTC as the reference if ambiguous.
        """
        try:
            # Try ISO 8601 first
            parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            parsed_utc = parsed.astimezone(timezone.utc)
            return parsed_utc.strftime("%d-%b-%Y")
        except ValueError:
            # Fallback: plain date string treated as UTC date
            try:
                parsed = datetime.strptime(date_str, "%Y-%m-%d")
                return parsed.strftime("%d-%b-%Y")
            except ValueError:
                raise ValueError(
                    f"Invalid date format: {date_str}. Expected ISO 8601 or YYYY-MM-DD."
                )


    def execute(self, tool_message: ToolMessage) -> ToolResult:
        """Fetches and processes emails with a hard 7 day lookback cap."""
        self.init()

        arguments = tool_message.tool_data.get("arguments", {})
        raw_start = arguments.get("start_date")
        raw_end = arguments.get("end_date")  # Not used for IMAP filter
        raw_unseen = arguments.get("unseen")
        repo_update = arguments.get("repo_update", False)
        search_string = arguments.get("search_string", None)

        now_utc = datetime.now(timezone.utc)
        MAX_LOOKBACK = timedelta(days=7)
        FUTURE_SKEW_FALLBACK = timedelta(hours=1)

        # Default unseen: True if not explicitly set
        unseen = True if raw_unseen is None else bool(raw_unseen)

        # Normalize and bound start_date
        if not raw_start:
            # No start_date; safe default is last 7 days
            bounded_start = now_utc - MAX_LOOKBACK
            logger.info(
                f"[EmailTool] No start_date provided. "
                f"Defaulting to {MAX_LOOKBACK.days} days ago: {bounded_start.isoformat()}"
            )
        else:
            try:
                iso_str = raw_start.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(iso_str)
                if parsed.tzinfo is None:
                    logger.warning(
                        f"[EmailTool] start_date '{raw_start}' was naive. Treating as UTC."
                    )
                    parsed = parsed.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.error(
                    f"[EmailTool] Failed to parse start_date '{raw_start}': {e}. "
                    f"Defaulting to {MAX_LOOKBACK.days} days ago."
                )
                parsed = now_utc - MAX_LOOKBACK

            # Future guard
            if parsed > now_utc:
                logger.warning(
                    f"[EmailTool] start_date {parsed} is in the future; "
                    f"adjusting to {FUTURE_SKEW_FALLBACK} ago."
                )
                parsed = now_utc - FUTURE_SKEW_FALLBACK

            # Hard cap lookback
            lookback = now_utc - parsed
            if lookback > MAX_LOOKBACK:
                logger.warning(
                    f"[EmailTool] start_date {parsed} is older than {MAX_LOOKBACK.days} days; "
                    f"capping to {MAX_LOOKBACK.days} days ago."
                )
                parsed = now_utc - MAX_LOOKBACK

            bounded_start = parsed

        start_date = bounded_start.replace(microsecond=0).isoformat()

        # Parse end_date for client-side filtering
        bounded_end = None
        if raw_end:
            try:
                iso_str = raw_end.replace("Z", "+00:00")
                parsed = datetime.fromisoformat(iso_str)
                if parsed.tzinfo is None:
                    logger.warning(
                        f"[EmailTool] end_date '{raw_end}' was naive. Treating as UTC."
                    )
                    parsed = parsed.replace(tzinfo=timezone.utc)
                bounded_end = parsed
            except Exception as e:
                logger.error(
                    f"[EmailTool] Failed to parse end_date '{raw_end}': {e}. "
                    f"Client-side end_date filtering will be skipped."
                )

        logger.info(
            f"[EmailTool] Final bounded start_date={start_date}, "
            f"end_date={bounded_end.isoformat() if bounded_end else 'None'}, "
            f"unseen={unseen}, repo_update={repo_update}, search_string={search_string}"
        )

        # Convert to IMAP SINCE date (date only, no time)
        imap_date = self.format_imap_date(start_date)

        # Fetch, process, and optionally update repo
        # Note: IMAP search only uses date, but we'll filter by timestamp client-side
        emails = self.email_utils.fetch_and_store_emails(
            start_date=imap_date,
            unseen=unseen,
            search_string=search_string,
            repo_update=repo_update,
            start_timestamp=bounded_start,
            end_timestamp=bounded_end,
        )

        return ToolResult(
            result_type="fetch_email",
            content=f"Processed {len(emails)} emails successfully.",
            data_list=emails,
        )


# === TEST BLOCK ===
if __name__ == "__main__":
    import app.assistant.tests.test_setup  # This is just run for the import
    from app.assistant.ServiceLocator.service_locator import DI
    from app.assistant.lib.blackboard.Blackboard import Blackboard

    # Configure logging for testing

    # Create a mock ToolMessage for testing
    mock_message = ToolMessage(
        data_type="tool_request",
        sender="test_user",
        receiver=None,
        task="fetch_emails",
        tool_name="fetch_email",
        tool_data={
            "arguments": {
                "start_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),  # Use today's date
                "unseen": True,
            }
        },
        request_id=None,
    )

    # Instantiate the tool and execute the fetch
    email_tool = EmailTool()
    result = email_tool.execute(mock_message)

    # Print results
    print(result.content)
    for email in result.data_list:
        print(email)
