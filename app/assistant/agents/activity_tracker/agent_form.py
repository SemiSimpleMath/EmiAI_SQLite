from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class AgentForm(BaseModel):
    """
    Output schema for activity_tracker agent.
    Returns a simple list of activity category names that should be reset,
    plus the NEW TOTAL counts for countable activities (e.g., hydration, coffee),
    plus any sleep events detected from chat,
    plus wake segments (when user was awake during sleep hours),
    plus signals about whether day has started.
    """

    activity_counts: Optional[Dict[str, int]] = Field(
        default_factory=dict,
        description="Dict of activity names to their NEW TOTAL counts today (e.g., {'hydration': 3, 'coffee': '}). CRITICAL: Return the complete updated total, not the increment!"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of what evidence was found and why these activities should be reset"
    )
