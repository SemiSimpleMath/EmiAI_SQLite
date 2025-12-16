import traceback
from sqlalchemy import insert

from app.models.base import get_session
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.utils.logging_config import get_maintenance_logger

logger = get_maintenance_logger(__name__)


def _classify_message(message_content: str, message_role: str) -> str:
    """
    Use switchboard agent to classify a message.
    Returns category string or None if classification fails or not applicable.
    """
    # Only classify user messages
    if message_role != 'user':
        return None
    
    try:
        from app.assistant.ServiceLocator.service_locator import DI
        from app.assistant.utils.pydantic_classes import Message
        
        # Get or create switchboard agent
        switchboard = DI.agent_factory.create_agent('switchboard')
        if not switchboard:
            return None
        
        # Classify the message
        agent_input = {
            "message_content": message_content,
            "message_role": message_role
        }
        
        response = switchboard.action_handler(Message(agent_input=agent_input))
        result = response.data or {}
        
        category = result.get('category')
        confidence = result.get('confidence', 0)
        
        # Only use category if confidence is high enough
        if category and confidence >= 0.7:
            logger.info(f"[switchboard] Classified as '{category}' (conf: {confidence:.2f}): {message_content[:50]}...")
            return category
        
        return None
        
    except Exception as e:
        logger.warning(f"[switchboard] Classification failed: {e}")
        return None


def save_to_unified_db(messages, source: str, db_session=None, force_test_db=False, classify_messages=True):
    """
    Save messages to the UnifiedLog table.

    Args:
        messages: List of messages (must have id, timestamp, content, and optional role).
        source: Source string (e.g., 'chat', 'slack', 'email').
        db_session: Optional SQLAlchemy session.
        force_test_db: If True, force use test database.
        classify_messages: If True, run switchboard classification on user messages.
    """
    own_session = False
    if db_session is None:
        db_session = get_session(force_test_db=force_test_db)
        own_session = True
    print("save to unified", source)
    try:
        if not messages:
            logger.info(f"No {source} messages to save.")
            return

        records = []
        for msg in messages:
            role = msg.get("role", None) or 'unknown'
            message_content = msg.get('message', '')
            
            # Classify user messages before saving
            category = None
            if classify_messages and role == 'user' and message_content:
                category = _classify_message(message_content, role)
            
            records.append({
                'id': msg.get('id'),
                'timestamp': msg.get('timestamp'),
                'role': role,
                'message': message_content,
                'source': source,
                'processed': False,
                'category': category,
            })

        # SQLite: Use INSERT OR IGNORE instead of PostgreSQL's ON CONFLICT DO NOTHING
        stmt = insert(UnifiedLog).values(records).prefix_with('OR IGNORE')
        result = db_session.execute(stmt)
        db_session.commit()
        logger.info(f"[{source}] Messages saved. Rows inserted: {result.rowcount}")
        print(f"[{source}] Messages saved. Rows inserted: {result.rowcount}")
    except Exception:
        db_session.rollback()
        logger.error(f"[{source}] Error saving messages:")
        print("ERROR at save unified")
        logger.error(traceback.format_exc())

    finally:
        if own_session:
            db_session.close()
