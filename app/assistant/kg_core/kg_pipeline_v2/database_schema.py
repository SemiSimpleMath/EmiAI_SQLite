"""
Database Schema for KG Pipeline V2 - Independent Stage Processing
SQLite Compatible Version

This schema supports:
1. Complete node and edge data storage
2. Stage-by-stage processing with intermediate results
3. Provenance tracking through all stages
4. Fault tolerance and recovery
5. Parallel processing readiness
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

# Use shared Base from app.models.base
from app.models.base import Base

# Helper to generate string UUIDs for SQLite
def generate_uuid():
    return str(uuid.uuid4())


class PipelineBatch(Base):
    """Organize processing into batches for better management"""
    __tablename__ = 'pipeline_batches'
    
    id = Column(Integer, primary_key=True)
    batch_name = Column(String(100), nullable=False)
    status = Column(String(20), default='pending')  # pending, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    total_nodes = Column(Integer, default=0)
    processed_nodes = Column(Integer, default=0)
    failed_nodes = Column(Integer, default=0)
    batch_metadata = Column(JSON)  # Additional batch metadata


class PipelineChunk(Base):
    """
    A chunk of data flowing through the pipeline stages.
    
    Represents a unit of processing (e.g., one conversation). The chunk contains
    multiple nodes/edges stored as JSON in stage_results. This is NOT a KG node.
    """
    __tablename__ = 'pipeline_chunks'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    batch_id = Column(Integer, ForeignKey('pipeline_batches.id'))
    
    # Chunk metadata (human-readable label for this processing unit)
    label = Column(String(255), nullable=False)  # e.g., "Conversation 2025-10-17"
    node_type = Column(String(50), nullable=False)  # e.g., "ConversationChunk", "MetadataResult"
    original_sentence = Column(Text)  # Summary or first sentence
    
    # Provenance data
    conversation_id = Column(String(100))
    message_id = Column(String(100))
    data_source = Column(String(50))
    original_timestamp = Column(DateTime)
    
    # Processing metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    batch = relationship("PipelineBatch", back_populates="chunks")
    stage_results = relationship("StageResult", back_populates="chunk")
    outgoing_edges = relationship("PipelineEdge", foreign_keys="PipelineEdge.source_chunk_id", back_populates="source_chunk")
    incoming_edges = relationship("PipelineEdge", foreign_keys="PipelineEdge.target_chunk_id", back_populates="target_chunk")


class PipelineEdge(Base):
    """Edge data for processing through all stages"""
    __tablename__ = 'pipeline_edges'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    batch_id = Column(Integer, ForeignKey('pipeline_batches.id'))
    
    # Edge data
    source_chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'))  # SQLite: UUID as TEXT
    target_chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'))  # SQLite: UUID as TEXT
    edge_type = Column(String(100))
    original_sentence = Column(Text)
    
    # Provenance data
    conversation_id = Column(String(100))
    message_id = Column(String(100))
    
    # Processing metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    batch = relationship("PipelineBatch", back_populates="edges")
    source_chunk = relationship("PipelineChunk", foreign_keys=[source_chunk_id], back_populates="outgoing_edges")
    target_chunk = relationship("PipelineChunk", foreign_keys=[target_chunk_id], back_populates="incoming_edges")


class StageResult(Base):
    """
    Store intermediate results from each processing stage.
    
    This is the 'waiting area' between stages. Each chunk's data (containing multiple nodes/edges)
    is stored here as JSON for the next stage to process.
    """
    __tablename__ = 'stage_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    stage_name = Column(String(50), nullable=False)  # conversation_boundary, parser, fact_extraction, metadata, merge
    
    # Stage-specific result data (contains multiple nodes/edges as JSON)
    result_data = Column(JSON, nullable=False)
    
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
    by resetting the status back to 'pending'.
    """
    __tablename__ = 'stage_completion'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    stage_name = Column(String(50), nullable=False)
    
    # Status tracking
    status = Column(String(20), default='pending')  # pending, processing, completed, failed
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    
    # Relationships
    chunk = relationship("PipelineChunk")


# Stage-specific result tables for better organization

class FactExtractionResult(Base):
    """Detailed fact extraction results"""
    __tablename__ = 'fact_extraction_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    
    # Fact extraction specific data
    facts = Column(JSON)  # List of extracted facts
    confidence_scores = Column(JSON)  # Confidence for each fact
    extraction_metadata = Column(JSON)  # Additional extraction info
    
    created_at = Column(DateTime, default=datetime.utcnow)


class ParserResult(Base):
    """Detailed parser results"""
    __tablename__ = 'parser_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    
    # Parser specific data
    parsed_entities = Column(JSON)  # List of parsed entities
    parsed_relationships = Column(JSON)  # List of parsed relationships
    sentence_analysis = Column(JSON)  # Sentence-level analysis
    parser_metadata = Column(JSON)  # Additional parser info
    
    created_at = Column(DateTime, default=datetime.utcnow)


class MetadataResult(Base):
    """Detailed metadata enrichment results"""
    __tablename__ = 'metadata_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    
    # Metadata specific data
    enriched_metadata = Column(JSON)  # Enriched node metadata
    category = Column(String(100))  # Extracted category
    confidence = Column(Float)  # Metadata confidence
    metadata_source = Column(String(50))  # Source of metadata
    
    created_at = Column(DateTime, default=datetime.utcnow)


class MergeResult(Base):
    """Detailed merge results"""
    __tablename__ = 'merge_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    
    # Merge specific data
    merged_data = Column(JSON)  # Final merged node data
    merge_operations = Column(JSON)  # What merge operations were performed
    conflicts_resolved = Column(JSON)  # Any conflicts that were resolved
    merge_metadata = Column(JSON)  # Additional merge info
    
    created_at = Column(DateTime, default=datetime.utcnow)


class TaxonomyResult(Base):
    """Detailed taxonomy classification results"""
    __tablename__ = 'taxonomy_results'
    
    id = Column(Text, primary_key=True, default=generate_uuid)  # SQLite: UUID as TEXT
    chunk_id = Column(Text, ForeignKey('pipeline_chunks.id'), nullable=False)  # SQLite: UUID as TEXT
    
    # Taxonomy specific data
    taxonomy_path = Column(String(500))  # Full taxonomy path
    taxonomy_id = Column(Integer)  # Final taxonomy ID
    confidence = Column(Float)  # Classification confidence
    classification_source = Column(String(50))  # How it was classified
    taxonomy_metadata = Column(JSON)  # Additional taxonomy info
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Add relationships to PipelineBatch
PipelineBatch.chunks = relationship("PipelineChunk", back_populates="batch")
PipelineBatch.edges = relationship("PipelineEdge", back_populates="batch")
