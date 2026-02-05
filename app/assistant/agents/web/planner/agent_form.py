from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProgressItem(BaseModel):
    """
    High-signal, append-only progress facts.
    Keep items short and only emit when something materially new is discovered.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["fact", "partial_answer", "evidence", "blocker", "moot"] = Field(
        ...,
        description="Type of progress update.",
    )
    summary: str = Field(..., description="One-sentence summary of the new information.")
    evidence_url: Optional[str] = Field(None, description="Optional supporting URL.")
    confidence: Optional[Literal["low", "med", "high"]] = Field(None, description="Optional confidence level.")
    major_impact: bool = Field(False, description="True if this likely changes the overall plan (moot/blocker).")


class AgentForm(BaseModel):
    what_i_am_thinking: str
    summary: str
    checklist: List[str]
    progress_report: List[ProgressItem]
    plan: str
    action: str
    action_input: str


# Ensure postponed annotations are resolved for structured output schemas.
AgentForm.model_rebuild()
