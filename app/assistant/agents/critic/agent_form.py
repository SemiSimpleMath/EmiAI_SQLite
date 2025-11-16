from pydantic import BaseModel


class AgentForm(BaseModel):
    my_thoughts: str
    critique: str
    is_it_worth_trouble: str
    actionable_change: str
    must_revise_plan: bool