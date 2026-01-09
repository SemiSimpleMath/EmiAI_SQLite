from pydantic import BaseModel, Field
from typing import List, Optional

class Milestone(BaseModel):
    """A specific event or milestone that occurred today."""
    time: Optional[str] = Field(
        None,
        description="The time of the event if known (e.g., '09:00' or 'Morning')"
    )
    description: str = Field(
        description="Verbatim description of the event (e.g., 'Ate breakfast')"
    )

class AgentForm(BaseModel):
    """
    Output schema for daily_context_tracker agent.
    Maintains a simple log of the day's defining characteristics and events.
    """
    day_description: str = Field(
        description="A 1-2 sentence summary of Jukka's day, mood, or primary focus."
    )
    milestones: List[Milestone] = Field(
        default_factory=list,
        description="A chronological list of significant things that have happened today."
    )
    reasoning: str = Field(
        description="Brief explanation of why the description was updated or which milestones were added."
    )