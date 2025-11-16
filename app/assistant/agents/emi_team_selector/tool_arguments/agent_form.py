from typing import Dict
from pydantic import BaseModel

class AgentForm(BaseModel):
    tool_arguments: Dict[str, str]
