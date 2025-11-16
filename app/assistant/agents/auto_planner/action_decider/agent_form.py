from typing import List
from pydantic import BaseModel

class AgentForm(BaseModel):
    relevance_analysis: str
    cost_benefit_analysis: str
    decision: bool
    recommendation: str

