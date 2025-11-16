"""
Entity Cards Database Model
Stores generated entity cards for prompt injection
"""

import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, DateTime, Text, Float, Boolean,
    UniqueConstraint, Index, func, Integer, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from app.models.base import Base, get_session

# SQLite compatibility: Custom type for JSON arrays
class JSONEncodedList(TypeDecorator):
    """Represents a list as JSON-encoded string for SQLite."""
    impl = Text
    cache_ok = True
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return None
    
    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return None


class EntityCard(Base):
    """
    Entity Card table for storing generated entity cards
    """
    __tablename__ = 'entity_cards'
    
    # Primary key (SQLite: UUID as TEXT)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Core entity information
    entity_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False)  # Removed index=True since we have explicit Index
    source_node_id = Column(String, nullable=True)  # Reference to KG node if applicable (UUID as TEXT)
    
    # Original KG data
    original_description = Column(Text, nullable=True)  # Original description from KG node
    original_aliases = Column(JSONEncodedList, nullable=True)  # Original aliases from KG node
    
    # Generated content
    summary = Column(Text, nullable=False)
    key_facts = Column(JSONEncodedList, nullable=True)  # Array of key facts
    relationships = Column(JSONEncodedList, nullable=True)  # Array of relationship descriptions
    
    # Metadata
    aliases = Column(JSONEncodedList, nullable=True)  # Alternative names for the entity (processed)
    confidence = Column(Float, nullable=True)  # Confidence score of the generation
    
    # Processing metadata
    batch_number = Column(Integer, nullable=True)  # Which batch this was processed in
    total_batches = Column(Integer, nullable=True)  # Total batches for the entity
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Additional metadata stored as JSON
    card_metadata = Column(JSON, nullable=False, default=dict)
    
    # Status tracking
    is_active = Column(Boolean, default=True, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)  # When last used for prompt injection
    usage_count = Column(Integer, default=0, nullable=False)  # How many times used
    
    __table_args__ = (
        # Unique constraint on entity name to prevent duplicates
        UniqueConstraint('entity_name', name='uq_entity_cards_entity_name'),
        
        # Indexes for efficient querying (SQLite compatible - no GIN indexes)
        Index('ix_entity_cards_entity_type', 'entity_type'),
        Index('ix_entity_cards_created_at', 'created_at'),
        Index('ix_entity_cards_last_used', 'last_used'),
        Index('ix_entity_cards_usage_count', 'usage_count'),
        Index('ix_entity_cards_is_active', 'is_active'),
        {'extend_existing': True}
    )


class EntityCardUsage(Base):
    """
    Track usage of entity cards for prompt injection
    """
    __tablename__ = 'entity_card_usage'
    
    # Primary key (SQLite: UUID as TEXT)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to entity card
    entity_card_id = Column(String, ForeignKey('entity_cards.id', ondelete='CASCADE'), nullable=False)
    
    # Usage context
    agent_name = Column(String(100), nullable=True)  # Which agent used the card
    session_id = Column(String(255), nullable=True)  # Session identifier
    query_text = Column(Text, nullable=True)  # The query that triggered the usage
    
    # Usage metadata
    usage_type = Column(String(50), nullable=False, default='prompt_injection')  # Type of usage
    confidence_threshold = Column(Float, nullable=True)  # Confidence threshold used
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    entity_card = relationship("EntityCard")
    
    __table_args__ = (
        Index('ix_entity_card_usage_entity_card_id', 'entity_card_id'),
        Index('ix_entity_card_usage_agent_name', 'agent_name'),
        Index('ix_entity_card_usage_session_id', 'session_id'),
        Index('ix_entity_card_usage_created_at', 'created_at'),
    )


