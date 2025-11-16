
from pydantic import BaseModel
class AgentForm(BaseModel):
    reason: str
    action: str
    action_input: str