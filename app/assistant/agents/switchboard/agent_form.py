from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class TaggedChunk(BaseModel):
    """A self-contained chunk extracted from the conversation window."""
    
    category: Optional[str] = Field(
        default=None,
        description="Category: 'preference' or 'state', or null if not applicable"
    )
    
    extracted_summary: str = Field(
        description="Self-contained summary of the preference/fact (should make sense without context)"
    )
    
    tags: List[str] = Field(
        default_factory=list,
        description="List of topic tags (e.g., ['food', 'routine']). Max 2 tags for routing to downstream agents."
    )
    
    source_message_ids: List[str] = Field(
        default_factory=list,
        description="List of message IDs from the conversation window that this fact was extracted from"
    )
    
    confidence: float = Field(
        default=0.8,
        description="Confidence in the extraction (0.0 to 1.0)"
    )
    
    @field_validator('category', mode='before')
    @classmethod
    def normalize_category(cls, v):
        """Convert string 'null', 'None', or empty string to Python None."""
        if v in ('null', 'None', '', 'none'):
            return None
        return v


class AgentForm(BaseModel):
    """
    Switchboard output: A list of tagged chunks extracted from the conversation window.
    """
    
    tagged_chunks: List[TaggedChunk] = Field(
        default_factory=list,
        description="List of extracted preference/fact chunks. Empty list if none found."
    )
    
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation of what was considered and why chunks were extracted or rejected (for debugging)"
    )
