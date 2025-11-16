# drop_news_tables.py

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from app.models.base import Base
from app.assistant.news.news_schema import (
    NewsCategory,
    NewsLabel,
    NewsScore,
    NewsArticle,
    NewsFeedback
)
from app.assistant.database.db_handler import engine

# Configure logging
from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

def drop_news_tables():
    """
    Drops all news-related tables from the database in the correct order to respect foreign key dependencies.
    """
    # List of tables to drop in order respecting foreign key dependencies
    tables_to_drop = [
        NewsFeedback.__table__,  # Drop child tables first
        NewsArticle.__table__,
        NewsScore.__table__,
        NewsLabel.__table__,
        NewsCategory.__table__,   # Drop parent tables last
    ]

    try:
        # Initialize inspector to check existing tables
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # Filter tables that actually exist
        tables_present = [table for table in tables_to_drop if table.name in existing_tables]

        if not tables_present:
            logger.info("No news-related tables found to drop.")
            return

        # Drop the tables
        Base.metadata.drop_all(bind=engine, tables=tables_present)
        logger.info("Successfully dropped news-related tables.")
    except SQLAlchemyError as e:
        logger.error(f"Error dropping tables: {e}")
        raise

if __name__ == "__main__":
    drop_news_tables()
