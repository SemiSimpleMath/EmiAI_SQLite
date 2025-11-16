from pydantic import BaseModel


class AgentForm(BaseModel):
    summary: str
