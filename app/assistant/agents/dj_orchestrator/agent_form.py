from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class SongCandidate(BaseModel):
    """A single song candidate with reasoning."""
    
    title: str = Field(description="Song title (no extra formatting).")

    artist: str = Field(description="Primary artist name (no extra formatting).")
    
    reasoning: str = Field(
        description="Brief explanation of why this song fits the current vibe targets"
    )

    source: Literal["provided", "new"] = Field(
        description="Where this candidate came from. 'provided' means it was one of the 10 provided songs. 'new' means you invented it as a similar alternative."
    )


class AgentForm(BaseModel):
    """
    Output from the DJ orchestrator agent.
    
    Provides 5-10 song candidates that match the current vibe targets.
    The DJ Manager will score these based on play history and randomly
    select one (less recently played songs have higher probability).
    """
    
    candidates: List[SongCandidate] = Field(
        description=(
            "Exactly 10 candidates total. If a provided list is present and contains at least 5 items: "
            "pick exactly 5 from it (source='provided') and invent 5 new similar alternatives (source='new'). "
            "If the provided list is missing or has fewer than 5 items: pick as many as possible from it "
            "(source='provided') and fill the remainder with new candidates (source='new')."
        ),
        min_length=10,
        max_length=10,
    )
    
    vibe_interpretation: str = Field(
        description="Brief interpretation of the vibe targets (e.g., 'Low energy, slightly melancholic, instrumental preferred')"
    )
    
    skip_music: bool = Field(
        default=False,
        description="Set to true if music is not appropriate right now (e.g., meeting soon, user seems to want quiet)"
    )
    
    skip_reason: Optional[str] = Field(
        default=None,
        description="If skip_music is true, explain why"
    )
