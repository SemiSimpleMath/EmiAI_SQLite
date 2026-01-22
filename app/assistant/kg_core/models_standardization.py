# ASCII only.
# SQLite version - uses JSON fields instead of specialized vector types

from sqlalchemy import Column, String, Integer, DateTime, Text, Boolean, func, JSON
from app.models.base import Base
import uuid

# Helper to generate string UUIDs for SQLite
def generate_uuid():
    return str(uuid.uuid4())

# Canonical label per node_type
class LabelCanon(Base):
    __tablename__ = "label_canon"
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    node_type = Column(String, index=True, nullable=False)
    canonical_label_titlecase = Column(String, nullable=False)
    lowercase_norm = Column(String, index=True, nullable=False)
    embedding = Column(JSON, nullable=True)  # SQLite: Store embedding as JSON array
    status = Column(String, default="active")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=True)

# Alias label pointing to a canonical
class LabelAlias(Base):
    __tablename__ = "label_alias"
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    node_type = Column(String, index=True, nullable=False)
    alias_text = Column(String, index=True, nullable=False)
    canon_id = Column(Text, index=True, nullable=False)  # SQLite: UUID as TEXT
    method = Column(String, nullable=False)
    confidence = Column(Integer, default=5)
    source = Column(String, nullable=True)
    example_context = Column(Text, nullable=True)
    agent_reasoning = Column(Text, nullable=True)
    usage_count = Column(Integer, default=0)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

# Canonical edge predicate per domain and range
class EdgeCanon(Base):
    __tablename__ = "edge_canon"
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    domain_type = Column(String, index=True, nullable=False)
    range_type = Column(String, index=True, nullable=False)
    edge_type = Column(String, index=True, nullable=False)
    edge_type_embedding = Column(JSON, nullable=True)  # SQLite: Store 384-dim vector as JSON array
    is_symmetric = Column(Boolean, default=False)
    status = Column(String, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String, nullable=True)

# Alias predicate pointing to a canonical predicate
class EdgeAlias(Base):
    __tablename__ = "edge_alias"
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    canon_id = Column(Text, index=True, nullable=False)  # SQLite: UUID as TEXT
    raw_text = Column(String, index=True, nullable=False)
    domain_type = Column(String, index=True, nullable=False)
    range_type = Column(String, index=True, nullable=False)
    method = Column(String, nullable=True)
    confidence = Column(Integer, nullable=True)
    provenance = Column(JSON, nullable=True)  # SQLite: JSONB → JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Review queue for mid-confidence or conflicts
class ReviewQueue(Base):
    __tablename__ = "review_queue"
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    item_type = Column(String, index=True, nullable=False)  # "label" or "edge"
    proposal_text = Column(String, nullable=False)
    bucket_json = Column(JSON, nullable=False)  # SQLite: JSONB → JSON
    candidates_json = Column(JSON, nullable=True)  # SQLite: JSONB → JSON
    scores_json = Column(JSON, nullable=True)  # SQLite: JSONB → JSON
    reason = Column(String, nullable=True)
    state = Column(String, default="open")  # open, decided
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_by = Column(String, nullable=True)
    decision = Column(String, nullable=True)
