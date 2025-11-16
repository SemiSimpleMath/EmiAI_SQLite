# knowledge_graph_db_sqlite.py
# SQLite + ChromaDB compatible version of KG models

import uuid
from sqlalchemy import (
    Column, String, JSON, DateTime, Text, ForeignKey, Float,
    UniqueConstraint, Index, func
)
from sqlalchemy.orm import relationship
from app.models.base import Base

# --- Message ID to Source Mapping Table ---
class MessageSourceMapping(Base):
    __tablename__ = 'message_source_mapping'
    message_id = Column(String, primary_key=True)
    source_table = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    
    __table_args__ = (
        Index('ix_message_source_mapping_source_table', 'source_table'),
    )


# --- Universal Node Table (SQLite version) ---
class Node(Base):
    __tablename__ = 'kg_node_metadata'
    
    # Core fields
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    label = Column(String, nullable=False)
    node_type = Column(String, nullable=False)  # Entity, Event, State, Goal, Concept, Property
    
    # Searchable fields
    description = Column(Text, nullable=True)
    aliases = Column(JSON, nullable=True)  # Stored as JSON array in SQLite
    category = Column(String, nullable=True)
    
    # Flexible attributes
    attributes = Column(JSON, nullable=False, default=dict)
    
    # Message tracking and provenance
    original_message_id = Column(String, nullable=True)
    original_sentence = Column(Text, nullable=True)
    sentence_id = Column(String, nullable=True)
    
    # Timestamps
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    start_date_confidence = Column(String, nullable=True)
    end_date_confidence = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # Promoted fields
    valid_during = Column(Text, nullable=True)
    hash_tags = Column(JSON, nullable=True)  # Stored as JSON array in SQLite
    semantic_label = Column(String, nullable=True)
    goal_status = Column(String, nullable=True)
    
    # NOTE: Embeddings are stored in ChromaDB, not here
    
    # First-class fields
    confidence = Column(Float, nullable=True)
    importance = Column(Float, nullable=True)
    source = Column(String, nullable=True)
    
    # ORM relationships
    outgoing_edges = relationship("Edge", back_populates="source_node", foreign_keys="Edge.source_id")
    incoming_edges = relationship("Edge", back_populates="target_node", foreign_keys="Edge.target_id")
    
    __table_args__ = (
        Index('ix_kg_nodes_label', 'label'),
        Index('ix_kg_nodes_node_type', 'node_type'),
        Index('ix_kg_nodes_category', 'category'),
        Index('ix_kg_nodes_start_date', 'start_date'),
        Index('ix_kg_nodes_end_date', 'end_date'),
        Index('ix_kg_nodes_confidence', 'confidence'),
        Index('ix_kg_nodes_importance', 'importance'),
        Index('ix_kg_nodes_source', 'source'),
    )


# --- Universal Edge Table (SQLite version) ---
class Edge(Base):
    __tablename__ = 'kg_edge_metadata'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String, ForeignKey('kg_node_metadata.id', ondelete='CASCADE'), nullable=False, index=True)
    target_id = Column(String, ForeignKey('kg_node_metadata.id', ondelete='CASCADE'), nullable=False, index=True)
    relationship_type = Column(String, nullable=False)
    relationship_descriptor = Column(String, nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
    
    # Message tracking
    original_message_id = Column(String, nullable=True)
    sentence_id = Column(String, nullable=True)
    sentence = Column(Text, nullable=True)
    
    original_message_timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    
    # NOTE: Embeddings are stored in ChromaDB, not here
    
    # First-class fields
    confidence = Column(Float, nullable=True)
    importance = Column(Float, nullable=True)
    source = Column(String, nullable=True)
    
    # ORM relationships
    source_node = relationship("Node", back_populates="outgoing_edges", foreign_keys=[source_id])
    target_node = relationship("Node", back_populates="incoming_edges", foreign_keys=[target_id])
    
    __table_args__ = (
        UniqueConstraint('source_id', 'target_id', 'relationship_type', name='uq_edge_unique'),
        Index('ix_kg_edges_sentence', 'sentence'),
        Index('ix_kg_edges_original_message_timestamp', 'original_message_timestamp'),
        Index('ix_kg_edges_confidence', 'confidence'),
        Index('ix_kg_edges_importance', 'importance'),
        Index('ix_kg_edges_source', 'source'),
    )


# Node type constants for compatibility
NODE_TYPES = ['Entity', 'Event', 'State', 'Goal', 'Concept', 'Property']


# --- Database Management Functions ---
def initialize_knowledge_graph_db():
    """Initialize knowledge graph tables."""
    from app.models.base import get_session
    session = get_session()
    engine = session.bind
    print(f"🔍 KG DB Debug: Connecting to database: {engine.url}")
    Base.metadata.create_all(engine, checkfirst=True)
    session.close()
    print("Knowledge graph tables initialized successfully.")
    print("💡 Tip: Run 'python seed_core_nodes.py' to seed Jukka and Emi nodes.")


def drop_knowledge_graph_db():
    """Drop all knowledge graph tables."""
    from app.models.base import get_session
    session = get_session()
    engine = session.bind
    Base.metadata.drop_all(engine, tables=[
        Edge.__table__, Node.__table__, MessageSourceMapping.__table__,
    ], checkfirst=True)
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
            print("Usage: python knowledge_graph_db_sqlite.py [init|drop|reset]")
    else:
        initialize_knowledge_graph_db()
