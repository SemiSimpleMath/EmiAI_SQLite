"""
Exploration Node Data Models for KG Explorer Pipeline
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class ExplorationNode(BaseModel):
    """A node selected for exploration."""
    id: str
    label: str
    semantic_label: Optional[str] = None
    type: str
    category: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    connection_count: int = 0
    exploration_potential: float = 0.0
    reasoning: Optional[str] = None