class EntityCardIndex(Base):
    """
    Search index for entity cards to enable fast lookup by aliases and variations
    """
    __tablename__ = 'entity_card_index'
    
    # Primary key (SQLite: UUID as TEXT)
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to entity card
    entity_card_id = Column(String, ForeignKey('entity_cards.id', ondelete='CASCADE'), nullable=False)
    
    # Index terms
    index_term = Column(String(255), nullable=False)  # The term to index (alias, variation, etc.)
    term_type = Column(String(50), nullable=False)  # 'alias', 'variation', 'normalized', etc.
    term_priority = Column(Float, default=1.0, nullable=False)  # Priority for matching
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    # Relationship
    entity_card = relationship("EntityCard")
    
    __table_args__ = (
        # Unique constraint to prevent duplicate index terms for same entity
        UniqueConstraint('entity_card_id', 'index_term', name='uq_entity_card_index_term'),
        
        # Indexes for efficient lookup
        Index('ix_entity_card_index_term', 'index_term'),
        Index('ix_entity_card_index_term_type', 'term_type'),
        Index('ix_entity_card_index_priority', 'term_priority'),
    )


# Database management functions
def check_entity_cards_db_exists():
    """Check if entity cards tables exist"""
    from sqlalchemy import inspect
    session = get_session()
    engine = session.bind
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    session.close()
    
    required_tables = ['entity_cards', 'entity_card_usage', 'entity_card_index']
    existing_required_tables = [table for table in required_tables if table in existing_tables]
    
    return {
        'exists': len(existing_required_tables) == len(required_tables),
        'existing_tables': existing_required_tables,
        'missing_tables': [table for table in required_tables if table not in existing_tables]
    }


def initialize_entity_cards_db(force_test_db=False):
    """Initialize entity cards tables."""
    try:
        print("Creating entity cards tables...")
        
        # Use get_session to get the correct engine
        from app.models.base import get_session
        session = get_session(force_test_db=force_test_db)
        engine = session.bind
        
        # Create tables directly
        Base.metadata.create_all(engine, checkfirst=True)
        session.close()
        
        print("Entity cards tables initialized successfully.")
        
    except Exception as e:
        if "already exists" in str(e) or "DuplicateTable" in str(e):
            print("Entity cards tables already exist. Skipping creation.")
        else:
            print(f"Error initializing entity cards tables: {e}")
            raise


def drop_entity_cards_db():
    """Drop all entity cards tables."""
    session = get_session()
    engine = session.bind
    Base.metadata.drop_all(engine, tables=[
        EntityCardUsage.__table__, 
        EntityCardIndex.__table__, 
        EntityCard.__table__,
    ], checkfirst=True)
    session.close()
    print("Entity cards tables dropped successfully.")


def reset_entity_cards_db():
    """Drop and recreate all entity cards tables."""
    print("Resetting entity cards database...")
    drop_entity_cards_db()
    initialize_entity_cards_db()
    print("Entity cards database reset completed.")


# Helper functions for entity card operations
def create_entity_card(session, entity_name, entity_type, summary, **kwargs):
    """
    Create a new entity card
    """
    entity_card = EntityCard(
        entity_name=entity_name,
        entity_type=entity_type,
        summary=summary,
        **kwargs
    )
    session.add(entity_card)
    return entity_card


def get_entity_card_by_name(session, entity_name):
    """
    Get entity card by entity name
    """
    return session.query(EntityCard).filter(
        EntityCard.entity_name == entity_name,
        EntityCard.is_active == True
    ).first()


def search_entity_cards(session, search_term, limit=10):
    """
    Search entity cards by name, aliases, or content
    """
    from sqlalchemy import or_, func, String
    
    return session.query(EntityCard).filter(
        EntityCard.is_active == True,
        or_(
            EntityCard.entity_name.ilike(f'%{search_term}%'),
            # SQLite: cast JSON to string for searching
            func.cast(EntityCard.aliases, String).ilike(f'%{search_term}%'),
            func.cast(EntityCard.original_aliases, String).ilike(f'%{search_term}%'),
            EntityCard.summary.ilike(f'%{search_term}%'),
            EntityCard.original_description.ilike(f'%{search_term}%')
        )
    ).limit(limit).all()


