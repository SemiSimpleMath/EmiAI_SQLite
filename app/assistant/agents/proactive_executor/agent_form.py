"""
Proactive Executor Agent Form
=============================

Defines the structured output for the proactive executor agent.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ExecutionAction(str, Enum):
    """What action the executor decides to take."""
    HANDLE_DIRECTLY = "handle_directly"  # Use tools myself
    DELEGATE_TO_EMI = "delegate_to_emi"  # Complex request, send to emi_team
    ACKNOWLEDGE_ONLY = "acknowledge_only"  # Just confirm, no action needed
    UPDATE_STATUS = "update_status"  # Update physical/cognitive status


class StatusUpdate(BaseModel):
    """Update to user's physical/cognitive status based on accepted suggestion."""
    field: str = Field(description="Status field to update (e.g., 'caffeine_recent', 'last_meal', 'energy_boost')")
    value: str = Field(description="New value for the field")
    reason: str = Field(description="Why this update is being made")


class AgentForm(BaseModel):
    """Structured output for the proactive executor."""
    
    # Decision
    action: ExecutionAction = Field(
        description="What action to take based on user's response"
    )
    
    # Understanding
    user_intent_summary: str = Field(
        description="Brief summary of what the user wants (1 sentence)"
    )
    
    # For delegation to emi_team
    delegation_task: Optional[str] = Field(
        default=None,
        description="If delegating, the clear task description for emi_team"
    )
    
    # For status updates
    status_updates: Optional[List[StatusUpdate]] = Field(
        default=None,
        description="Status updates to apply (e.g., user had coffee, took a break)"
    )
    
    # Confirmation message
    confirmation_message: str = Field(
        description="Brief message to confirm to user what's happening"
    )
    
    # Should we update physical status automatically?
    trigger_status_refresh: bool = Field(
        default=False,
        description="Whether to trigger a physical_status refresh after this action"
    )

