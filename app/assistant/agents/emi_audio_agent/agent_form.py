from pydantic import BaseModel, Field


class AgentForm(BaseModel):
    think_carefully: str
    msg_for_user: str
    reason: str
    have_all_info: bool
    call_team: bool
    msg_for_agent: str
    information_for_agent: str