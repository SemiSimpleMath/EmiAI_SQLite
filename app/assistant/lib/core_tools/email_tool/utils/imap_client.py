import imaplib
import email
from email import policy

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class IMAPClient:
    """Handles IMAP authentication and email fetching."""

    def __init__(self, email_addr, email_password, imap_url="imap.gmail.com"):
        self.email_addr = email_addr
        self.email_password = email_password
        self.imap_url = imap_url
        self.mail = self.authenticate()

    def authenticate(self):
        """Authenticate with the IMAP server."""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_url)
            mail.login(self.email_addr, self.email_password)
            return mail
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP authentication failed: {e}")
            raise

    def search_emails(self, date_since: str, unseen: bool, search_string: str):
        """Search for emails matching criteria."""
        self.mail.select("INBOX")
        criteria = [f"SINCE {date_since}"]
        if unseen:
            criteria.append("UNSEEN")
        if search_string:
            criteria.append(f'TEXT "{search_string}"')

        self.ensure_authenticated()
        print(criteria)
        result, data = self.mail.uid("search", None, *criteria)

        if result != "OK":
            logger.error("Failed to search emails")
            return []

        email_uids = [{"uid": email_uid.decode()} for email_uid in data[0].split()]
        logger.info(f"📧 Gmail IMAP API returned {len(email_uids)} emails")
        return email_uids

    def fetch_full_email(self, email_uid: str):
        """Fetch full email content."""
        result, email_data = self.mail.uid("fetch", email_uid, "(RFC822)")
        if result != "OK":
            logger.error(f"Failed to fetch full email for UID {email_uid}")
            return {}

        email_message = email.message_from_bytes(email_data[0][1], policy=policy.default)
        return {"uid": email_uid, "raw_email": email_message}

    def ensure_authenticated(self):
        try:
            self.mail.noop()  # Ping the server to check if session is alive
        except:
            logger.warning("IMAP session expired, reconnecting...")
            self.mail = self.authenticate()  # Re-authenticate
