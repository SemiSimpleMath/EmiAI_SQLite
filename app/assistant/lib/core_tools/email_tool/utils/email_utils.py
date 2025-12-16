# app/assistant/lib/core_tools/email_tool/utils/email_utils.py

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from email import message_from_string

from app.assistant.lib.core_tools.email_tool.utils.gmail_api_client import GmailAPIClient
from app.assistant.lib.core_tools.email_tool.utils.email_processor import EmailProcessor
from app.assistant.utils.pydantic_classes import Message
from app.assistant.event_repository.event_repository import EventRepositoryManager
from app.assistant.ServiceLocator.service_locator import DI
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

class EmailUtils:
    """Handles email fetching, processing, and storing using Gmail API."""

    def __init__(self):
        """Initialize Gmail API client"""
        self.gmail_client = GmailAPIClient()
        self.repo_manager = EventRepositoryManager()

    def fetch_and_store_emails(self, start_date, unseen=True, search_string=None, repo_update=False, 
                                start_timestamp=None, end_timestamp=None):
        """
        Fetch emails using Gmail API, process them, and optionally update the repo.

        Args:
            start_date: Start date string in Gmail format (YYYY/MM/DD)
            unseen: Whether to search only unseen emails
            search_string: Optional text search string
            repo_update: If True, store emails in EventRepository
            start_timestamp: Optional datetime for client-side filtering (inclusive)
            end_timestamp: Optional datetime for client-side filtering (inclusive)

        For repo_update=True (scheduler):
          - Store all qualifying emails in EventRepository (data_type='email').
          - Call sync_events_with_server once with all seen UIDs.
          - sync_events_with_server will prune email events older than 10 hours
            that were not seen in this run.

        For repo_update=False (agent queries):
          - Do not touch the repo at all. Just return processed_emails.
        """
        # Build Gmail query using unix timestamps (more precise than date strings)
        start_ts = None
        end_ts = None
        gmail_start_date = None
        
        if start_timestamp:
            # Convert to unix timestamp
            start_ts = int(start_timestamp.timestamp())
            logger.debug(f"Using start timestamp: {start_ts} ({start_timestamp})")
        else:
            # Fallback to date string if no timestamp provided
            gmail_start_date = self._convert_to_gmail_date(start_date)
            logger.debug(f"Using start date string: {gmail_start_date}")
        
        if end_timestamp:
            # Gmail's "before:" is exclusive, so add 1 second to make it inclusive
            end_ts = int(end_timestamp.timestamp()) + 1
            logger.debug(f"Using end timestamp: {end_ts} ({end_timestamp} + 1 second)")
        
        query = self.gmail_client.build_query(
            start_date=gmail_start_date,
            end_date=None,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            unseen=unseen,
            search_string=search_string
        )
        
        emails = self.gmail_client.search_emails(query, max_results=100)
        logger.info(f"Gmail API returned {len(emails)} candidates.")
        
        if not emails:
            logger.debug(f"📧 Email fetch complete: 0 candidates found, 0 stored")
            return []

        # Step 1: Filter by timestamp BEFORE parsing (to avoid wasting time on emails we'll discard)
        logger.info(f"📧 BEFORE timestamp filter: {len(emails)} emails from Gmail API")
        
        filtered_emails = []
        skipped_outside_timerange = 0
        
        if start_timestamp or end_timestamp:
            for email_meta in emails:
                # Fetch full email
                full_email = self.gmail_client.fetch_full_email(email_meta["uid"])
                if not full_email:
                    continue
                
                # Parse raw email string into EmailMessage object
                email_message = message_from_string(full_email["raw_email"])
                email_metadata = EmailProcessor.extract_metadata(email_message)
                
                date_received_str = email_metadata.get("date_received", "")
                if date_received_str and date_received_str != "[No Date]":
                    try:
                        email_datetime = parsedate_to_datetime(date_received_str)
                        # Ensure timezone-aware (parsedate_to_datetime returns timezone-aware)
                        if email_datetime.tzinfo is None:
                            email_datetime = email_datetime.replace(tzinfo=timezone.utc)
                        
                        # Filter by start_timestamp (inclusive)
                        if start_timestamp and email_datetime < start_timestamp:
                            skipped_outside_timerange += 1
                            logger.debug(
                                f"Skipping email {email_meta['uid']} - date {email_datetime} "
                                f"is before start_timestamp {start_timestamp}"
                            )
                            continue
                        
                        # Filter by end_timestamp (inclusive)
                        if end_timestamp and email_datetime > end_timestamp:
                            skipped_outside_timerange += 1
                            logger.debug(
                                f"Skipping email {email_meta['uid']} - date {email_datetime} "
                                f"is after end_timestamp {end_timestamp}"
                            )
                            continue
                    except Exception as e:
                        logger.warning(
                            f"Could not parse date_received '{date_received_str}' for email {email_meta['uid']}: {e}. "
                            f"Including email anyway."
                        )
                        # If we can't parse the date, include it to be safe
                
                # Email passed timestamp filter - store it for processing
                filtered_emails.append((email_meta, full_email, email_metadata))
        else:
            # No timestamp filtering - fetch all emails
            for email_meta in emails:
                full_email = self.gmail_client.fetch_full_email(email_meta["uid"])
                if not full_email:
                    continue
                # Parse raw email string into EmailMessage object
                email_message = message_from_string(full_email["raw_email"])
                email_metadata = EmailProcessor.extract_metadata(email_message)
                filtered_emails.append((email_meta, full_email, email_metadata))
        
        logger.info(f"📧 AFTER timestamp filter: {len(filtered_emails)} emails (skipped {skipped_outside_timerange} outside range)")
        
        # Step 2: Mark ALL filtered emails as read (for maintenance tool only)
        # Do this BEFORE parsing to avoid wasting time on emails we'll mark as read anyway
        if repo_update:
            logger.info(f"📧 Marking {len(filtered_emails)} emails as read...")
            for email_meta, full_email, email_metadata in filtered_emails:
                subject = email_metadata.get("subject", "No Subject")
                try:
                    self.gmail_client.mark_as_read(email_meta["uid"])
                    logger.info(f"✅ Marked email as read: {subject[:50]}")
                except Exception as e:
                    logger.error(f"❌ Failed to mark email as read: {subject[:50]} - Error: {e}")
                    # If this is a scope error, provide helpful guidance
                    if "insufficientPermissions" in str(e) or "insufficient authentication scopes" in str(e):
                        logger.error("⚠️  OAUTH SCOPE MISSING: Delete token.pickle and re-authenticate to get gmail.modify scope")
        
        # Step 3: Now parse only the emails that passed the timestamp filter
        # PHASE A: Process all emails with LLM (no DB writes)
        processed_emails = []
        email_ids = []
        skipped_low_importance = 0
        skipped_missing_importance = 0
        
        summary_agent = DI.agent_factory.create_agent("email_parser")
        logger.info(f"📧 Starting LLM processing for {len(filtered_emails)} emails...")

        for idx, (email_meta, full_email, email_metadata) in enumerate(filtered_emails):
            # Now extract body and parse (we already have metadata from filtering step)
            # Parse raw email string into EmailMessage object
            email_message = message_from_string(full_email["raw_email"])
            email_body = EmailProcessor.extract_email_body(email_message)

            agent_msg = Message(agent_input=email_body)
            result_data = summary_agent.action_handler(agent_msg)
            summary_data = result_data.data if hasattr(result_data, "data") else result_data
            
            logger.debug(f"📧 Processed email {idx+1}/{len(filtered_emails)}")

            email_data = {
                **email_metadata,
                **summary_data,
                "uid": email_meta["uid"],
                "data_type": "email",
            }

            # Require a valid importance; if missing or invalid, skip
            importance_raw = email_data.get("importance", None)

            if importance_raw is None:
                skipped_missing_importance += 1
                logger.error(
                    f"Email {email_meta['uid']} missing 'importance'. "
                    f"Skipping. Subject: {email_data.get('subject', 'No Subject')}"
                )
                continue

            try:
                importance = int(importance_raw)
            except (ValueError, TypeError):
                skipped_missing_importance += 1
                logger.error(
                    f"Invalid importance value '{importance_raw}' for email {email_meta['uid']}. "
                    f"Skipping. Subject: {email_data.get('subject', 'No Subject')}"
                )
                continue

            # Filter by importance - low importance emails are already marked as read but not stored
            if importance < 5:
                skipped_low_importance += 1
                logger.info(
                    f"⏭️  Skipping storage for email {email_meta['uid']} with importance {importance} (< 5): "
                    f"{email_data.get('subject', 'No Subject')} (already marked as read)"
                )
                continue

            processed_emails.append(email_data)
            if repo_update:
                email_ids.append(email_meta["uid"])

        # PHASE B: Batch write to database (quick, single burst)
        # This ensures DB lock is held for minimal time
        if repo_update and email_ids:
            logger.info(f"📧 Batch writing {len(email_ids)} emails to repository...")
            for email_data in processed_emails:
                self.repo_manager.store_event(
                    email_data["uid"],
                    event_data=email_data,
                    data_type="email",
                )
            # Single sync call enforces 10 hour policy for emails
            self.repo_manager.sync_events_with_server(email_ids, "email")
            logger.info(f"📧 Batch write complete")

        # Debug summary
        logger.info(
            f"📧 Email fetch complete: {len(emails)} candidates found, "
            f"{len(processed_emails)} stored (importance >= 5), "
            f"{skipped_low_importance} skipped (importance < 5), "
            f"{skipped_missing_importance} skipped (missing/invalid importance), "
            f"{skipped_outside_timerange} skipped (outside timestamp range)"
        )

        return processed_emails
    
    def _convert_to_gmail_date(self, imap_date_str):
        """
        Convert IMAP date format (DD-MMM-YYYY) to Gmail format (YYYY/MM/DD)
        
        Args:
            imap_date_str: Date string in IMAP format (e.g., "15-Nov-2024")
            
        Returns:
            Date string in Gmail format (e.g., "2024/11/15")
        """
        try:
            dt = datetime.strptime(imap_date_str, "%d-%b-%Y")
            return dt.strftime("%Y/%m/%d")
        except Exception as e:
            logger.warning(f"Could not convert date '{imap_date_str}': {e}. Using as-is.")
            return imap_date_str

