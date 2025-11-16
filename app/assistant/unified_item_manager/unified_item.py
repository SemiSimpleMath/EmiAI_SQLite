"""
UnifiedItem Database Model
===========================

Represents a persistent, state-tracked item from any external source.
"""

from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text, Integer, Index, func, JSON
from app.models.base import Base


class ItemState(str, Enum):
    """
    State machine for UnifiedItems.
    
    Transitions:
    NEW -> TRIAGED (agent made initial decision)
    NEW -> DISMISSED (no action needed)
    NEW -> ACTION_PENDING (action planned)
    ACTION_PENDING -> ACTION_TAKEN (action completed)
    ACTION_PENDING -> FAILED (action failed)
    ANY -> SNOOZED (re-present later)
    SNOOZED -> NEW (when snooze expires)
    """
    NEW = "new"                      # Never seen by agent
    TRIAGED = "triaged"              # Agent reviewed, made decision
    ACTION_PENDING = "action_pending"  # Action decided, not complete
    ACTION_TAKEN = "action_taken"    # Action completed successfully
    DISMISSED = "dismissed"          # No action needed
    SNOOZED = "snoozed"             # Re-present at snooze_until time
    FAILED = "failed"                # Action attempted but failed


class UnifiedItem(Base):
    """
    Persistent state tracking for external events.
    
    Each item from email, calendar, todo, or scheduler is ingested once
    and tracked through its lifecycle. This prevents repeated triage of
    the same items across agent restarts.
    
    Key Fields:
    - unique_id: Source-specific identifier (e.g., "email:msg123")
    - state: Current processing state (NEW, DISMISSED, etc.)
    - source_type: Where it came from (email, calendar, todo, scheduler)
    - state_history: JSON log of all state transitions
    - snooze_until: When to re-present if snoozed
    """
    __tablename__ = 'unified_items'
    
    # ===== Primary Identification =====
    id = Column(Integer, primary_key=True)
    unique_id = Column(String(512), unique=True, nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # 'email', 'calendar', 'todo', 'scheduler', 'calendar_series'
    
    # ===== State Machine =====
    state = Column(String(50), nullable=False, default=ItemState.NEW, index=True)
    state_history = Column(JSON, nullable=False, default=list)  # Track all state transitions (SQLite compatible)
    
    # ===== Content =====
    title = Column(String(500))  # Subject, summary, title
    content = Column(Text)  # Full content/description
    data = Column(JSON)  # Full original data from source (SQLite compatible)
    item_metadata = Column(JSON)  # Additional metadata (e.g., recurring_event_id) - SQLite compatible
    
    # ===== Timestamps =====
    source_timestamp = Column(DateTime(timezone=True))  # When event actually occurred (email sent, meeting scheduled)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # ===== Snoozing =====
    snooze_until = Column(DateTime(timezone=True), nullable=True, index=True)
    snooze_count = Column(Integer, default=0)
    
    # ===== Agent Decisions =====
    agent_decision = Column(Text)  # What the agent decided to do
    agent_notes = Column(Text)  # Agent's reasoning
    related_action_id = Column(String(100))  # Link to AgentActivityLog
    
    # ===== Priority/Importance =====
    importance = Column(Integer, default=5)  # 1-10 scale (from source or agent)
    
    # ===== Indexes for Common Queries =====
    __table_args__ = (
        Index('idx_state_created', 'state', 'created_at'),
        Index('idx_state_source', 'state', 'source_type'),
        Index('idx_source_type_state', 'source_type', 'state'),
        Index('idx_snooze_until', 'snooze_until'),
    )
    
    def __repr__(self):
        return f"<UnifiedItem(id={self.id}, unique_id='{self.unique_id}', state='{self.state}', title='{self.title[:50]}')>"
    
    def to_dict(self):
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'unique_id': self.unique_id,
            'source_type': self.source_type,
            'state': self.state,
            'title': self.title,
            'content': self.content,
            'data': self.data,
            'item_metadata': self.item_metadata,
            'source_timestamp': self.source_timestamp.isoformat() if self.source_timestamp else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'snooze_until': self.snooze_until.isoformat() if self.snooze_until else None,
            'snooze_count': self.snooze_count,
            'agent_decision': self.agent_decision,
            'agent_notes': self.agent_notes,
            'related_action_id': self.related_action_id,
            'importance': self.importance,
            'state_history': self.state_history
        }


# ===== Database Management Functions =====

def initialize_unified_items_db():
    """Initialize unified_items table."""
    from app.models.base import get_session
    session = get_session()
    engine = session.bind
    print(f"🔍 Unified Items DB: Connecting to database: {engine.url}")
    Base.metadata.create_all(engine, tables=[UnifiedItem.__table__], checkfirst=True)
    session.close()
    print("✅ unified_items table initialized successfully.")


def drop_unified_items_db():
    """Drop unified_items table."""
    from app.models.base import get_session
    session = get_session()
    engine = session.bind
    Base.metadata.drop_all(engine, tables=[UnifiedItem.__table__], checkfirst=True)
    session.close()
    print("✅ unified_items table dropped successfully.")


def reset_unified_items_db():
    """Drop and recreate unified_items table."""
    print("⚠️  Resetting unified_items table...")
    drop_unified_items_db()
    initialize_unified_items_db()
    print("✅ unified_items table reset completed.")


if __name__ == "__main__":
    print("\n🚀 Initializing unified_items table...")
    initialize_unified_items_db()
    print("\n💡 Table created successfully (or already exists)!")
    print("📊 You can now use UnifiedItemManager to ingest and manage items.\n")

