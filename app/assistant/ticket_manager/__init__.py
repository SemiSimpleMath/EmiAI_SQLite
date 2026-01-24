"""
Ticket Manager
===============

Generic ticket system for managing suggestions from any agent.

Components:
- TicketManager: Database CRUD, state transitions, UI emission
- TicketState: State enum (pending, proposed, accepted, dismissed, etc.)
"""

from app.assistant.ticket_manager.ticket_manager import (
    TicketManager,
    get_ticket_manager,
)

from app.assistant.ticket_manager.proactive_ticket import (
    TicketState,
)

__all__ = [
    'TicketManager',
    'get_ticket_manager',
    'TicketState',
]
