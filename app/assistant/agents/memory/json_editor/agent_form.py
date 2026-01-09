from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict


class JsonEdit(BaseModel):
    """A single edit operation on the JSON."""
    operation: Literal['delete', 'update', 'insert', 'no_change']
    path: str = Field(description="JSON path to edit (e.g., 'food.likes[2]' or 'drinks.coffee.cutoff_time')")
    new_value: Optional[Dict[str, str]] = Field(default=None, description="New value to set (for insert/update)")
    reason: str = Field(description="Why this edit is needed")


class AgentForm(BaseModel):
    """JSON Editor output: list of edits to perform."""
    
    edits: List[JsonEdit] = Field(
        default_factory=list,
        description="List of edit operations to perform on the JSON"
    )
    
    decision: Literal['proceed', 'reject'] = Field(
        description="Whether to proceed with edits or reject (e.g., if duplicate/no change needed)"
    )
    
    reasoning: str = Field(
        description="Overall reasoning for the edit decisions"
    )


