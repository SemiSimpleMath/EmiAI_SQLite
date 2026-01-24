from pydantic import BaseModel, Field
from typing import List, Literal


class AgentForm(BaseModel):
    """
    Memory Decider output.

    This agent only decides:
    - should we store this fact?
    - which tags should route it?
    - a canonical fact_summary to pass downstream.
    """

    what_i_am_thinking: str = Field(description="Brief reasoning for proceed vs reject.")

    tags: List[str] = Field(
        default_factory=list,
        description="1-2 routing tags (e.g., ['food'], ['drink','routine']). Empty if rejecting.",
    )

    decision: Literal["proceed", "reject"] = Field(
        description="Whether this should be stored as user memory."
    )

    fact_summary: str = Field(
        default="",
        description="Canonical sentence to store/apply (required if proceeding).",
    )

    rejection_reason: str = Field(
        default="",
        description="If rejecting, explain why this should not be saved.",
    )

