from typing import List, Optional
from pydantic import BaseModel

class AgentForm(BaseModel):
    relevance_analysis: str
    cost_benefit_analysis: str
    decision: str  # "act_now", "snooze", or "dismiss"
    snooze_hours: Optional[int] = None  # How many hours to snooze (if decision == "snooze")
    recommendation: str

