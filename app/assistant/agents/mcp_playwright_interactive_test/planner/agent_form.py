from pydantic import BaseModel
from typing import List


class AgentForm(BaseModel):
    what_i_am_thinking: str
    summary: str
    plan: str
    action: str
    action_input: str

