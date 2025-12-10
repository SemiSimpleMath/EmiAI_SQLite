# app/assistant/lib/core_tools/email_tool/utils/gmail_api_client.py
"""
Gmail API client using OAuth2 credentials
"""
from pathlib import Path
import pickle
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify'  # Required to mark emails as read
]

class GmailAPIClient:
    """Gmail API client using OAuth2"""
    
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _get_credentials_path(self):
        """Get path to OAuth credentials"""
        credentials_dir = Path(__file__).resolve().parents[3] / 'credentials'
        return credentials_dir / 'credentials.json'
    
    def _get_token_path(self):
        """Get path to OAuth token"""
        credentials_dir = Path(__file__).resolve().parents[3] / 'credentials'
        return credentials_dir / 'token.pickle'
    
    def _authenticate(self):
        """Authenticate with Gmail API using OAuth2"""
        creds = None
        token_path = self._get_token_path()
        credentials_path = self._get_credentials_path()
        
        # Load existing token
        if token_path.exists():
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
        
        # Refresh or get new credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    logger.info("Gmail credentials refreshed successfully.")
                    # Save refreshed token
                    with open(token_path, 'wb') as token:
                        pickle.dump(creds, token)
                except Exception as e:
                    logger.error(f"Error refreshing Gmail credentials: {e}")
                    creds = None
            
            if not creds:
                # No valid credentials - user needs to authenticate via web UI
                raise FileNotFoundError(
                    f"Gmail OAuth token not found or invalid at {token_path}. "
                    "Please authenticate through the setup wizard or features settings."
                )
        
        try:
            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail API service initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to create Gmail service: {e}")
            raise
    
    def search_emails(self, query, max_results=100):
        """
        Search emails using Gmail query syntax
        
        Args:
            query: Gmail query string (e.g., "is:unread after:2024/01/01")
            max_results: Maximum number of emails to return
            
        Returns:
            List of email metadata dicts with keys: uid, subject, from, date
        """
        try:
            # LOG EXACT PARAMETERS BEING SENT TO GMAIL API
            logger.info("="*80)
            logger.info("📧 GMAIL API CALL - EXACT PARAMETERS:")
            logger.info(f"   userId: 'me'")
            logger.info(f"   query (q): '{query}'")
            logger.info(f"   maxResults: {max_results}")
            logger.info("="*80)
            
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            # LOG EXACT RESPONSE FROM GMAIL API
            logger.info("="*80)
            logger.info("📬 GMAIL API RESPONSE:")
            logger.info(f"   Total messages returned: {len(messages)}")
            logger.info(f"   Message IDs: {[msg['id'] for msg in messages[:5]]}{'...' if len(messages) > 5 else ''}")
            logger.info("="*80)
            
            email_list = []
            for msg in messages:
                email_list.append({
                    'uid': msg['id'],
                    'threadId': msg.get('threadId', '')
                })
            
            return email_list
            
        except HttpError as e:
            if e.resp.status == 401:
                logger.error("❌ Gmail authentication failed (401 UNAUTHENTICATED)")
                logger.error(f"   Error details: {e.error_details if hasattr(e, 'error_details') else e}")
                logger.error("   ⚠️  Please re-authenticate through the Features settings page")
                # Delete the invalid token so next initialization will prompt for re-auth
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted invalid token at {token_path}")
                raise FileNotFoundError(
                    "Gmail authentication expired or invalid. Please re-authenticate through the Features settings page."
                )
            elif e.resp.status == 403 and "insufficient" in str(e).lower():
                logger.error("❌ Gmail authentication has insufficient scopes (403)")
                logger.error(f"   Error details: {e}")
                logger.error("   ⚠️  The token doesn't have required permissions (gmail.readonly, gmail.send, gmail.modify)")
                logger.error("   ⚠️  Deleting token - please re-authenticate through the Features settings page")
                # Delete the insufficient token
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted insufficient token at {token_path}")
                raise FileNotFoundError(
                    "Gmail token has insufficient permissions. Please re-authenticate through the Features settings page to grant all required scopes."
                )
            else:
                logger.error(f"Gmail API HTTP error ({e.resp.status}): {e}")
                return []
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            return []
    
    def fetch_full_email(self, message_id):
        """
        Fetch full email content by message ID
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Dict with keys: uid, raw_email (full RFC822 format)
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='raw'
            ).execute()
            
            # Decode the raw message
            raw_email = base64.urlsafe_b64decode(message['raw']).decode('utf-8')
            
            return {
                'uid': message_id,
                'raw_email': raw_email
            }
            
        except HttpError as e:
            if e.resp.status == 401:
                logger.error("❌ Gmail authentication failed (401 UNAUTHENTICATED) while fetching email")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted invalid token at {token_path}")
                raise FileNotFoundError(
                    "Gmail authentication expired or invalid. Please re-authenticate through the Features settings page."
                )
            elif e.resp.status == 403 and "insufficient" in str(e).lower():
                logger.error("❌ Gmail token has insufficient scopes (403) while fetching email")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted insufficient token at {token_path}")
                raise FileNotFoundError(
                    "Gmail token has insufficient permissions. Please re-authenticate through the Features settings page."
                )
            else:
                logger.error(f"Gmail API HTTP error ({e.resp.status}) fetching email {message_id}: {e}")
                return None
        except Exception as e:
            logger.error(f"Error fetching email {message_id}: {e}")
            return None
    
    def send_email(self, to, subject, body):
        """
        Send an email via Gmail API
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text)
            
        Returns:
            Dict with message ID if successful, None otherwise
        """
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info(f"Email sent successfully to {to}. Message ID: {sent_message['id']}")
            return {'id': sent_message['id']}
            
        except HttpError as e:
            if e.resp.status == 401:
                logger.error("❌ Gmail authentication failed (401 UNAUTHENTICATED) while sending email")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted invalid token at {token_path}")
                raise FileNotFoundError(
                    "Gmail authentication expired or invalid. Please re-authenticate through the Features settings page."
                )
            elif e.resp.status == 403 and "insufficient" in str(e).lower():
                logger.error("❌ Gmail token has insufficient scopes (403) while sending email")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted insufficient token at {token_path}")
                raise FileNotFoundError(
                    "Gmail token has insufficient permissions. Please re-authenticate through the Features settings page."
                )
            else:
                logger.error(f"Gmail API HTTP error ({e.resp.status}) sending email: {e}")
                return None
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return None
    
    def mark_as_read(self, message_id):
        """Mark an email as read"""
        logger.info(f"📝 MARK_AS_READ called for message_id: {message_id}")
        logger.info(f"   API endpoint: https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}/modify")
        logger.info(f"   Request body: {{'removeLabelIds': ['UNREAD']}}")
        
        try:
            result = self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logger.info(f"✅ Successfully marked email {message_id} as read")
            logger.info(f"   API response: {result}")
        except HttpError as e:
            if e.resp.status == 401:
                logger.error("❌ Gmail authentication failed (401 UNAUTHENTICATED) while marking email as read")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted invalid token at {token_path}")
                raise FileNotFoundError(
                    "Gmail authentication expired or invalid. Please re-authenticate through the Features settings page."
                )
            elif e.resp.status == 403 and "insufficient" in str(e).lower():
                logger.error("❌ Gmail token has insufficient scopes (403) while marking email as read")
                logger.error("   ⚠️  Missing 'gmail.modify' scope - token was created before this scope was added")
                token_path = self._get_token_path()
                if token_path.exists():
                    token_path.unlink()
                    logger.info(f"   Deleted insufficient token at {token_path}")
                raise FileNotFoundError(
                    "Gmail token has insufficient permissions (missing gmail.modify). Please re-authenticate through the Features settings page."
                )
            else:
                logger.error(f"❌ Gmail API HTTP error ({e.resp.status}) marking email {message_id} as read: {e}")
                logger.error(f"   Error type: {type(e).__name__}")
                logger.error(f"   Error details: {str(e)}")
                raise  # Re-raise so caller can handle it
        except Exception as e:
            logger.error(f"❌ Error marking email {message_id} as read: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error details: {str(e)}")
            raise  # Re-raise so caller can handle it
    
    def build_query(self, start_date=None, end_date=None, start_timestamp=None, end_timestamp=None, unseen=False, search_string=None):
        """
        Build Gmail search query from parameters
        
        Args:
            start_date: Start date in format YYYY/MM/DD (deprecated, use start_timestamp)
            end_date: End date in format YYYY/MM/DD (deprecated, use end_timestamp)
            start_timestamp: Unix timestamp for start (preferred)
            end_timestamp: Unix timestamp for end (preferred)
            unseen: If True, search only unread emails
            search_string: Additional search terms
            
        Returns:
            Gmail query string
        """
        query_parts = []
        
        # Prefer unix timestamps over date strings (more precise)
        if start_timestamp:
            query_parts.append(f"after:{int(start_timestamp)}")
        elif start_date:
            query_parts.append(f"after:{start_date}")
        
        if end_timestamp:
            query_parts.append(f"before:{int(end_timestamp)}")
        elif end_date:
            query_parts.append(f"before:{end_date}")
        
        if unseen:
            query_parts.append("is:unread")
        
        if search_string:
            query_parts.append(search_string)
        
        query = " ".join(query_parts)
        logger.debug(f"Built Gmail query: {query}")
        return query

