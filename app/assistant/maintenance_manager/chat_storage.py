import traceback
from sqlalchemy import insert

from app.models.base import get_session
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.utils.logging_config import get_maintenance_logger

logger = get_maintenance_logger(__name__)


def save_chat_messages(blackboard, db_session=None, force_test_db=False):
    """
    Save chat messages (not tool output or system messages) to the UnifiedLog table.
    Source is always set to 'chat'.
    """
    own_session = False
    if db_session is None:
        db_session = get_session(force_test_db=force_test_db)
        own_session = True

    try:
        chat_messages = [msg for msg in blackboard.get_messages() if msg.is_chat]

        if not chat_messages:
            logger.info("No chat messages to save.")
            return

        records = [
            {
                'id': msg.id,
                'timestamp': msg.timestamp,
                'role': msg.role or 'unknown',
                'message': msg.content,
                'source': 'chat',
                'processed': False,
            }
            for msg in chat_messages
        ]

        # SQLite: Use INSERT OR IGNORE instead of PostgreSQL's ON CONFLICT DO NOTHING
        stmt = insert(UnifiedLog).values(records).prefix_with('OR IGNORE')
        result = db_session.execute(stmt)
        db_session.commit()
        logger.info(f"Chat history saved. Rows inserted: {result.rowcount}")

    except Exception:
        db_session.rollback()
        logger.error("Error saving chat history:")
        logger.error(traceback.format_exc())

    finally:
        if own_session:
            db_session.close()
