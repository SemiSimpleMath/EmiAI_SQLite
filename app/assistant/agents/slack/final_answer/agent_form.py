from typing import List, Dict
from pydantic import BaseModel


class KeyValue(BaseModel):
    key: str
    value: str

class AgentForm(BaseModel):
    task: str
    answer: str
    what_was_done: str
    interesting_info: str
    sources_used: str

