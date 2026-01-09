from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class TimelineEntry(BaseModel):
    # IMPORTANT: LLM outputs LOCAL TIME ONLY (no timezone, no Z, no offset).
    # Python code converts local->UTC deterministically before saving.
    start_local: str  # "YYYY-MM-DDTHH:MM:SS" local time (naive)
    end_local: str    # "YYYY-MM-DDTHH:MM:SS" local time (naive)
    label: str  # Location name
    address: Optional[Dict[str, str]] = None
    confidence: float = 0.7
    reasoning: str = ""


class AgentForm(BaseModel):
    timeline_entries: List[TimelineEntry]
    reasoning: str = ""  # Overall reasoning
