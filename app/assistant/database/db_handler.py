import uuid
from typing import Type, Iterable, List, Dict, Optional, Any
from sqlalchemy import create_engine, Column, Integer, Text, JSON, TIMESTAMP, func, String, Boolean
from sqlalchemy.sql import select
from datetime import date

from app.models.base import Base  # Import Base from base.py
from app.models.base import get_session

import json
from hashlib import sha256

from sqlalchemy import Column, String, JSON, DateTime, func

# Note: UUID type not needed for SQLite (using Text for IDs)

# Unified ingestion log model
class UnifiedLog(Base):
    __tablename__ = 'unified_log'

    id = Column(Text, primary_key=True)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    role = Column(Text)
    message = Column(Text, nullable=False)
    source = Column(Text, nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

class InfoDatabase(Base):
    __tablename__ = 'info_database'

    id = Column(Text, primary_key=True)
    label = Column(String, nullable=False)
    info = Column(Text, nullable=False)
    timestamp = Column(TIMESTAMP(timezone=True), nullable=True)
    relevance_score = Column(Integer, nullable=True)
    source = Column(String, nullable=True)

class AgentActivityLog(Base):
    __tablename__ = 'agent_activity_log'

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now())
    agent_name = Column(String, nullable=True)
    description = Column(String, nullable=False)
    parameters = Column(JSON, nullable=True)
    status = Column(String, nullable=False, default="pending")
    notes = Column(Text, nullable=True)

class RAGDatabase(Base):
    __tablename__ = 'rag_database'

    id = Column(Text, primary_key=True)
    document = Column(Text, nullable=False)
    embedding = Column(JSON, nullable=False)
    source = Column(String, nullable=True)
    scope = Column(String, nullable=False, default='chat')
    timestamp = Column(TIMESTAMP(timezone=True), nullable=False)
    processed = Column(Boolean, default=False, nullable=False)

class EventRepository(Base):
    __tablename__ = 'event_repository'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, nullable=False)
    data_type = Column(String, nullable=False)
    data = Column(JSON, nullable=False)
    data_hash = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=func.now())

class EmailCheckState(Base):
    __tablename__ = 'email_check_state'

    id = Column(Integer, primary_key=True, default=1)
    last_checked = Column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    @staticmethod
    def compute_hash(event_data):
        """Compute a SHA-256 hash of the event data."""
        return sha256(json.dumps(event_data, sort_keys=True).encode()).hexdigest()

def initialize_database(force_test_db=False):
    """
    Initialize all defined tables in the database.
    """
    # Use get_session to get the correct engine
    session = get_session(force_test_db=force_test_db)
    engine = session.bind
    
    Base.metadata.create_all(engine)
    session.close()

def fetch_unprocessed_logs_by_date(
        self,
        source_model: Type,
        source_name: str,
        batch_date: date,
        filter_roles: Optional[Iterable[str]] = None,
        batch_size: int = 100
) -> List[Dict[str, Any]]:
    db_session = get_session()
    try:
        query = select(source_model).where(
            source_model.processed == False,
            source_model.source == source_name,
            func.date(source_model.timestamp) == batch_date
        )
        if filter_roles:
            query = query.where(source_model.role.in_(filter_roles))
        query = query.order_by(source_model.timestamp.asc()).limit(batch_size)
        results = db_session.execute(query).scalars().all()
        return [
            {
                "id": log.id,
                "timestamp": log.timestamp,
                "message": getattr(log, "message", None),
                "role": getattr(log, "role", None)
            }
            for log in results
        ]
    finally:
        db_session.close()

if __name__ == "__main__":
    # Force use test database
    initialize_database(force_test_db=True)
    print("\nDatabase initialized successfully in test database.")
