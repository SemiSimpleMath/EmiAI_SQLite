from typing import List
from pydantic import BaseModel, Field

class ResolvedSentence(BaseModel):
    original_sentence: str
    resolved_sentence: str
    reasoning: str

class AgentForm(BaseModel):
    resolved_sentences: List[ResolvedSentence]
