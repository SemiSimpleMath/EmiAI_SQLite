"""
Taxonomy Lookup Agent Form

Finds the most relevant taxonomy paths based on a description.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class TaxonomyPath(BaseModel):
    """A single relevant taxonomy path."""
    
    path: str = Field(
        description="Full taxonomy path (e.g., 'entity > artifact > machine > robot')"
    )
    
    relevance_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Relevance score for this path (0.0-1.0)"
    )
    
    reasoning: str = Field(
        description="Brief explanation of why this path is relevant to the description"
    )


class AgentForm(BaseModel):
    """Output schema for taxonomy path lookup."""
    
    relevant_paths: List[TaxonomyPath] = Field(
        default=[],
        description="List of most relevant taxonomy paths, ordered by relevance score"
    )
