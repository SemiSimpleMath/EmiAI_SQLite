from pydantic import BaseModel


class AgentForm(BaseModel):
    what_i_am_thinking: str
    plan: str
    action: str
    answer: str

