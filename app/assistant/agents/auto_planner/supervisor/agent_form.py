from typing import Optional
from pydantic import BaseModel

class AgentForm(BaseModel):
    summary_of_information: str
    relevance_analysis: str
    cost_benefit_analysis: str
    decision: str  # "act_now", "snooze", or "dismiss"
    snooze_hours: Optional[int] = None  # How many hours to snooze (if decision == "snooze")
    action: str
    action_input: str