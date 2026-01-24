"""
Ticket Database Model
=====================

Generic ticket model for suggestions and actions across the system.
Tracks lifecycle from creation through user response and execution.
"""

from enum import Enum
from datetime import datetime, timezone
import json
from pathlib import Path
from sqlalchemy import Column, String, DateTime, Text, Integer, Index, func, JSON

from app.models.base import Base


_TICKET_CONFIG_CACHE = None
_TICKET_CONFIG_MTIME = None


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_ticket_config() -> dict:
    global _TICKET_CONFIG_CACHE, _TICKET_CONFIG_MTIME
    config_path = Path(__file__).resolve().parent / "config_ticket_manager.json"
    try:
        if not config_path.exists():
            return {}
        mtime = config_path.stat().st_mtime
        if _TICKET_CONFIG_CACHE is None or _TICKET_CONFIG_MTIME != mtime:
            _TICKET_CONFIG_CACHE = json.loads(config_path.read_text(encoding="utf-8")) or {}
            _TICKET_CONFIG_MTIME = mtime
        return _TICKET_CONFIG_CACHE if isinstance(_TICKET_CONFIG_CACHE, dict) else {}
    except Exception:
        return {}


class TicketState(str, Enum):
    """
    State machine for tickets.
    """

    PENDING = "pending"
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SNOOZED = "snoozed"
    DISMISSED = "dismissed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ProactiveTicket(Base):
    """
    Persistent state tracking for tickets.
    """

    __tablename__ = "proactive_tickets"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(String(100), unique=True, nullable=False, index=True)

    suggestion_type = Column(String(50), nullable=False)

    state = Column(String(50), nullable=False, default=TicketState.PENDING.value, index=True)
    state_history = Column(JSON, nullable=False, default=list)

    title = Column(String(500))
    message = Column(Text)
    action_type = Column(String(100))
    action_params = Column(JSON)

    status_effect = Column(JSON, nullable=True)

    ticket_type = Column(String(50), nullable=True)
    effects_processed = Column(Integer, default=0)

    trigger_context = Column(JSON)
    trigger_reason = Column(Text)

    ask_user_id = Column(String(100))
    user_response_raw = Column(Text)
    user_response_parsed = Column(JSON)
    user_action = Column(String(50), nullable=True)
    user_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    proposed_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    valid_from = Column(DateTime(timezone=True))
    valid_until = Column(DateTime(timezone=True), index=True)

    snooze_until = Column(DateTime(timezone=True), nullable=True, index=True)
    snooze_count = Column(Integer, default=0)

    related_action_id = Column(String(100))
    execution_result = Column(Text)

    stale_after_minutes = Column(Integer, nullable=True)
    resolution_strategy = Column(String(50), nullable=True)
    auto_resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_reason = Column(Text, nullable=True)
    assumed_status_effect = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_ticket_state_created", "state", "created_at"),
        Index("idx_ticket_type_state", "suggestion_type", "state"),
        Index("idx_ticket_snooze", "snooze_until"),
        Index("idx_ticket_valid_until", "valid_until"),
    )

    def __repr__(self):
        return (
            "<ProactiveTicket("
            f"id={self.id}, ticket_id='{self.ticket_id}', state='{self.state}', "
            f"title='{self.title[:30] if self.title else 'N/A'}')>"
        )

    def get_stale_after_minutes(self) -> int:
        """
        Returns stale minutes or -1 if never stale.
        """
        if self.stale_after_minutes is not None:
            return self.stale_after_minutes
        cfg = _load_ticket_config()
        by_ticket_type = cfg.get("stale_minutes_by_ticket_type", {}) if isinstance(cfg, dict) else {}
        by_suggestion_type = cfg.get("stale_minutes_by_suggestion_type", {}) if isinstance(cfg, dict) else {}
        if isinstance(by_ticket_type, dict) and self.ticket_type in by_ticket_type:
            return _coerce_int(by_ticket_type[self.ticket_type], 120)
        if isinstance(by_suggestion_type, dict) and self.suggestion_type in by_suggestion_type:
            return _coerce_int(by_suggestion_type[self.suggestion_type], 120)
        return _coerce_int(cfg.get("default_stale_minutes", 120), 120)

    def get_default_resolution_strategy(self) -> str:
        if self.resolution_strategy:
            return self.resolution_strategy
        cfg = _load_ticket_config()
        by_ticket_type = cfg.get("resolution_strategy_by_ticket_type", {}) if isinstance(cfg, dict) else {}
        by_suggestion_type = cfg.get("resolution_strategy_by_suggestion_type", {}) if isinstance(cfg, dict) else {}
        if isinstance(by_ticket_type, dict) and self.ticket_type in by_ticket_type:
            return by_ticket_type[self.ticket_type]
        if isinstance(by_suggestion_type, dict) and self.suggestion_type in by_suggestion_type:
            return by_suggestion_type[self.suggestion_type]
        return str(cfg.get("default_resolution_strategy", "abandoned"))

    def is_stale(self) -> bool:
        if self.state != TicketState.PROPOSED.value:
            return False
        if not self.proposed_at:
            return False

        from datetime import timedelta

        stale_minutes = self.get_stale_after_minutes()
        if stale_minutes == -1:
            return False
        stale_threshold = self.proposed_at + timedelta(minutes=stale_minutes)
        return datetime.now(timezone.utc) > stale_threshold

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "suggestion_type": self.suggestion_type,
            "state": self.state,
            "state_history": self.state_history,
            "title": self.title,
            "message": self.message,
            "action_type": self.action_type,
            "action_params": self.action_params,
            "trigger_context": self.trigger_context,
            "trigger_reason": self.trigger_reason,
            "status_effect": self.status_effect,
            "ask_user_id": self.ask_user_id,
            "user_response_raw": self.user_response_raw,
            "user_response_parsed": self.user_response_parsed,
            "user_action": self.user_action,
            "user_text": self.user_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "snooze_until": self.snooze_until.isoformat() if self.snooze_until else None,
            "snooze_count": self.snooze_count,
            "related_action_id": self.related_action_id,
            "execution_result": self.execution_result,
            "stale_after_minutes": self.stale_after_minutes,
            "resolution_strategy": self.resolution_strategy,
            "auto_resolved_at": self.auto_resolved_at.isoformat() if self.auto_resolved_at else None,
            "resolution_reason": self.resolution_reason,
            "assumed_status_effect": self.assumed_status_effect,
        }


def initialize_proactive_tickets_db():
    from app.models.base import get_session

    session = get_session()
    engine = session.bind
    Base.metadata.create_all(engine, tables=[ProactiveTicket.__table__], checkfirst=True)
    session.close()


def drop_proactive_tickets_db():
    from app.models.base import get_session

    session = get_session()
    engine = session.bind
    Base.metadata.drop_all(engine, tables=[ProactiveTicket.__table__], checkfirst=True)
    session.close()


def reset_proactive_tickets_db():
    drop_proactive_tickets_db()
    initialize_proactive_tickets_db()
