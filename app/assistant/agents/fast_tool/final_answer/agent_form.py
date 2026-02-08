from typing import List
from pydantic import BaseModel, ConfigDict


class KeyValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    value: str


class AgentForm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final_answer_task: str
    final_answer_answer: str
    final_answer_what_was_done: str
    final_answer_interesting_info: str
    final_answer_sources_used: str
    final_answer_data_list: List[KeyValue]
