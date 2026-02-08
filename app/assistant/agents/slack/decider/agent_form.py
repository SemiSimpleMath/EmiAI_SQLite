from typing import Optional
from pydantic import BaseModel

class AgentForm(BaseModel):
    what_i_am_thinking: str
    next_agent: str
