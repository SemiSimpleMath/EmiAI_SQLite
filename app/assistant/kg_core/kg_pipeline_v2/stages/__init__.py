"""
Stage Processors for KG Pipeline V2

Individual stage processors that can be run independently.

NOTE: Imports are lazy to avoid circular dependencies and SQLAlchemy table conflicts.
Import the specific processor you need directly from its module.

Example:
    from app.assistant.kg_core.kg_pipeline_v2.stages.conversation_boundary import ConversationBoundaryProcessor
    from app.assistant.kg_core.kg_pipeline_v2.stages.parser import ParserProcessor
"""

# Lazy imports - only import when explicitly accessed
def __getattr__(name):
    """Lazy import of stage processors to avoid import chain issues."""
    if name == 'ConversationBoundaryProcessor':
        from .conversation_boundary import ConversationBoundaryProcessor
        return ConversationBoundaryProcessor
    elif name == 'FactExtractionProcessor':
        from .fact_extraction import FactExtractionProcessor
        return FactExtractionProcessor
    elif name == 'ParserProcessor':
        from .parser import ParserProcessor
        return ParserProcessor
    elif name == 'MetadataProcessor':
        from .metadata import MetadataProcessor
        return MetadataProcessor
    elif name == 'MergeProcessor':
        from .merge import MergeProcessor
        return MergeProcessor
    elif name == 'TaxonomyProcessor':
        from .taxonomy import TaxonomyProcessor
        return TaxonomyProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'ConversationBoundaryProcessor',
    'FactExtractionProcessor',
    'ParserProcessor', 
    'MetadataProcessor',
    'MergeProcessor',
    'TaxonomyProcessor'
]
