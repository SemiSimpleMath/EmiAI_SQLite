from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["done"] = Field(..., description="Always 'done'.")
    is_done: bool
    done_reason: str
    missing_requirements: List[str] = Field(default_factory=list)

