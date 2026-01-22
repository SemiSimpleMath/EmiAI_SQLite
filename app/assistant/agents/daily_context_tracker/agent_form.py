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
    day_description: str = Field(
        description="The Expected Schedule (events/times) followed by 1-2 sentences on dominating themes/mood."
    )
    milestones: List[Milestone] = Field(
        default_factory=list,
        description="A chronological list of verbatim events that HAVE ALREADY happened today."
    )
    current_status: str = Field(
        description="A short label of what Jukka is doing right now (e.g., 'At work', 'On lunch', 'AFK')."
    )
    reasoning: str = Field(
        description="Internal logic for updates (e.g., 'Updating schedule because Jukka took the day off')."
    )