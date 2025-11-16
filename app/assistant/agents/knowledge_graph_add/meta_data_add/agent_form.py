from typing import List

from pydantic import BaseModel, Field


class Node(BaseModel):
    temp_id: str
    aliases: List[str]
    hash_tags: List[str]
    start_date: str
    start_date_confidence: str
    end_date: str
    end_date_confidence: str
    valid_during: str
    semantic_label: str
    goal_status: str
    confidence: float
    importance: float

class AgentForm(BaseModel):
    Nodes: List[Node]
