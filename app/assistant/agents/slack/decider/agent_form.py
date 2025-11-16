from pydantic import BaseModel

class AgentForm(BaseModel):
    what_i_am_thinking: str
    action: str
    action_input: str
