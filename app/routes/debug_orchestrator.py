"""
Debug Orchestrator Route - Trigger and view proactive orchestrator for debugging.
"""
from flask import Blueprint, render_template, jsonify
from datetime import datetime, timezone
from app.assistant.ServiceLocator.service_locator import DI

debug_orchestrator_bp = Blueprint('debug_orchestrator', __name__)


@debug_orchestrator_bp.route('/debug/orchestrator')
def orchestrator_page():
    """Render the orchestrator debug page."""
    return render_template('debug_orchestrator.html')


@debug_orchestrator_bp.route('/debug/orchestrator/run', methods=['POST'])
def run_orchestrator():
    """Manually trigger the proactive orchestrator."""
    try:
        from app.assistant.day_flow_manager import get_physical_pipeline_manager

        print("🎯 DEBUG: Triggering physical orchestrator stage...")
        manager = get_physical_pipeline_manager()
        stage_result = manager.run_stage("day_flow_orchestrator", reason="debug_orchestrator")
        result = stage_result.output if stage_result else {"error": "Stage not run"}
        print(f"🎯 DEBUG: Orchestrator result: {result}")
        
        return jsonify({
            "success": True,
            "result": result,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        import traceback
        print(f"🎯 DEBUG: Orchestrator error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@debug_orchestrator_bp.route('/debug/orchestrator/tickets')
def get_tickets():
    """Get all proactive tickets."""
    try:
        from app.assistant.ticket_manager import get_ticket_manager, TicketState
        from datetime import timedelta

        manager = get_ticket_manager()
        pending = [t.to_dict() for t in manager.get_tickets(state=TicketState.PENDING, limit=10)]
        proposed = [t.to_dict() for t in manager.get_tickets(state=TicketState.PROPOSED, limit=20)]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent_list = [t.to_dict() for t in manager.get_tickets(since_utc=cutoff, limit=20)]
        
        return jsonify({
            "pending": pending,
            "proposed": proposed,
            "recent": recent_list,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@debug_orchestrator_bp.route('/debug/orchestrator/ticket/<ticket_id>/accept', methods=['POST'])
def accept_ticket(ticket_id):
    """Accept a ticket."""
    try:
        manager = DI.ticket_manager
        
        success = manager.mark_accepted(ticket_id, user_response="Accepted via debug UI")
        
        return jsonify({"success": success, "ticket_id": ticket_id, "action": "accepted"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_orchestrator_bp.route('/debug/orchestrator/ticket/<ticket_id>/dismiss', methods=['POST'])
def dismiss_ticket(ticket_id):
    """Dismiss a ticket."""
    try:
        manager = DI.ticket_manager
        
        success = manager.mark_dismissed(ticket_id, reason="Dismissed via debug UI")
        
        return jsonify({"success": success, "ticket_id": ticket_id, "action": "dismissed"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@debug_orchestrator_bp.route('/debug/orchestrator/ticket/<ticket_id>/snooze', methods=['POST'])
def snooze_ticket(ticket_id):
    """Snooze a ticket for 30 minutes."""
    try:
        manager = DI.ticket_manager
        
        success = manager.mark_snoozed(ticket_id, snooze_minutes=30)
        
        return jsonify({"success": success, "ticket_id": ticket_id, "action": "snoozed", "minutes": 30})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

