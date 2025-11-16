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
"""

from .pipeline_coordinator import PipelineCoordinator
from .stages import (
    ConversationBoundaryProcessor, FactExtractionProcessor, ParserProcessor, MetadataProcessor,
    MergeProcessor, TaxonomyProcessor
)
from .database_schema import (
    PipelineBatch, PipelineChunk, PipelineEdge, StageResult, StageCompletion,
    FactExtractionResult, ParserResult, MetadataResult, MergeResult, TaxonomyResult
)

__all__ = [
    'PipelineCoordinator',
    'ConversationBoundaryProcessor', 'FactExtractionProcessor', 'ParserProcessor', 'MetadataProcessor',
    'MergeProcessor', 'TaxonomyProcessor',
    'PipelineBatch', 'PipelineChunk', 'PipelineEdge', 'StageResult', 'StageCompletion',
    'FactExtractionResult', 'ParserResult', 'MetadataResult', 'MergeResult', 'TaxonomyResult'
]
