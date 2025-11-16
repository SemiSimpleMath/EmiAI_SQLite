import traceback
from sqlalchemy import insert

from app.models.base import get_session
from app.assistant.database.db_handler import UnifiedLog
from app.assistant.utils.logging_config import get_maintenance_logger

logger = get_maintenance_logger(__name__)


def save_to_unified_db(messages, source: str, db_session=None, force_test_db=False):
    """
    Save messages to the UnifiedLog table.

    Args:
        messages: List of messages (must have id, timestamp, content, and optional role).
        source: Source string (e.g., 'chat', 'slack', 'email').
        db_session: Optional SQLAlchemy session.
        force_test_db: If True, force use test database.
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

        records = [
            {
                'id': msg.get('id'),
                'timestamp': msg.get('timestamp'),
                'role': msg.get("role", None) or 'unknown',
                'message': msg.get('message'),
                'source': source,
                'processed': False,
            }
            for msg in messages
        ]

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
