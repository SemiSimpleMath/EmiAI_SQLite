from pydantic import BaseModel, Field
from typing import List, Literal

EvidenceLabel = Literal["Reported", "Calendar", "Inferred"]

class Milestone(BaseModel):
    """A significant event that occurred today."""
    time: str = Field(
        description="Local time or local time range (e.g., '12:30 PM' or '12:35 PM - 1:20 PM')."
    )
    description: str = Field(
        description="Verbatim event description only (e.g., 'Lunch.' or 'AFK (ongoing).'). Do not include the evidence label in this field."
    )
    evidence: EvidenceLabel = Field(
        description="Evidence source: 'Reported' (user chat), 'Calendar' (calendar evidence), or 'Inferred' (telemetry)."
    )
    ongoing: bool = Field(
        default=False,
        description="True only if the milestone is currently ongoing (example: AFK ongoing)."
    )

class AgentForm(BaseModel):
    expected_schedule: str = Field(
        description=(
            "Planned structure of today, one item per line, with times when known. "
            "Primary source is today's calendar when provided, but user chat overrides calendar for conflicting time ranges. "
            "Example lines: 'Work 9:00 AM - 4:30 PM'."
        )
    )
    day_theme: str = Field(
        description="1 to 5 sentences describing what is dominating the day (plans, constraints, major concerns, travel day, etc.)."
    )
    milestones: List[Milestone] = Field(
        default_factory=list,
        description=(
            "Chronological historic log of significant events that already happened today. "
            "Include meals, naps, walks, major errands, major schedule changes, health updates, and AFK blocks of 20+ minutes. "
            "Exclude minor habits (water, coffee, stretches, bathroom trips, small snacks). "
            "AFK: at most one milestone per AFK interval; if ongoing and first reaches 20+ minutes, create one milestone at start time with ongoing=True; "
            "when it ends, edit that same milestone to final duration and set ongoing=False. "
            "You may revise an AFK milestone into a more specific event if later evidence explains what happened during that AFK."
        )
    )
    current_status: str = Field(
        description="Short label of what the user is doing right now (examples: 'At work', 'On lunch', 'AFK', 'Driving', 'At home')."
    )
