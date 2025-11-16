from pydantic import BaseModel
from typing import List


class AgentForm(BaseModel):
    what_i_am_thinking: str
    plan: str
    current_step: str
    action: str
    action_input: str
    checklist: List[str]
    achievements: List[str]

