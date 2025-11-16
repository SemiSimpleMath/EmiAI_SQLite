from datetime import datetime, timezone
import uuid
from typing import List, Optional, Any
from sqlalchemy import select
from sentence_transformers import SentenceTransformer
from app.models.base import get_session
from app.assistant.database.db_handler import RAGDatabase

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

class RAGDBHandler:
    def __init__(self, embedding_model: Optional[Any] = None):
        self.embedding_model = embedding_model or SentenceTransformer("all-MiniLM-L6-v2")

    def insert_rag_facts(self, data_list: List[Any], source_name: str) -> None:
        db_session = get_session()
        new_entries = []

        print("\n\n\nAt insert_rag_facts")
        print("Labeled facts: ",data_list)
        print("source ", source_name)

        try:
            for fact in data_list:
                embedding = self.embedding_model.encode(fact).tolist()
                existing = db_session.execute(
                    select(RAGDatabase).where(RAGDatabase.document == fact)
                ).scalars().first()
                if not existing:
                    new_entries.append(RAGDatabase(
                        id=str(uuid.uuid4()),
                        document=fact,
                        embedding=embedding,
                        source=source_name,
                        timestamp=datetime.now(timezone.utc),
                        processed=False,
                        scope=source_name,
                    ))
            if new_entries:
                db_session.add_all(new_entries)
                db_session.commit()
        except Exception as e:
            db_session.rollback()
            logger.error(f"[{source_name}] Error inserting RAG facts: {e}")
        finally:
            db_session.close()
