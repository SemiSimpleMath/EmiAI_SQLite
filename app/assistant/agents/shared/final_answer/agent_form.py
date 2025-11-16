from typing import List, Dict
from pydantic import BaseModel


class KeyValue(BaseModel):
    key: str
    value: str

class AgentForm(BaseModel):
    final_answer_task: str
    final_answer_answer: str
    final_answer_what_was_done: str
    final_answer_interesting_info: str
    final_answer_sources_used: str
    final_answer_data_list: List[KeyValue]
