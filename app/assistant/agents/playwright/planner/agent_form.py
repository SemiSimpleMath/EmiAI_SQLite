from __future__ import annotations

from pydantic import BaseModel, Field


class AgentForm(BaseModel):
    what_i_am_thinking: str
    summary: str
    checklist: list[str]
    progress_report: list[str]
    plan: str
    action: str
    action_input: str


