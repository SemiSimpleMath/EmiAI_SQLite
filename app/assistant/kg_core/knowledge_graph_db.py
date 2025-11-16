# knowledge_graph_db.py
# SQLite-compatible version (embeddings now stored in ChromaDB)

import uuid
import os
from sqlalchemy import (
    Column, String, JSON, DateTime, Text, ForeignKey, Float,
    UniqueConstraint, Index, func, Enum
)
from sqlalchemy.orm import relationship

from app.models.base import Base, get_session

# --- Node Type ENUM ---
# Fixed ontology: Entity, Event, State, Goal, Concept, Property
NODE_TYPE_ENUM = Enum('Entity', 'Event', 'State', 'Goal', 'Concept', 'Property', name='node_type_enum')

# --- Message ID to Source Mapping Table ---
class MessageSourceMapping(Base):
    __tablename__ = 'message_source_mapping'
    message_id = Column(String, primary_key=True)  # The message ID
    source_table = Column(String, nullable=False)  # Which table it came from (unified_log, processed_entity_log, etc.)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    __table_args__ = (
        Index('ix_message_source_mapping_source_table', 'source_table'),
    )


# --- Universal Node Table (Revised) ---
class Node(Base):
    __tablename__ = 'nodes'
    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    label         = Column(String, nullable=False)
    node_type     = Column(NODE_TYPE_ENUM, nullable=False)
    

    # --- ADDED: Dedicated columns for core, searchable fields ---
    description   = Column(Text, nullable=True)
    aliases       = Column(JSON, nullable=True)  # SQLite: JSON array instead of ARRAY(String)
    category      = Column(String, nullable=True)  # For better filtering: Person, Place, Organization, etc.

    # Miscellaneous data remains in this flexible JSON column
    attributes    = Column(JSON, nullable=False, default=dict)

    # --- REMOVED: Context and sentence fields - these belong on edges, not nodes ---
    
    # --- ADDED: Message tracking and provenance ---
    original_message_id = Column(String, nullable=True)  # ID of the original message that first created this node (immutable)
    original_sentence = Column(Text, nullable=True)  # The sentence that first created this node (immutable provenance)
    sentence_id = Column(String, nullable=True)  # ID of the most recent sentence that updated this node (changes with merges)

    # Timestamps for validity and tracking
    start_date    = Column(DateTime(timezone=True), nullable=True)
    end_date      = Column(DateTime(timezone=True), nullable=True)
    start_date_confidence = Column(String, nullable=True)  # "confirmed", "estimated", "inferred"
    end_date_confidence   = Column(String, nullable=True)  # "confirmed", "estimated", "inferred"
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- ADDED: Promoted fields from attributes ---
    valid_during  = Column(Text, nullable=True)
    hash_tags     = Column(JSON, nullable=True)  # SQLite: JSON array instead of ARRAY(String)
    semantic_label = Column(String, nullable=True)
    goal_status   = Column(String, nullable=True)
    
    # NOTE: Embeddings now stored in ChromaDB, not in database
    
    # --- ADDED: New first-class fields ---
    confidence = Column(Float, nullable=True)  # Confidence score (0.0 to 1.0)
    importance = Column(Float, nullable=True)  # Importance score (0.0 to 1.0)
    source = Column(String, nullable=True)  # Source of the information

    # ORM relationships
    outgoing_edges = relationship("Edge", back_populates="source_node", foreign_keys="Edge.source_id")
    incoming_edges = relationship("Edge", back_populates="target_node", foreign_keys="Edge.target_id")

    __table_args__ = (
        Index('ix_nodes_label', 'label'),
        Index('ix_nodes_node_type', 'node_type'),
        Index('ix_nodes_category', 'category'),  # For efficient category filtering
        # --- ADDED: Indexes for promoted fields ---
        Index('ix_nodes_start_date', 'start_date'),
        Index('ix_nodes_end_date', 'end_date'),
        Index('ix_nodes_start_date_confidence', 'start_date_confidence'),
        Index('ix_nodes_end_date_confidence', 'end_date_confidence'),
        Index('ix_nodes_valid_during', 'valid_during'),
        Index('ix_nodes_semantic_label', 'semantic_label'),
        Index('ix_nodes_goal_status', 'goal_status'),
        Index('ix_nodes_confidence', 'confidence'),
        Index('ix_nodes_importance', 'importance'),
        Index('ix_nodes_source', 'source'),
        # --- ADDED: Indexes for message tracking and provenance ---
        Index('ix_nodes_original_message_id', 'original_message_id'),
        Index('ix_nodes_original_sentence', 'original_sentence'),
        Index('ix_nodes_sentence_id', 'sentence_id'),
        # NOTE: JSON fields (aliases, hash_tags, attributes) and embeddings not indexed in SQLite
    )

