from typing import List, Dict, Union

from pydantic import BaseModel

class Link(BaseModel):
    key: str
    value: str

class AgentForm(BaseModel):
    final_answer_content: str
    summary: str
    important_links: List[Link]