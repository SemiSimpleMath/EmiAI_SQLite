"""
Refactored Database Schema for KG Pipeline V2

This schema properly separates:
1. Chunks (units of data flowing through the pipeline)
2. Stage results (waiting areas between stages)
3. Stage completion tracking (which chunks have been processed)

The pipeline does NOT store actual KG nodes/edges - those only exist in the 
final nodes/edges tables after the merge stage.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base
from datetime import datetime
import uuid


class PipelineBatch(Base):
    """Group of chunks processed together"""
    __tablename__ = 'pipeline_batches'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_name = Column(String(255), nullable=False)
    status = Column(String(50), default='pending')  # pending, processing, completed, failed
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Metadata
    batch_metadata = Column(JSON)  # Additional batch metadata
    
    # Relationships
    chunks = relationship("PipelineChunk", back_populates="batch")


class PipelineChunk(Base):
    """
    A chunk of data flowing through the pipeline.
    
    This represents a unit of processing (e.g., one conversation, one set of messages).
    It does NOT store actual KG nodes - just metadata about the chunk.
    """
    __tablename__ = 'pipeline_chunks'
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    batch_id = Column(Integer, ForeignKey('pipeline_batches.id'))
    
    # Chunk metadata (NOT KG node data)
    chunk_label = Column(String(255))  # Human-readable label (e.g., "Conversation 2025-10-17")
    chunk_type = Column(String(50))  # Type of chunk (e.g., "conversation", "document")
    
    # Source provenance
    source = Column(String(50))  # Where this chunk came from (e.g., "chat", "slack")
    source_id = Column(String(255))  # Original ID from source system
    original_timestamp = Column(DateTime)  # When the original data was created
    
    # Processing metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    batch = relationship("PipelineBatch", back_populates="chunks")
    stage_results = relationship("StageResult", back_populates="chunk")
    stage_completions = relationship("StageCompletion", back_populates="chunk")


class StageResult(Base):
    """
    Store intermediate results from each processing stage.
    
    This is the "waiting area" between stages. Each stage reads from the previous
    stage's results and writes its own results here.
    """
    __tablename__ = 'stage_results'
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    chunk_id = Column(UUID, ForeignKey('pipeline_chunks.id'), nullable=False)
    stage_name = Column(String(50), nullable=False)  # conversation_boundary, parser, fact_extraction, metadata, merge
    
    # Stage-specific result data (stored as JSON)
    result_data = Column(JSONB, nullable=False)
    
    # Processing metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_time = Column(Float)  # seconds
    agent_version = Column(String(50))  # Track which agent version was used
    
    # Relationships
    chunk = relationship("PipelineChunk", back_populates="stage_results")


class StageCompletion(Base):
    """
    Track which stages are complete for each chunk.
    
    This prevents reprocessing the same chunk and enables rerunning stages
    by resetting completion status.
    """
    __tablename__ = 'stage_completion'
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    chunk_id = Column(UUID, ForeignKey('pipeline_chunks.id'), nullable=False)
    stage_name = Column(String(50), nullable=False)
    
    # Status tracking
    status = Column(String(20), default='pending')  # pending, processing, completed, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Relationships
    chunk = relationship("PipelineChunk", back_populates="stage_completions")


# Note: We removed PipelineNode and PipelineEdge tables.
# Actual KG nodes and edges are stored in the main nodes/edges tables
# (defined in knowledge_graph_db.py) after the merge stage.
# The pipeline should NOT duplicate this data structure.

