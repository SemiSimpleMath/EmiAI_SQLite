from pydantic import BaseModel, Field
from typing import List


class AgentForm(BaseModel):
    semantic_label: str = Field(
        description="Human-readable, context-specific description of the node (e.g., 'Father (Jukka's)', 'Likes sushi (Jukka)')"
    )
    reasoning: str = Field(
        description="Brief explanation of the semantic label choice"
    )
