from pydantic import BaseModel, Field
from typing import Optional, List


class FinalAnswer(BaseModel):
    """Structured response from the questioner after user interaction"""
    normal: bool = None
    ignore: bool = None
    custom_instructions: str = None  # User's actionable instructions

class AgentForm(BaseModel):
    what_i_am_thinking: str
    action: str
    action_input: Optional[str]
    final_answer: FinalAnswer

