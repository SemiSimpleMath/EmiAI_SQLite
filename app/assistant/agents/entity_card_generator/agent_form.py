from typing import List, Union
from pydantic import BaseModel, Field, ConfigDict

class MetaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, description="Metadata key.")
    value: Union[str, float, int, bool] = Field(
        default=None, description="Scalar value for the key."
    )

class AgentForm(BaseModel):
    """
    Structured output form for entity card generation
    """
    model_config = ConfigDict(extra="forbid")

    should_create_card: bool = Field(
        ..., description="Whether this node should have an entity card created. Consider if the entity name would be useful for prompt injection - avoid generic terms like 'dad', 'mom', 'friend' that would create noise."
    )
    entity_name: str = Field(
        ..., min_length=1, max_length=255,
        description="Primary name of the entity. Match the original label when possible."
    )
    entity_type: str = Field(
        ..., min_length=1, max_length=100,
        description="Type of the entity (person, organization, location, etc.)."
    )
    summary: str = Field(
        ..., description="Two to four sentences summarizing the entity."
    )
    key_facts: List[str] = Field(
        default_factory=list,
        description="Three to eight concise facts about the entity."
    )
    relationships: List[str] = Field(
        default_factory=list,
        description="List of key relationships for the entity."
    )
    card_metadata: List[MetaItem] = Field(
        default_factory=list,
        description="Additional context items such as timestamps or confidence notes."
    )
    confidence: float = Field(
        default=None, ge=0.0, le=1.0,
        description="Confidence score for the card."
    )
