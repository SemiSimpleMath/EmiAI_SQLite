"""
Pipeline State Data Models for KG Explorer Pipeline
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel


class PipelineStage(str, Enum):
    """Stages of the KG Explorer pipeline."""
    NODE_SELECTION = "node_selection"
    EXPLORATION = "exploration"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineState(BaseModel):
    """State of the KG Explorer pipeline."""
    pipeline_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_stage: Optional[PipelineStage] = None
    error_message: Optional[str] = None
    final_report: Optional[Dict[str, Any]] = None
