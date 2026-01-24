"""
TicketManager
==============

Manages CRUD operations and state transitions for tickets (suggestions, approvals, etc.).

This is a generic ticket system that any agent can use to create tickets.
The ticket flow is: pending -> proposed -> accepted/dismissed/snoozed/expired
"""

import uuid
from collections import deque
from contextlib import contextmanager
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy.exc import SQLAlchemyError

from app.models.base import get_session
from app.assistant.ticket_manager.proactive_ticket import (
    ProactiveTicket, 
    TicketState,
    initialize_proactive_tickets_db
)
from app.assistant.utils.logging_config import get_logger
from app.assistant.utils.error_logging import log_critical_error, log_warning_banner

logger = get_logger(__name__)


class TicketManager:
    """
    Manages ticket lifecycle.
    
    Responsibilities:
    - Create new tickets
    - Query tickets by state
    - Transition ticket states
    - Handle snooze expiration
    - Handle ticket expiration
    """
    
    def __init__(self):
        # Ensure table exists
        try:
            initialize_proactive_tickets_db()
        except Exception as e:
            logger.warning(f"Could not initialize proactive_tickets table: {e}")
        
        # Clear all tickets on app startup (disabled)
        # self._clear_all_tickets_on_startup()
        self._ticket_queue = deque()
        self._ticket_queue_lock = threading.Lock()
        self._ticket_processing_lock = threading.Lock()

    @contextmanager
    def _session_scope(self):
        session = get_session()
        session.expire_on_commit = False
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _enqueue_ticket_ids(self, ticket_ids: List[int]) -> None:
        if not ticket_ids:
            return
        with self._ticket_queue_lock:
            existing = set(self._ticket_queue)
            for ticket_id in ticket_ids:
                if ticket_id not in existing:
                    self._ticket_queue.append(ticket_id)
                    existing.add(ticket_id)

    def _pop_ticket_id(self) -> Optional[int]:
        with self._ticket_queue_lock:
            if not self._ticket_queue:
                return None
            return self._ticket_queue.popleft()

    def claim_accepted_tickets(self, ticket_type: Optional[str] = None) -> List[ProactiveTicket]:
        """
        Claim accepted, unprocessed tickets via a serialized in-process queue.
        Returns claimed ticket objects with effects_processed=2.
        """
        claimed: List[ProactiveTicket] = []
        if not self._ticket_processing_lock.acquire(blocking=False):
            return claimed

        try:
            with self._session_scope() as session:
                query = session.query(ProactiveTicket.id).filter(
                    ProactiveTicket.state == TicketState.ACCEPTED.value,
                    ProactiveTicket.effects_processed == 0,
                )
                if ticket_type:
                    query = query.filter(ProactiveTicket.ticket_type == ticket_type)
                ticket_ids = [row[0] for row in query.all()]

            self._enqueue_ticket_ids(ticket_ids)

            while True:
                ticket_id = self._pop_ticket_id()
                if ticket_id is None:
                    break

                with self._session_scope() as session:
                    claim = (
                        session.query(ProactiveTicket)
                        .filter(
                            ProactiveTicket.id == ticket_id,
                            ProactiveTicket.effects_processed == 0,
                        )
                        .update({ProactiveTicket.effects_processed: 2}, synchronize_session=False)
                    )
                if claim != 1:
                    continue

                with self._session_scope() as session:
                    ticket = session.query(ProactiveTicket).filter(ProactiveTicket.id == ticket_id).first()
                    if ticket:
                        claimed.append(ticket)

            return claimed
        finally:
            self._ticket_processing_lock.release()

    def set_ticket_processed_state(self, ticket_id: int, state: int) -> None:
        """Set effects_processed for a ticket id."""
        with self._session_scope() as session:
            session.query(ProactiveTicket).filter(
                ProactiveTicket.id == ticket_id
            ).update({ProactiveTicket.effects_processed: state}, synchronize_session=False)
    
    def _emit_suggestion_to_ui(self, ticket_dict: Dict[str, Any]):
        """Emit a proactive suggestion to the frontend via WebSocket with TTS."""
        try:
            from app.assistant.ServiceLocator.service_locator import DI
            from app.assistant.utils.pydantic_classes import Message, UserMessage, UserMessageData
            from datetime import datetime, timezone
            
            # Emit the suggestion data for the popup
            message = Message(
                event_topic='proactive_suggestion',
                data=ticket_dict
            )
            DI.event_hub.publish(message)
            logger.info(f"Emitted proactive suggestion to UI: {ticket_dict.get('ticket_id')}")
            
            # Also emit TTS message so Emi speaks the suggestion
            tts_text = ticket_dict.get('message') or ticket_dict.get('title', 'I have a suggestion for you.')
            tts_message = UserMessage(
                data_type='user_msg',
                sender='proactive_orchestrator',
                receiver=None,
                timestamp=datetime.now(timezone.utc),
                role='assistant',
                user_message_data=UserMessageData(
                    feed=None,  # No visual feed, just TTS
                    tts=True,
                    tts_text=tts_text
                )
            )
            tts_message.event_topic = 'socket_emit'
            DI.event_hub.publish(tts_message)
            logger.info(f"Emitted TTS for proactive suggestion")
            
        except Exception as e:
            logger.warning(f"Could not emit suggestion to UI: {e}")
    
    # =========================================================================
    # Create Operations
    # =========================================================================
    
    def create_ticket(
        self,
        suggestion_type: str,
        title: str,
        message: str,
        action_type: str = "none",
        action_params: Dict = None,
        trigger_context: Dict = None,
        trigger_reason: str = None,
        valid_hours: int = 4,
        status_effect: Dict = None,
        ticket_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new proactive ticket.
        
        Args:
            suggestion_type: Category (nutrition, rest, task, movement, reminder)
            title: Short description
            message: What Emi says to user
            action_type: What to do if accepted (calendar_block, reminder, notify, none)
            action_params: Parameters for the action
            trigger_context: Snapshot of context that triggered this
            trigger_reason: Why this was suggested
            valid_hours: How long this suggestion is valid (default 4 hours)
            status_effect: Dict of field -> value to record when accepted (e.g., {"finger_stretch": "completed"})
            ticket_type: Explicit ticket type (e.g., "wellness", "tool_approval", "general")
            
        Returns:
            Created ticket as dict or None if error
        """
        with self._session_scope() as session:
            now = datetime.now(timezone.utc)
            ticket_id = f"proactive_{suggestion_type}_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            
            # Determine ticket_type based on action_type or explicit override
            if not ticket_type:
                if action_type and action_type.startswith("tool_"):
                    ticket_type = "tool_approval"
                else:
                    ticket_type = "general"
            
            ticket = ProactiveTicket(
                ticket_id=ticket_id,
                suggestion_type=suggestion_type,
                state=TicketState.PENDING.value,
                state_history=[{
                    "state": TicketState.PENDING.value,
                    "timestamp": now.isoformat(),
                    "reason": "Created"
                }],
                title=title,
                message=message,
                action_type=action_type,
                action_params=action_params or {},
                trigger_context=trigger_context or {},
                trigger_reason=trigger_reason,
                status_effect=status_effect or {},
                ticket_type=ticket_type,
                effects_processed=0,
                valid_from=now,
                valid_until=now + timedelta(hours=valid_hours)
            )
            
            session.add(ticket)
            
            # Convert to dict before closing session
            ticket_dict = ticket.to_dict()
            logger.info(f"📋 Created ticket: {ticket_id} ({suggestion_type})")
            
            # Mark as proposed (ready to show user)
            self.mark_proposed(ticket_id)
            
            # Emit to frontend via WebSocket
            self._emit_suggestion_to_ui(ticket_dict)
            
            return ticket_dict
        
        # _session_scope handles rollback/close
        
    
    # =========================================================================
    # Query Operations
    # =========================================================================
    
    def get_ticket_by_id(self, ticket_id: str) -> Optional[ProactiveTicket]:
        """Get a ticket by its ticket_id."""
        with self._session_scope() as session:
            return session.query(ProactiveTicket).filter(
                ProactiveTicket.ticket_id == ticket_id
            ).first()
    
    def update_ticket(self, ticket_id: str, **kwargs) -> bool:
        """
        Update a ticket's fields.
        
        Args:
            ticket_id: The ticket_id to update
            **kwargs: Fields to update (title, message, suggestion_type, action_type, etc.)
            
        Returns:
            True if updated successfully, False otherwise
        """
        with self._session_scope() as session:
            ticket = session.query(ProactiveTicket).filter(
                ProactiveTicket.ticket_id == ticket_id
            ).first()
            
            if not ticket:
                logger.warning(f"Ticket not found for update: {ticket_id}")
                return False
            
            # Update allowed fields
            allowed_fields = [
                'title', 'message', 'suggestion_type', 'action_type', 
                'action_params', 'trigger_reason', 'valid_until'
            ]
            
            for field, value in kwargs.items():
                if field in allowed_fields and hasattr(ticket, field):
                    setattr(ticket, field, value)
            logger.info(f"Updated ticket {ticket_id}: {list(kwargs.keys())}")
            return True
    
    def save_ticket(self, ticket: ProactiveTicket) -> bool:
        """Save/update a ticket's changes to the database.
        
        Args:
            ticket: The ProactiveTicket instance to save
            
        Returns:
            True if save was successful, False otherwise
        """
        with self._session_scope() as session:
            # Merge the ticket into this session
            session.merge(ticket)
            return True
    
    def get_tickets_by_state(self, state: TicketState, limit: int = 50) -> List[ProactiveTicket]:
        """Get tickets in a specific state."""
        with self._session_scope() as session:
            return session.query(ProactiveTicket).filter(
                ProactiveTicket.state == state.value
            ).order_by(ProactiveTicket.created_at.desc()).limit(limit).all()
    
    def get_pending_tickets(self, limit: int = 10) -> List[ProactiveTicket]:
        """Get tickets ready to be proposed (PENDING state, not expired, not too old)."""
        with self._session_scope() as session:
            now = datetime.now(timezone.utc)
            max_age = timedelta(hours=2)  # Safety net (matches expire_old_tickets)
            
            # Fetch candidates
            candidates = session.query(ProactiveTicket).filter(
                ProactiveTicket.state == TicketState.PENDING.value
            ).order_by(ProactiveTicket.created_at.asc()).all()
            
            # Filter in Python for timezone safety
            result = []
            for ticket in candidates:
                # Check age (safety net - nothing older than 24h)
                created_at = ticket.created_at
                if created_at:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if (now - created_at) > max_age:
                        continue  # Too old
                
                # Check valid_until
                valid_until = ticket.valid_until
                if valid_until and valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=timezone.utc)
                if valid_until and valid_until <= now:
                    continue  # Expired
                
                result.append(ticket)
                if len(result) >= limit:
                    break
            return result
    
    def get_snoozed_tickets_ready(self) -> List[ProactiveTicket]:
        """Get snoozed tickets whose snooze time has passed."""
        with self._session_scope() as session:
            now = datetime.now(timezone.utc)
            # Fetch snoozed tickets with snooze_until set
            candidates = session.query(ProactiveTicket).filter(
                ProactiveTicket.state == TicketState.SNOOZED.value,
                ProactiveTicket.snooze_until != None
            ).all()
            
            # Filter in Python for timezone safety
            ready = []
            for ticket in candidates:
                snooze_until = ticket.snooze_until
                if snooze_until and snooze_until.tzinfo is None:
                    snooze_until = snooze_until.replace(tzinfo=timezone.utc)
                if snooze_until and snooze_until <= now:
                    ready.append(ticket)
            return ready
    
    def get_proposed_tickets_waiting(self) -> List[Dict[str, Any]]:
        """
        Get tickets ready to show to the user.
        Returns tickets in PENDING or PROPOSED state that are:
        - Not expired (valid_until is null or in the future)
        - Not snoozed (snooze_until is null or in the past)
        - Not too old (safety net: max 2 hours)
        """
        with self._session_scope() as session:
            now = datetime.now(timezone.utc)
            max_age = timedelta(hours=2)  # Safety net (matches expire_old_tickets)
            
            # Fetch candidates
            candidates = session.query(ProactiveTicket).filter(
                ProactiveTicket.state.in_([
                    TicketState.PENDING.value,
                    TicketState.PROPOSED.value
                ])
            ).order_by(ProactiveTicket.created_at.asc()).all()
            
            # Filter in Python for timezone safety
            result = []
            for ticket in candidates:
                # Check age (safety net - nothing older than 24h)
                created_at = ticket.created_at
                if created_at:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if (now - created_at) > max_age:
                        continue  # Too old
                
                # Check valid_until (null = valid, future = valid)
                valid_until = ticket.valid_until
                if valid_until and valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=timezone.utc)
                if valid_until and valid_until <= now:
                    continue  # Expired
                
                # Check snooze_until (null = not snoozed, past = ready)
                snooze_until = ticket.snooze_until
                if snooze_until and snooze_until.tzinfo is None:
                    snooze_until = snooze_until.replace(tzinfo=timezone.utc)
                if snooze_until and snooze_until > now:
                    continue  # Still snoozed
                
                result.append(ticket.to_dict())
            
            return result
    
    def get_active_ticket_count(self) -> int:
        """Count tickets that are active (not completed/dismissed/expired/failed)."""
        with self._session_scope() as session:
            terminal_states = [
                TicketState.COMPLETED.value,
                TicketState.DISMISSED.value,
                TicketState.EXPIRED.value,
                TicketState.FAILED.value
            ]
            return session.query(ProactiveTicket).filter(
                ~ProactiveTicket.state.in_(terminal_states)
            ).count()
    
    def has_similar_active_ticket(self, suggestion_type: str, title_contains: str = None) -> bool:
        """
        Check if there's already an active ticket of similar type.
        Used to prevent duplicate suggestions.
        """
        with self._session_scope() as session:
            terminal_states = [
                TicketState.COMPLETED.value,
                TicketState.DISMISSED.value,
                TicketState.EXPIRED.value,
                TicketState.FAILED.value
            ]
            query = session.query(ProactiveTicket).filter(
                ProactiveTicket.suggestion_type == suggestion_type,
                ~ProactiveTicket.state.in_(terminal_states)
            )
            
            if title_contains:
                query = query.filter(ProactiveTicket.title.ilike(f"%{title_contains}%"))
            
            return query.count() > 0
    
    def get_recent_tickets(self, hours: int = 24, limit: int = 50) -> List[ProactiveTicket]:
        """Get tickets from the last N hours (by created_at)."""
        with self._session_scope() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return session.query(ProactiveTicket).filter(
                ProactiveTicket.created_at >= cutoff
            ).order_by(ProactiveTicket.created_at.desc()).limit(limit).all()
    
    def get_recently_accepted_tickets(self, hours: int = 2, limit: int = 50) -> List[ProactiveTicket]:
        """Get tickets accepted in the last N hours (by responded_at)."""
        with self._session_scope() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            return session.query(ProactiveTicket).filter(
                ProactiveTicket.state == TicketState.ACCEPTED.value,
                ProactiveTicket.responded_at >= cutoff
            ).order_by(ProactiveTicket.responded_at.desc()).limit(limit).all()
    
    # =========================================================================
    # State Transition Operations
    # =========================================================================
    
    def transition_state(
        self,
        ticket_id: str,
        new_state: TicketState,
        reason: str = None,
        **kwargs
    ) -> bool:
        """
        Transition a ticket to a new state.
        
        Args:
            ticket_id: The ticket to update
            new_state: Target state
            reason: Why the transition
            **kwargs: Additional fields to update (snooze_until, user_response_raw, etc.)
            
        Returns:
            True if successful
        """
        with self._session_scope() as session:
            ticket = session.query(ProactiveTicket).filter(
                ProactiveTicket.ticket_id == ticket_id
            ).first()
            
            if not ticket:
                logger.warning(f"Ticket not found: {ticket_id}")
                return False
            
            old_state = ticket.state
            now = datetime.now(timezone.utc)
            
            # Update state
            ticket.state = new_state.value
            
            # Add to history
            history = ticket.state_history or []
            history.append({
                "from_state": old_state,
                "to_state": new_state.value,
                "timestamp": now.isoformat(),
                "reason": reason or f"Transitioned to {new_state.value}"
            })
            ticket.state_history = history
            
            # Update timestamps based on state
            if new_state == TicketState.PROPOSED:
                ticket.proposed_at = now
            elif new_state in [TicketState.ACCEPTED, TicketState.SNOOZED, TicketState.DISMISSED]:
                ticket.responded_at = now
            elif new_state == TicketState.COMPLETED:
                ticket.completed_at = now
            
            # Update additional fields from kwargs
            for key, value in kwargs.items():
                if hasattr(ticket, key):
                    setattr(ticket, key, value)
            if new_state == TicketState.ACCEPTED:
                logger.info(
                    "✅ Ticket accepted",
                    extra={
                        "ticket_id": ticket.ticket_id,
                        "suggestion_type": ticket.suggestion_type,
                        "ticket_type": ticket.ticket_type,
                        "effects_processed": ticket.effects_processed,
                        "status_effect": ticket.status_effect,
                        "responded_at": ticket.responded_at.isoformat() if ticket.responded_at else None,
                    },
                )
            logger.info(f"📋 Ticket {ticket_id}: {old_state} → {new_state.value}")
            return True
    
    def mark_proposed(self, ticket_id: str, ask_user_id: str = None) -> bool:
        """Mark ticket as proposed to user."""
        return self.transition_state(
            ticket_id, 
            TicketState.PROPOSED, 
            reason="Proposed to user",
            ask_user_id=ask_user_id
        )
    
    def mark_accepted(self, ticket_id: str, user_response_raw: str = None) -> bool:
        """Mark ticket as accepted by user."""
        return self.transition_state(
            ticket_id,
            TicketState.ACCEPTED,
            reason="User accepted",
            user_response_raw=user_response_raw,
            user_response_parsed={"decision": "accept"}
        )
    
    def mark_snoozed(self, ticket_id: str, snooze_minutes: int = 30, user_response_raw: str = None) -> bool:
        """Mark ticket as snoozed by user."""
        snooze_until = datetime.now(timezone.utc) + timedelta(minutes=snooze_minutes)
        
        # Get current snooze count
        with self._session_scope() as session:
            ticket = session.query(ProactiveTicket).filter(
                ProactiveTicket.ticket_id == ticket_id
            ).first()
            snooze_count = (ticket.snooze_count or 0) + 1 if ticket else 1
        
        return self.transition_state(
            ticket_id,
            TicketState.SNOOZED,
            reason=f"User snoozed for {snooze_minutes} minutes",
            snooze_until=snooze_until,
            snooze_count=snooze_count,
            user_response_raw=user_response_raw,
            user_response_parsed={"decision": "snooze", "snooze_minutes": snooze_minutes}
        )
    
    def mark_dismissed(self, ticket_id: str, user_response_raw: str = None) -> bool:
        """Mark ticket as dismissed by user."""
        return self.transition_state(
            ticket_id,
            TicketState.DISMISSED,
            reason="User dismissed",
            user_response_raw=user_response_raw,
            user_response_parsed={"decision": "dismiss"}
        )
    
    def mark_acknowledged(self, ticket_id: str, user_response_raw: str = None) -> bool:
        """Mark ticket as acknowledged by user (seen but not completed)."""
        return self.transition_state(
            ticket_id,
            TicketState.ACKNOWLEDGED,
            reason="User acknowledged",
            user_response_raw=user_response_raw,
            user_response_parsed={"decision": "acknowledge"}
        )
    
    def mark_executing(self, ticket_id: str) -> bool:
        """Mark ticket as executing action."""
        return self.transition_state(
            ticket_id,
            TicketState.EXECUTING,
            reason="Executing action"
        )
    
    def mark_completed(self, ticket_id: str, execution_result: str = None, related_action_id: str = None) -> bool:
        """Mark ticket as completed successfully."""
        return self.transition_state(
            ticket_id,
            TicketState.COMPLETED,
            reason="Action completed",
            execution_result=execution_result,
            related_action_id=related_action_id
        )
    
    def mark_failed(self, ticket_id: str, execution_result: str = None) -> bool:
        """Mark ticket as failed."""
        return self.transition_state(
            ticket_id,
            TicketState.FAILED,
            reason="Action failed",
            execution_result=execution_result
        )
    
    def mark_expired(self, ticket_id: str, reason: str = "Time window passed") -> bool:
        """Mark ticket as expired."""
        return self.transition_state(
            ticket_id,
            TicketState.EXPIRED,
            reason=reason
        )
    
    # =========================================================================
    # Maintenance Operations
    # =========================================================================
    
    def wake_snoozed_tickets(self) -> int:
        """
        Handle snoozed tickets whose snooze time has passed.
        
        Instead of re-proposing the old ticket (which has stale message like
        "It's 5pm..." when it's now 7pm), we EXPIRE it and let the orchestrator
        create a fresh ticket with current context if the need still exists.
        
        Returns:
            Number of tickets processed
        """
        tickets = self.get_snoozed_tickets_ready()
        count = 0
        
        for ticket in tickets:
            # Expire the snoozed ticket - orchestrator will create fresh one if needed
            self.mark_expired(
                ticket.ticket_id, 
                reason=f"Snooze expired after {ticket.snooze_count} snooze(s) - orchestrator will re-evaluate"
            )
            count += 1
            logger.info(f"Expired snoozed ticket '{ticket.title}' - orchestrator will create fresh if needed")
        
        if count > 0:
            logger.info(f"📋 Expired {count} snoozed tickets (orchestrator will re-evaluate)")
        
        return count
    
    def expire_old_tickets(self) -> int:
        """
        Expire tickets that have passed their valid_until time.
        Also expires any ticket older than 2 hours as a safety net.
        
        Returns:
            Number of tickets expired
        """
        with self._session_scope() as session:
            now = datetime.now(timezone.utc)
            max_age = timedelta(hours=2)  # Safety net: tickets older than 2h are stale
            
            # Find tickets that are not in terminal state
            terminal_states = [
                TicketState.COMPLETED.value,
                TicketState.DISMISSED.value,
                TicketState.EXPIRED.value,
                TicketState.FAILED.value
            ]
            
            # Fetch ALL non-terminal candidates
            candidates = session.query(ProactiveTicket).filter(
                ~ProactiveTicket.state.in_(terminal_states)
            ).all()
            
            count = 0
            for ticket in candidates:
                should_expire = False
                
                # Check valid_until
                valid_until = ticket.valid_until
                if valid_until:
                    if valid_until.tzinfo is None:
                        valid_until = valid_until.replace(tzinfo=timezone.utc)
                    if valid_until < now:
                        should_expire = True
                
                # Safety net: expire anything older than 2 hours
                created_at = ticket.created_at
                if created_at:
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if (now - created_at) > max_age:
                        should_expire = True
                        logger.info(f"Safety net: expiring ticket {ticket.ticket_id} (age > 2h)")
                
                if should_expire:
                    self.mark_expired(ticket.ticket_id)
                    count += 1
            
            if count > 0:
                logger.info(f"Expired {count} old tickets")
            
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about tickets."""
        with self._session_scope() as session:
            total = session.query(ProactiveTicket).count()
            
            stats = {"total": total}
            for state in TicketState:
                count = session.query(ProactiveTicket).filter(
                    ProactiveTicket.state == state.value
                ).count()
                stats[state.value] = count
            
            return stats
    
    def clear_tool_approval_tickets(self) -> int:
        """
        Clear all tool approval tickets at startup.
        These are stale if the app restarted.
        
        Returns:
            Number of tickets deleted
        """
        with self._session_scope() as session:
            deleted = session.query(ProactiveTicket).filter(
                ProactiveTicket.suggestion_type == 'tool_approval',
                ProactiveTicket.state.in_(['pending', 'proposed'])
            ).delete(synchronize_session='fetch')
            return deleted

    def clear_all_tickets(self) -> int:
        """Delete all tickets."""
        with self._session_scope() as session:
            return session.query(ProactiveTicket).delete(synchronize_session='fetch')
    
    def _clear_all_tickets_on_startup(self):
        """
        Clear ALL proactive tickets at app startup (fresh slate).
        
        This ensures no stale tickets persist across restarts, which was causing
        the 'already have active X ticket' blocking issue.
        """
        with self._session_scope() as session:
            # Count before deletion
            count = session.query(ProactiveTicket).count()
            
            if count > 0:
                # Delete all tickets
                session.query(ProactiveTicket).delete(synchronize_session='fetch')
                logger.info(f"🧹 Cleared {count} stale proactive tickets at app startup")
            else:
                logger.info("No proactive tickets to clear at startup")


# Singleton instance
_ticket_manager: Optional[TicketManager] = None


def get_ticket_manager() -> TicketManager:
    """Get the singleton TicketManager instance."""
    global _ticket_manager
    if _ticket_manager is None:
        _ticket_manager = TicketManager()
    return _ticket_manager

