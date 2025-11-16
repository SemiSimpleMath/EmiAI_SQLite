from pydantic import BaseModel


class AgentForm(BaseModel):
    checklist: str
    accomplishments: str
