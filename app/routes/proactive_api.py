"""
Proactive Suggestions API
==========================

Endpoints for the proactive suggestion popup UI.
"""

from flask import Blueprint, jsonify, request
from datetime import datetime, timezone, timedelta

from app.assistant.utils.logging_config import get_logger
from app.assistant.ServiceLocator.service_locator import DI

logger = get_logger(__name__)

proactive_api_bp = Blueprint('proactive_api', __name__)


@proactive_api_bp.route('/api/proactive/pending')
def get_pending_suggestions():
    """
    Get suggestions ready to show to user.
    Returns tickets in PENDING or PROPOSED state.
    """
    try:
        # Using the manager ensures table is initialized
        ticket_manager = DI.ticket_manager
        
        # Get pending and proposed tickets ready to show
        tickets = ticket_manager.get_proposed_tickets_waiting()
        
        return jsonify({
            "count": len(tickets),
            "suggestions": tickets
        })
            
    except Exception as e:
        logger.error(f"Error getting pending suggestions: {e}")
        return jsonify({"error": str(e)}), 500


@proactive_api_bp.route('/api/proactive/respond', methods=['POST'])
def respond_to_suggestion():
    """
    Handle user response to a suggestion.
    
    Request body:
    {
        "ticket_id": "proactive_nutrition_...",
        "action": "done" | "skip" | "later",
        "user_text": "optional explanation from user (e.g., 'Had 2 glasses')",
        "snooze_minutes": 30  // required if action is "later"
    }
    """
    try:
        data = request.get_json()
        
        ticket_id = data.get('ticket_id')
        user_action = data.get('action')  # "done", "skip", "later"
        user_text = data.get('user_text', '')
        snooze_minutes = data.get('snooze_minutes', 30)
        
        if not ticket_id:
            return jsonify({"error": "ticket_id required"}), 400
        if user_action not in ['done', 'skip', 'later']:
            return jsonify({"error": "action must be done, skip, or later"}), 400
        
        manager = DI.ticket_manager
        
        # Get ticket and cache properties before detaching
        ticket = manager.get_ticket_by_id(ticket_id)
        is_tool_approval = False
        if ticket:
            is_tool_approval = ticket.action_type and ticket.action_type.startswith('tool_')
            
            # Store user_action and user_text
            ticket.user_action = user_action
            ticket.user_text = user_text
            manager.save_ticket(ticket)  # Save immediately to persist user input
        
        result = {
            "ticket_id": ticket_id,
            "action": user_action,
            "success": False
        }
        
        if user_action == 'done':
            success = manager.mark_accepted(ticket_id, user_response_raw=user_text)
            result["success"] = success
            
            if success:
                # Handle tool approval tickets specially (they're synchronous)
                if is_tool_approval:
                    # Tool is polling for state change, just mark accepted
                    logger.info(f"🔓 Tool approval accepted: {ticket.action_type}")
                    result["execution"] = {"success": True, "action": "tool_approval"}
                else:
                    # Wellness tickets will be processed by WellnessTicketProcessorStage
                    # which runs at the start of the next pipeline cycle
                    result["execution"] = {"success": True, "action": "accepted"}
                
        elif user_action == 'later':
            success = manager.mark_snoozed(
                ticket_id, 
                snooze_minutes=snooze_minutes,
                user_response_raw=user_text
            )
            result["success"] = success
            result["snooze_until"] = (
                datetime.now(timezone.utc) + timedelta(minutes=snooze_minutes)
            ).isoformat()
            
        elif user_action == 'skip':
            success = manager.mark_dismissed(ticket_id, user_response_raw=user_text)
            result["success"] = success
            
            # Handle tool approval rejections specially
            ticket = manager.get_ticket_by_id(ticket_id)
            if ticket and ticket.action_type and ticket.action_type.startswith('tool_'):
                _handle_tool_rejection(ticket, user_text)
        
        # Log the response
        logger.info(f"Proactive response: {ticket_id} -> {user_action} (success={result['success']})")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error responding to suggestion: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@proactive_api_bp.route('/api/proactive/count')
def get_pending_count():
    """Quick check for pending suggestion count (for badge display)."""
    try:
        # Using the manager ensures table is initialized
        ticket_manager = DI.ticket_manager
        tickets = ticket_manager.get_proposed_tickets_waiting()
        
        return jsonify({"count": len(tickets)})
            
    except Exception as e:
        return jsonify({"count": 0, "error": str(e)})


_wellness_refresh_pending = False
_wellness_refresh_lock = None

def _trigger_wellness_refresh():
    """
    Trigger a physical_status refresh in background.
    Called after ticket acceptance so wellness_activities are updated immediately.
    
    Debounced: if multiple accepts happen rapidly, only one refresh runs.
    """
    import threading
    
    global _wellness_refresh_pending, _wellness_refresh_lock
    
    if _wellness_refresh_lock is None:
        _wellness_refresh_lock = threading.Lock()
    
    with _wellness_refresh_lock:
        if _wellness_refresh_pending:
            logger.debug("Wellness refresh already pending, skipping duplicate")
            return
        _wellness_refresh_pending = True
    
    def refresh_worker():
        global _wellness_refresh_pending
        try:
            # Small delay to batch rapid accepts
            import time
            time.sleep(0.5)
            
            from app.assistant.day_flow_manager import get_physical_pipeline_manager
            manager = get_physical_pipeline_manager()
            logger.info("Event-driven wellness refresh triggered (ticket accepted)")
            manager.refresh()
            logger.info("Wellness refresh completed")
        except Exception as e:
            logger.warning(f"Could not trigger wellness refresh: {e}")
        finally:
            with _wellness_refresh_lock:
                _wellness_refresh_pending = False
    
    thread = threading.Thread(target=refresh_worker, daemon=True)
    thread.start()


def _handle_tool_rejection(ticket, user_message: str = None):
    """
    Handle when user rejects/dismisses a tool approval request.
    
    The tool is blocking/polling - it will see the 'dismissed' state
    and return an error result itself. We just log here.
    """
    action_params = ticket.action_params or {}
    tool_name = action_params.get('tool_name', 'unknown')
    
    logger.info(f"🚫 Tool rejection: {tool_name} - {ticket.title}")
    if user_message:
        logger.info(f"🚫 Reason: {user_message}")
    
    # Tool is polling and will see 'dismissed' state, then return error


