from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class SleepEvent(BaseModel):
    """A sleep event detected from user chat - when they went to sleep and/or woke up."""
    start_time: Optional[str] = Field(
        default=None,
        description="When user went to sleep (e.g., '23:00', '11:00 PM'). None if not mentioned."
    )
    end_time: Optional[str] = Field(
        default=None,
        description="When user woke up (e.g., '07:00', '3:00'). None if not mentioned."
    )
    raw_mention: str = Field(
        description="The exact phrase user said (e.g., 'I went to sleep at 11PM and woke up at 3')"
    )


class WakeSegment(BaseModel):
    """A wake/awake segment during the night - user was up when they should have been sleeping."""
    start_time: str = Field(
        description="When user woke up during the night (e.g., '03:00', '3:00 AM')"
    )
    end_time: Optional[str] = Field(
        default=None,
        description="When user went back to sleep (e.g., '03:30', '3:30 AM'). None if not explicitly mentioned."
    )
    duration_estimate_minutes: Optional[int] = Field(
        default=None,
        description="Best guess for how long they were awake (in minutes). Use this when end_time is not specified. Common estimates: 'a while'=30-60min, 'a bit'=15-30min, 'briefly'=5-15min."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Why they were awake (e.g., 'bathroom', 'couldn't sleep', 'stress'). None if not mentioned."
    )
    raw_mention: str = Field(
        description="The exact phrase user said (e.g., 'I woke up at 3am and couldn't go back to sleep for a while')"
    )


class DayStartSignal(BaseModel):
    """Signal that indicates day has started (user is up for real)."""
    signal_type: str = Field(
        description="Type of signal: 'confirmed_awake', 'going_back_to_sleep', or 'sleep_quality_report'"
    )
    reasoning: str = Field(
        description="Why this indicates day start or not (e.g., 'User said making coffee')"
    )


class AgentForm(BaseModel):
    """
    Output schema for activity_tracker agent.
    Returns a simple list of activity category names that should be reset,
    plus the NEW TOTAL counts for countable activities (e.g., hydration, coffee),
    plus any sleep events detected from chat,
    plus wake segments (when user was awake during sleep hours),
    plus signals about whether day has started.
    """
    activities_to_reset: List[str] = Field(
        default_factory=list,
        description="List of activity field names to reset (e.g., ['hydration', 'finger_stretch', 'meal'])"
    )
    activity_counts: Optional[Dict[str, int]] = Field(
        default_factory=dict,
        description="Dict of activity names to their NEW TOTAL counts today (e.g., {'hydration': 3, 'coffee': '}). CRITICAL: Return the complete updated total, not the increment!"
    )
    sleep_events: List[SleepEvent] = Field(
        default_factory=list,
        description="List of sleep/nap events detected from user chat"
    )
    wake_segments: List[WakeSegment] = Field(
        default_factory=list,
        description="List of wake/awake periods during the night (e.g., 'I woke up at 3am for a bit')"
    )
    day_start_signal: Optional[DayStartSignal] = Field(
        default=None,
        description="Signal about whether user is up for the day or going back to sleep"
    )
    reasoning: str = Field(
        ...,
        description="Brief explanation of what evidence was found and why these activities should be reset"
    )
