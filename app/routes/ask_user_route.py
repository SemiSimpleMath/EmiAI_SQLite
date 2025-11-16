from flask import Blueprint, jsonify, request
from app.assistant.utils.pydantic_classes import Message
from app.assistant.ServiceLocator.service_locator import DI

ask_user_route_bp = Blueprint('ask_user_route', __name__)

@ask_user_route_bp.route('/ask_user_answer', methods=['POST'])
def ask_user_answer():
    data = request.get_json()
    question_id = data.get("question_id")
    answer = data.get("answer")

    print(f"Received ask_user response:")
    print(f" - Question ID: {question_id}")
    print(f" - Answer: {answer}")

    if not question_id or answer is None:
        return jsonify({'success': False, 'error': 'Missing question_id or answer'}), 400

    # Create the message to send back to the tool
    msg = Message(
        sender="user",
        receiver=None,
        data={
            "question_id": question_id,
            "answer": answer
        }
    )
    msg.event_topic = f"ask_user_{question_id}"

    # Publish it to unblock the tool
    DI.event_hub.publish(msg)

    return jsonify({'success': True, 'status': 'Answer delivered to tool'}), 200