def update_entity_card_usage(session, entity_card_id, agent_name=None, session_id=None, query_text=None):
    """
    Update usage statistics for an entity card
    """
    # Update the entity card usage count and last used time
    entity_card = session.query(EntityCard).filter(EntityCard.id == entity_card_id).first()
    if entity_card:
        entity_card.usage_count += 1
        entity_card.last_used = datetime.now(timezone.utc)
    
    # Create usage record
    usage = EntityCardUsage(
        entity_card_id=entity_card_id,
        agent_name=agent_name,
        session_id=session_id,
        query_text=query_text
    )
    session.add(usage)
    return usage


def get_entity_cards_by_type(session, entity_type, limit=50):
    """
    Get entity cards by type
    """
    return session.query(EntityCard).filter(
        EntityCard.entity_type == entity_type,
        EntityCard.is_active == True
    ).order_by(EntityCard.usage_count.desc()).limit(limit).all()


def get_most_used_entity_cards(session, limit=20):
    """
    Get most frequently used entity cards
    """
    return session.query(EntityCard).filter(
        EntityCard.is_active == True
    ).order_by(EntityCard.usage_count.desc()).limit(limit).all()


def deactivate_entity_card(session, entity_name):
    """
    Deactivate an entity card (soft delete)
    """
    entity_card = get_entity_card_by_name(session, entity_name)
    if entity_card:
        entity_card.is_active = False
        return True
    return False


def get_entity_card_stats(session):
    """
    Get statistics about entity cards
    """
    total_cards = session.query(EntityCard).count()
    active_cards = session.query(EntityCard).filter(EntityCard.is_active == True).count()
    total_usage = session.query(func.sum(EntityCard.usage_count)).scalar() or 0
    
    # Get usage by type
    type_stats = session.query(
        EntityCard.entity_type,
        func.count(EntityCard.id).label('count'),
        func.sum(EntityCard.usage_count).label('total_usage')
    ).filter(EntityCard.is_active == True).group_by(EntityCard.entity_type).all()
    
    return {
        'total_cards': total_cards,
        'active_cards': active_cards,
        'total_usage': total_usage,
        'type_stats': [
            {
                'entity_type': stat.entity_type,
                'count': stat.count,
                'total_usage': stat.total_usage or 0
            }
            for stat in type_stats
        ]
    }


import json

def get_entity_card_for_prompt_injection(session, entity_name):
    """
    Return a formatted string for prompt injection.
    Includes original description, summary, key facts, relationships, aliases, and ALL metadata.
    """
    entity_card = get_entity_card_by_name(session, entity_name)
    if not entity_card:
        return ""

    # Helper function to ensure lists are deserialized
    def ensure_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except:
                return []
        return []

    parts = []
    parts.append(f"ENTITY CARD: {entity_card.entity_name}")
    parts.append(f"Type: {entity_card.entity_type}")
    parts.append("")

    # Original description
    parts.append("Original Description:")
    parts.append(entity_card.original_description or "No original description available")
    parts.append("")

    # Generated summary
    parts.append("Generated Summary:")
    parts.append(entity_card.summary or "")
    parts.append("")

    # Key facts - ensure proper deserialization
    key_facts = ensure_list(entity_card.key_facts)
    if key_facts:
        parts.append("Key Facts:")
        for fact in key_facts:
            parts.append(f"• {fact}")
        parts.append("")

    # Relationships - ensure proper deserialization
    relationships = ensure_list(entity_card.relationships)
    if relationships:
        parts.append("Key Relationships:")
        for rel in relationships:
            parts.append(f"• {rel}")
        parts.append("")

    # Aliases - ensure proper deserialization
    original_aliases = ensure_list(entity_card.original_aliases)
    if original_aliases:
        parts.append(f"Original Aliases: {', '.join(original_aliases)}")
    
    aliases = ensure_list(entity_card.aliases)
    if aliases:
        parts.append(f"Processed Aliases: {', '.join(aliases)}")

    # Metadata: accept stringified JSON, list of {key,value}, or dict
    meta_raw = getattr(entity_card, "card_metadata", None)
    meta_pairs = []
    meta_dict = {}

    if isinstance(meta_raw, str):
        try:
            loaded = json.loads(meta_raw)
        except Exception:
            loaded = []
        if isinstance(loaded, dict):
            meta_dict = {str(k): loaded[k] for k in loaded.keys()}
        elif isinstance(loaded, list):
            meta_pairs = loaded
    elif isinstance(meta_raw, dict):
        meta_dict = {str(k): meta_raw[k] for k in meta_raw.keys()}
    elif isinstance(meta_raw, list):
        meta_pairs = meta_raw

    if meta_pairs:
        for item in meta_pairs:
            if isinstance(item, dict) and "key" in item:
                meta_dict[str(item.get("key"))] = item.get("value")

    if meta_dict:
        parts.append("")
        parts.append("Metadata:")
        for k in sorted(meta_dict.keys(), key=lambda s: s.lower()):
            parts.append(f"• {k}: {meta_dict[k]}")

    return "\n".join(parts).strip()


