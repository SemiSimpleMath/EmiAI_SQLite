from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(..., description="What this click is intended to do (e.g., accept_cookies, close_modal).")
    x: float = Field(..., description="Viewport X coordinate (CSS pixels).")
    y: float = Field(..., description="Viewport Y coordinate (CSS pixels).")
    confidence: float = Field(..., ge=0.0, le=1.0, description="0.0 to 1.0 confidence.")
    rationale: str = Field(..., description="Brief explanation of why this is the right target.")


class AgentForm(BaseModel):
    """
    Structured output for `shared::vision_target_picker`.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["done"] = Field(..., description="Always 'done' so control returns to the planner.")
    targets: List[Target] = Field(
        ...,
        description="Proposed interaction targets in viewport coordinates (CSS pixels).",
    )

