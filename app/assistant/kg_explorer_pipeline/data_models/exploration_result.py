"""
Exploration Result Data Models for KG Explorer Pipeline
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel


class Discovery(BaseModel):
    """A discovered relationship or connection."""
    type: str  # "implicit_relationship", "temporal_inference", "missing_connection"
    description: str
    confidence: float
    evidence: List[str]
    suggested_action: Optional[str] = None


class TemporalInference(BaseModel):
    """A temporal reasoning result."""
    description: str
    confidence: float
    evidence: List[str]
    suggested_dates: Optional[Dict[str, str]] = None


class MissingConnection(BaseModel):
    """A missing connection that should exist."""
    description: str
    confidence: float
    evidence: List[str]
    suggested_connection: Optional[Dict[str, Any]] = None


class ExplorationResult(BaseModel):
    """Result of exploring a node."""
    node_id: str
    node_label: str
    discoveries: List[Discovery]
    temporal_inferences: List[TemporalInference]
    missing_connections: List[MissingConnection]
    confidence_score: float
    exploration_time: float
    error_message: Optional[str] = None
