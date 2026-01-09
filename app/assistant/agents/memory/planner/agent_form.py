from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict


class MemoryOperation(BaseModel):
    """A structured operation to perform on a JSON resource file."""
    
    operation: Literal['append', 'update', 'remove', 'no_change']
    file: Optional[str] = Field(default=None, description="e.g., 'resource_user_food_prefs.json'")
    path: Optional[str] = Field(default=None, description="JSON path like 'food.likes'")
    value: Optional[Dict[str, str]] = Field(default=None, description="Data to add/update (string key-value pairs)")
    search: Optional[Dict[str, str]] = Field(default=None, description="Search criteria (string key-value pairs)")
    expiry: Optional[str] = Field(default=None, description="Expiry date YYYY-MM-DD for temporary facts")
    reason: Optional[str] = Field(default=None, description="Reason for no_change operation")


class AgentForm(BaseModel):
    """Memory Planner output with structured operations."""
    
    what_i_am_thinking: str
    
    # Classification fields
    tags: List[str] = Field(
        default_factory=list,
        description="1-2 topic tags for this fact (e.g., ['food', 'routine'])"
    )
    
    # Decision fields
    decision: Literal['proceed', 'reject'] = Field(
        description="Whether to proceed with updating files or reject this extraction"
    )
    rejection_reason: str = Field(
        default="",
        description="If decision is 'reject', explain why this should not be saved"
    )
    
    # Operations (if proceeding)
    operations: List[MemoryOperation] = Field(
        default_factory=list,
        description="List of structured operations for Python to execute"
    )
    
    # Action field (always flow_exit_node for memory planner)
    action: str = Field(default="flow_exit_node")