# --- Universal Edge Table ---
class Edge(Base):
    __tablename__ = 'edges'
    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id     = Column(String, ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    target_id     = Column(String, ForeignKey('nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_type = Column(String, nullable=False)
    relationship_descriptor = Column(String, nullable=True)  # More specific semantic description (e.g., "is_married", "works_for", "lives_in")
    attributes    = Column(JSON, nullable=False, default=dict)
    
    # --- ADDED: Message tracking ---
    original_message_id = Column(String, nullable=True)  # ID of the original message that first created this edge (never changes)
    sentence_id = Column(String, nullable=True)  # ID of the most recent sentence that updated this edge (changes with merges)
    
    # --- ADDED: Top-level sentence field for easy access ---
    sentence = Column(Text, nullable=True)  # Extracted sentence from attributes for easy querying

    original_message_timestamp = Column(DateTime(timezone=True), nullable=True)  # When the original message was recorded
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # NOTE: Embeddings now stored in ChromaDB, not in database
    
    # --- ADDED: New first-class fields ---
    confidence = Column(Float, nullable=True)  # Confidence score (0.0 to 1.0)
    importance = Column(Float, nullable=True)  # Importance score (0.0 to 1.0)
    source = Column(String, nullable=True)  # Source of the information
    source_node   = relationship("Node", back_populates="outgoing_edges", foreign_keys=[source_id])
    target_node   = relationship("Node", back_populates="incoming_edges", foreign_keys=[target_id])

    __table_args__ = (
        UniqueConstraint('source_id', 'target_id', 'relationship_type', name='uq_edge_unique'),
        Index('ix_edges_sentence', 'sentence'),  # For efficient sentence searching
        Index('ix_edges_original_message_timestamp', 'original_message_timestamp'),
        Index('ix_edges_confidence', 'confidence'),
        Index('ix_edges_importance', 'importance'),
        Index('ix_edges_source', 'source'),
        # --- ADDED: Indexes for message tracking ---
        Index('ix_edges_original_message_id', 'original_message_id'),
        Index('ix_edges_sentence_id', 'sentence_id'),
        # --- ADDED: Index for relationship descriptor ---
        Index('ix_edges_relationship_descriptor', 'relationship_descriptor'),
        # NOTE: JSON fields (attributes) and embeddings not indexed in SQLite
    )

# --- Database Management Functions ---
def initialize_knowledge_graph_db():
    """Initialize knowledge graph tables."""
    session = get_session()
    engine = session.bind
    print(f"🔍 KG DB Debug: Connecting to database: {engine.url}")
    Base.metadata.create_all(engine, checkfirst=True)
    session.close()
    print("Knowledge graph tables initialized successfully.")
    print("💡 Tip: Run 'python -m app.assistant.kg_core.seed_core_nodes' to seed Jukka and Emi nodes.")

def drop_knowledge_graph_db():
    """Drop all knowledge graph tables."""
    session = get_session()
    engine = session.bind
    Base.metadata.drop_all(engine, tables=[
        Edge.__table__, Node.__table__, MessageSourceMapping.__table__,
    ], checkfirst=True)
    # SQLite: ENUM types are handled differently, no need to drop separately
    session.close()
    print("Knowledge graph tables dropped successfully.")

def reset_knowledge_graph_db():
    """Drop and recreate all knowledge graph tables."""
    print("Resetting knowledge graph database...")
    drop_knowledge_graph_db()
    initialize_knowledge_graph_db()
    print("Knowledge graph database reset completed.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "drop":
            drop_knowledge_graph_db()
        elif command == "reset":
            reset_knowledge_graph_db()
        elif command == "init":
            initialize_knowledge_graph_db()
        else:
            print("Usage: python knowledge_graph_db.py [init|drop|reset]")
    else:
        initialize_knowledge_graph_db()