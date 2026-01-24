"""
Wellness Management Route - Reset and manage wellness tracking data.
"""
from flask import Blueprint, jsonify
from datetime import datetime, timezone
import json
from pathlib import Path
from app.assistant.utils.path_utils import get_resources_dir

wellness_mgmt_bp = Blueprint('wellness_mgmt', __name__)


@wellness_mgmt_bp.route('/debug/wellness/reset', methods=['POST'])
def reset_wellness():
    """Reset all wellness tracking data to defaults."""
    try:
        from app.assistant.day_flow_manager import get_physical_pipeline_manager
        from app.assistant.ticket_manager import get_ticket_manager

        results = {}

        manager = get_physical_pipeline_manager()
        results["pipeline_reset"] = manager.force_daily_reset()
        
        # Clear proactive tickets
        try:
            ticket_manager = get_ticket_manager()
            deleted_count = ticket_manager.clear_all_tickets()
            results["proactive_tickets_cleared"] = deleted_count
        except Exception as e:
            results["proactive_tickets_error"] = str(e)
        
        return jsonify({
            "success": True,
            "message": "Wellness tracking reset to defaults",
            "results": results
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@wellness_mgmt_bp.route('/debug/wellness/status')
def wellness_status():
    """Get current wellness tracking status."""
    try:
        resources_dir = get_resources_dir()

        def load_resource(filename):
            filepath = resources_dir / filename
            try:
                return json.loads(filepath.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {"_not_generated_yet": True}
            except Exception as e:
                return {"error": str(e)}

        pipeline_state = load_resource("resource_wellness_pipeline_status.json")
        tracked_activities = load_resource("resource_tracked_activities_output.json")
        sleep_output = load_resource("resource_sleep_output.json")

        return jsonify({
            "pipeline_state": pipeline_state,
            "tracked_activities": tracked_activities,
            "sleep_output": sleep_output,
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
