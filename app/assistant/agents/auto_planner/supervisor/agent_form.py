from pydantic import BaseModel

class AgentForm(BaseModel):
    summary_of_information: str
    relevance_analysis: str
    cost_benefit_analysis: str
    decision: bool
    action: str
    action_input: str