def extract_entity_field(entity_card, field_name):
    """
    Extract a specific field from an entity card for granular injection.
    
    Args:
        entity_card: EntityCard instance
        field_name: One of: 'summary', 'key_facts', 'relationships', 'description', 
                   'aliases', 'original_aliases', 'metadata', 'all'
    
    Returns:
        Formatted string for the requested field, or empty string if field doesn't exist
    """
    if not entity_card:
        return ""
    
    if field_name == "summary":
        return entity_card.summary or ""
    
    elif field_name == "key_facts":
        key_facts = entity_card.key_facts or []
        if key_facts:
            return "\n".join(f"• {fact}" for fact in key_facts)
        return ""
    
    elif field_name == "relationships":
        relationships = entity_card.relationships or []
        if relationships:
            return "\n".join(f"• {rel}" for rel in relationships)
        return ""
    
    elif field_name == "description":
        return entity_card.original_description or ""
    
    elif field_name == "aliases":
        aliases = entity_card.aliases or []
        if aliases:
            return ", ".join(aliases)
        return ""
    
    elif field_name == "original_aliases":
        original_aliases = entity_card.original_aliases or []
        if original_aliases:
            return ", ".join(original_aliases)
        return ""
    
    elif field_name == "metadata":
        meta_raw = getattr(entity_card, "card_metadata", None)
        
        # Check if metadata exists and is not empty
        if not meta_raw:
            return ""
        if isinstance(meta_raw, dict) and len(meta_raw) == 0:
            return ""
        if isinstance(meta_raw, list) and len(meta_raw) == 0:
            return ""
        if isinstance(meta_raw, str) and (not meta_raw.strip() or meta_raw.strip() == "[]" or meta_raw.strip() == "{}"):
            return ""
        
        meta_dict = {}
        
        # Handle string (JSON stored as string in database)
        if isinstance(meta_raw, str):
            try:
                loaded = json.loads(meta_raw)
                # After parsing, treat it as the parsed type (dict or list)
                meta_raw = loaded
            except Exception:
                # If parsing fails, it's not valid JSON, return empty
                return ""
        
        # Now meta_raw should be either dict or list (or already was)
        if isinstance(meta_raw, dict):
            if len(meta_raw) > 0:
                meta_dict = {str(k): meta_raw[k] for k in meta_raw.keys()}
        elif isinstance(meta_raw, list):
            # Handle list of MetaItem objects (from agent_form)
            # Format: [{"key": "key1", "value": "value1"}, ...]
            for item in meta_raw:
                if isinstance(item, dict):
                    # Check for both formats: {"key": ..., "value": ...} and direct key-value pairs
                    if "key" in item:
                        meta_dict[str(item.get("key"))] = item.get("value")
                    else:
                        # If it's a dict without "key", treat all keys as metadata
                        for k, v in item.items():
                            meta_dict[str(k)] = v
        
        if meta_dict and len(meta_dict) > 0:
            # Format as bullet points
            formatted = "\n".join(f"• {k}: {v}" for k, v in sorted(meta_dict.items(), key=lambda x: x[0].lower()))
            return formatted
        return ""
    
    elif field_name == "all":
        # Return full card (backward compatibility)
        session = get_session()
        try:
            return get_entity_card_for_prompt_injection(session, entity_card.entity_name)
        finally:
            session.close()
    
    elif field_name == "type":
        return entity_card.entity_type or ""
    
    else:
        # Unknown field name
        return ""


