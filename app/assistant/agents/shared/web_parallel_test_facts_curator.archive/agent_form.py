from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field


class BroadcastItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    message: str


class AgentForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["done"] = Field(..., description="Always 'done'.")
    facts_patch: Dict[str, Any] = Field(default_factory=dict)
    broadcast: List[BroadcastItem] = Field(default_factory=list)
    notes: str

