from typing import List

from pydantic import BaseModel


class AgentForm(BaseModel):
    topics: List[str]
    done: bool
