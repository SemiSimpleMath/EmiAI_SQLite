"""
Ticket API
==========

REST endpoints for ticket interactions.
Route layer - delegates to TicketService for business logic.
"""

from flask import Blueprint, jsonify, request

from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI

logger = get_logger(__name__)

ticket_api_bp = Blueprint('ticket_api', __name__)


@ticket_api_bp.route('/api/tickets/pending')
def get_pending_tickets():
    """
    Get tickets ready to show to user.
    Returns tickets in PENDING or PROPOSED state.
    """
    try:
        ticket_manager = DI.ticket_manager
        tickets = ticket_manager.get_tickets_pending_or_proposed()

        return jsonify({
            "count": len(tickets),
            "tickets": [t.to_dict() for t in tickets],
        })

    except Exception as e:
        logger.error(f"Error getting pending tickets: {e}")
        return jsonify({"error": str(e)}), 500


@ticket_api_bp.route('/api/tickets/respond', methods=['POST'])
def respond_to_ticket():
    """
    Handle user response to a ticket.
    
    Request body:
    {
        "ticket_id": "...",
        "action": "done" | "skip" | "later" | "acknowledge" | "willdo" | "no" | "accept" | "dismiss",
        "user_text": "optional user explanation",
        "snooze_minutes": 30  // only used if action is "later"
    }
    
    Actions:
    - Activity layout: "done" (completed), "skip" (dismissed), "later" (snoozed)
    - Advice layout: "acknowledge" (received), "willdo" (will act), "no" (not applicable), "later"
    - Tool approval: "accept" (allow), "dismiss" (deny)
    """
    try:
        from app.assistant.ticket_manager.ticket_service import get_ticket_service

        data = request.get_json() or {}

        ticket_id = data.get('ticket_id', '')
        action = data.get('action', '')
        user_text = data.get('user_text', '')
        snooze_minutes = data.get('snooze_minutes', 30)

        service = get_ticket_service()
        response = service.respond(
            ticket_id=ticket_id,
            action=action,
            user_text=user_text or None,
            snooze_minutes=snooze_minutes,
        )

        result = {
            "ticket_id": response.ticket_id,
            "action": response.action,
            "success": response.success,
        }

        if response.error:
            return jsonify({"error": response.error}), 400

        if response.snooze_until:
            result["snooze_until"] = response.snooze_until.isoformat()

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error responding to ticket: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@ticket_api_bp.route('/api/tickets/count')
def get_pending_count():
    """Quick check for pending ticket count (for badge display)."""
    try:
        ticket_manager = DI.ticket_manager
        tickets = ticket_manager.get_tickets_pending_or_proposed()

        return jsonify({"count": len(tickets)})

    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})
