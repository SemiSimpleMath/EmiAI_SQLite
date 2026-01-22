"""
KG Pipeline V2 - Continuous Processing Pipeline

This module provides continuous processing for the knowledge graph pipeline.
Each stage runs independently and continuously, waiting for upstream data.

Key Features:
- Continuous processing (stages run indefinitely)
- Automatic data flow (stages wait for upstream data)
- Parallel processing (all stages run simultaneously)
- Fault tolerance and recovery
- Thread-safe operations

Usage:
    # Option A: Start all stages at once
    python app/assistant/kg_core/kg_pipeline_v2/start_all_stages.py
    
    # Option B: Start each stage separately
    python app/assistant/kg_core/kg_pipeline_v2/stages/conversation_boundary.py
    python app/assistant/kg_core/kg_pipeline_v2/stages/parser.py
    python app/assistant/kg_core/kg_pipeline_v2/stages/fact_extraction.py
    python app/assistant/kg_core/kg_pipeline_v2/stages/metadata.py
    python app/assistant/kg_core/kg_pipeline_v2/stages/merge.py

NOTE: Stage processors are imported lazily to avoid SQLAlchemy table conflicts.
Import them directly from their modules when needed.
"""

from .pipeline_coordinator import PipelineCoordinator
from .database_schema import (
    PipelineBatch, PipelineChunk, PipelineEdge, StageResult, StageCompletion,
    FactExtractionResult, ParserResult, MetadataResult, MergeResult, TaxonomyResult
)

# Stage processors are available via lazy import from .stages
# Example: from app.assistant.kg_core.kg_pipeline_v2.stages import MergeProcessor

__all__ = [
    'PipelineCoordinator',
    'PipelineBatch', 'PipelineChunk', 'PipelineEdge', 'StageResult', 'StageCompletion',
    'FactExtractionResult', 'ParserResult', 'MetadataResult', 'MergeResult', 'TaxonomyResult'
]