def get_entity_field_for_injection(session, entity_name, field_name):
    """
    Get a specific field from an entity card by entity name.
    
    Args:
        session: Database session
        entity_name: Name of the entity
        field_name: Field to extract (see extract_entity_field for options)
    
    Returns:
        Formatted string for the requested field, or empty string if not found
    """
    entity_card = get_entity_card_by_name(session, entity_name)
    if not entity_card:
        return ""
    
    return extract_entity_field(entity_card, field_name)


class EntityCardRunLog(Base):
    """
    Track entity card generation runs for incremental processing
    """
    __tablename__ = 'entity_card_run_log'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Run information
    last_run_time = Column(DateTime(timezone=True), nullable=False)
    nodes_processed = Column(Integer, nullable=False)
    nodes_updated = Column(Integer, nullable=False)  # How many entity cards were actually updated
    run_duration_seconds = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_entity_card_run_log_last_run_time', 'last_run_time'),
        Index('ix_entity_card_run_log_created_at', 'created_at'),
    )


def get_last_entity_card_run_time(session):
    """
    Get the timestamp of the last entity card generation run
    """
    last_run = session.query(EntityCardRunLog).order_by(EntityCardRunLog.created_at.desc()).first()
    return last_run.last_run_time if last_run else None


def log_entity_card_run(session, last_run_time, nodes_processed, nodes_updated, run_duration_seconds=None):
    """
    Log an entity card generation run
    """
    run_log = EntityCardRunLog(
        last_run_time=last_run_time,
        nodes_processed=nodes_processed,
        nodes_updated=nodes_updated,
        run_duration_seconds=run_duration_seconds
    )
    session.add(run_log)
    session.commit()
    return run_log


class DescriptionRunLog(Base):
    """
    Track description creation runs for incremental processing
    """
    __tablename__ = 'description_run_log'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    last_run_time = Column(DateTime(timezone=True), nullable=False)
    nodes_processed = Column(Integer, nullable=False)
    nodes_updated = Column(Integer, nullable=False)
    run_duration_seconds = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_description_run_log_last_run_time', 'last_run_time'),
        Index('ix_description_run_log_created_at', 'created_at'),
    )


def get_last_description_run_time(session):
    """
    Get the timestamp of the last description creation run
    """
    last_run = session.query(DescriptionRunLog).order_by(DescriptionRunLog.last_run_time.desc()).first()
    return last_run.last_run_time if last_run else None

def log_description_run(session, last_run_time, nodes_processed, nodes_updated, run_duration_seconds=None):
    """
    Log a description creation run
    """
    run_log = DescriptionRunLog(
        last_run_time=last_run_time,
        nodes_processed=nodes_processed,
        nodes_updated=nodes_updated,
        run_duration_seconds=run_duration_seconds
    )
    session.add(run_log)
    session.commit()
    return run_log

def get_nodes_updated_since(session, since_timestamp):
    """
    Get nodes that have been updated since the given timestamp
    """
    from app.assistant.kg_core.knowledge_graph_db import Node
    return session.query(Node).filter(Node.updated_at > since_timestamp).all()
