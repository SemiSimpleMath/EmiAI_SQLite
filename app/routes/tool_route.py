from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
import uuid

from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI

tool_route_bp = Blueprint('tool_route', __name__)

@tool_route_bp.route('/tool/', methods=['POST'])
def handle_tool_route():

    print("At tool route")

    try:
        data = request.get_json()

        print(data)

        msg = Message(
            data_type="tool_request",
            sender="User",
            receiver=None,
            content="Update task status",
            timestamp=datetime.now(timezone.utc),
            id=str(uuid.uuid4()),
            event_topic = 'ui_tool_caller',
            data = data
        )

        result = DI.event_hub.publish(msg)

        response = {
            "success": True,
            "message": "Task update sent",
        }

        if hasattr(result, "content") and result.content:
            response["agent_response"] = result.content

        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"Error handling todo update: {e}")
        return jsonify({'success': False, 'message': 'Error processing todo update'}), 500
