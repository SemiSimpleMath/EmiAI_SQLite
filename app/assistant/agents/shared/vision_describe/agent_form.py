from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AgentForm(BaseModel):
    """
    Structured output for `shared::vision_describe`.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., description="Concise description of the most recent screenshot.")

