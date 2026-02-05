from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class BroadcastItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(..., description="Exact job_id of a running job (preferred), or type:<child_type>.")
    message: str = Field(..., description="Short factual message/constraint to forward.")


class AgentForm(BaseModel):
    """Structured output for `shared::orchestrator_router`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["done"] = Field(..., description="Always 'done'.")
    replan_needed: bool = Field(
        False,
        description="Set true when we need the architect to spawn additional jobs / advance to next stage.",
    )
    cancel_running: bool = Field(
        False,
        description="Request cooperative cancellation of running jobs (best-effort).",
    )
    cancel_targets: List[str] = Field(
        default_factory=list,
        description="Optional: cancel only these job_ids (if empty and cancel_running=true, cancel all).",
    )
    broadcast: List[BroadcastItem] = Field(
        default_factory=list,
        description="Best-effort messages to forward to currently running jobs.",
    )
    notes: str = Field("", description="Short explanation of routing/plan advancement decisions.")


AgentForm.model_rebuild()

from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class BroadcastItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Exact job_id (preferred) or type:<child_type> or child_id:<substring>.")
    message: str = Field(..., description="Short factual update or constraint to forward.")


class AgentForm(BaseModel):
    """Structured output for `shared::orchestrator_router`."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["done"] = Field(..., description="Always 'done'.")
    replan_needed: bool = Field(
        False,
        description="True if new work should be scheduled (advance to next stage, spawn missing job, or major change).",
    )
    cancel_running: bool = Field(
        False,
        description="If true, request cooperative cancellation of running children (best-effort).",
    )
    cancel_targets: List[str] = Field(
        default_factory=list,
        description="Optional: restrict cancellations to these job_id values.",
    )
    broadcast: List[BroadcastItem] = Field(
        default_factory=list,
        description="Best-effort forwarding: who should be informed of facts/constraints.",
    )
    notes: str = Field("", description="Short explanation for routing decisions.")


AgentForm.model_rebuild()

