"""
KG Batch Processing Module

High-performance parallel and batch processing for knowledge graph ingestion.
"""

from .kg_batch_process import KGBatchProcessor, ProcessingConfig, ConversationChunk, ProcessingResult

__all__ = [
    'KGBatchProcessor',
    'ProcessingConfig', 
    'ConversationChunk',
    'ProcessingResult'
]

