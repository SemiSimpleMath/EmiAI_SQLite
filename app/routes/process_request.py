# app/routes/process_request.py

from flask import request, Blueprint, jsonify, current_app
from app.assistant.utils.pydantic_classes import Message
import uuid
from datetime import datetime

process_request_bp = Blueprint('process_request', __name__)

from app.assistant.utils.logging_config import get_logger
from app.assistant.performance.performance_monitor import performance_monitor
logger = get_logger(__name__)


@process_request_bp.route('/process_request', methods=['POST'])
def process_request():
    timer_id = performance_monitor.start_timer('process_request', str(uuid.uuid4()))
    
    try:
        sid = request.form['socket_id']
        text = request.form.get('text')
        speaking_mode = request.form.get('speaking_mode')
        
        # Check for mode flags and set DI state
        is_test_mode = request.form.get('test') == 'true'
        is_memo_mode = request.form.get('memo') == 'true'
        
        print("Speaking mode: ", speaking_mode)
        print("Test mode: ", is_test_mode)
        print("Memo mode: ", is_memo_mode)
        
        if not text:
            performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'No text provided'})
            return jsonify({'error': 'No text provided'}), 400

        # Set DI mode flags
        from app.assistant.ServiceLocator.service_locator import ServiceLocator
        if is_memo_mode:
            ServiceLocator.set_memo_mode(True)
        elif is_test_mode:
            ServiceLocator.set_test_mode(True)
        else:
            ServiceLocator.set_normal_mode()

        # Handle memo mode (direct database storage, no agent processing)
        if is_memo_mode:
            return handle_memo_mode(text, sid, timer_id)
        
        # Normal processing (test mode or normal mode)
        return handle_normal_processing(text, sid, speaking_mode, timer_id)
            
    except Exception as e:
        logger.exception(f"Error during processing request: {e}")
        performance_monitor.end_timer(timer_id, {'status': 'error', 'error': str(e)})
        return jsonify({'error': 'Processing failed'}), 500


def handle_memo_mode(text, socket_id, timer_id):
    """Memo mode: Direct database storage, no agent processing"""
    try:
        # Save directly to unified_log
        from app.assistant.database.db_handler import UnifiedLog
        from app.models.base import get_session
        
        session = get_session()
        memo_entry = UnifiedLog(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            role='user',
            message=text,
            source='chat',
            processed=False
        )
        session.add(memo_entry)
        session.commit()
        session.close()
        
        logger.info(f"📝 Memo saved: {text[:50]}...")
        performance_monitor.end_timer(timer_id, {'status': 'success', 'mode': 'memo'})
        return jsonify({'message': 'Memo saved successfully'}), 200
        
    except Exception as e:
        logger.exception(f"Error in memo mode: {e}")
        performance_monitor.end_timer(timer_id, {'status': 'error', 'error': str(e)})
        return jsonify({'error': 'Failed to save memo'}), 500


def handle_normal_processing(text, socket_id, speaking_mode, timer_id):
    """Unified processing for both test and normal modes"""
    try:
        # ✅ Access event_hub via DI
        event_hub = current_app.DI.event_hub
        if not event_hub:
            logger.error("❌ event_hub not found in DI!")
            performance_monitor.end_timer(timer_id, {'status': 'error', 'error': 'event_hub not found'})
            return jsonify({'error': 'Internal Server Error'}), 500

        if speaking_mode == "true":
            event_topic = 'emi_chat_speaking_mode_request'
        else:
            event_topic = 'emi_chat_request'

        # Construct the UserMessage object
        chat_request = Message(
            data_type='user_message',
            sender='User',
            receiver=None,
            content=None,
            data={'socket_id': socket_id},
            timestamp=datetime.now(),
            id=str(uuid.uuid4()),
            event_topic=event_topic,
            agent_input=text,
            role='user'
        )

        # ✅ Directly publish to event_hub
        event_hub.publish(chat_request)
        logger.info(f"✅ EventHub: Published '{event_topic}' event.")

        performance_monitor.end_timer(timer_id, {'status': 'success', 'event_topic': event_topic})
        return jsonify({'message': 'Request sent to event hub'}), 200

    except Exception as e:
        logger.exception(f"Error during processing request: {e}")
        performance_monitor.end_timer(timer_id, {'status': 'error', 'error': str(e)})
        return jsonify({'error': 'Processing failed'}), 500

