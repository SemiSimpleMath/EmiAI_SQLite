from pydantic import BaseModel

class AgentForm(BaseModel):
    conclusion: str
    reason: str = None
    task_done: bool
