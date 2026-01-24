"""
Migration: Add ticket_type and effects_processed columns to proactive_tickets table

Adds:
- ticket_type (TEXT) - "wellness", "tool_approval", "task", "general"
- effects_processed (INTEGER, default 0)
"""

from app.models.base import get_session
from sqlalchemy import text


def migrate():
    """Add new columns for ticket type tracking."""
    session = get_session()
    
    try:
        # Check if columns already exist
        result = session.execute(text("PRAGMA table_info(proactive_tickets)"))
        columns = [row[1] for row in result.fetchall()]
        
        if "ticket_type" not in columns:
            session.execute(text(
                "ALTER TABLE proactive_tickets ADD COLUMN ticket_type TEXT"
            ))
            print("Added ticket_type column")
        else:
            print("ticket_type column already exists")
        
        if "effects_processed" not in columns:
            session.execute(text(
                "ALTER TABLE proactive_tickets ADD COLUMN effects_processed INTEGER DEFAULT 0"
            ))
            print("Added effects_processed column")
        else:
            print("effects_processed column already exists")
        
        session.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        session.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
