from typing import List, Dict
from pydantic import BaseModel

class AgentForm(BaseModel):
    task: str
    what_was_done: str
    status: str


