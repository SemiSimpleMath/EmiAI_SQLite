from flask import Flask, render_template
from flask import Blueprint, redirect, url_for
from pathlib import Path
import json

chat_bot_bp = Blueprint('chat_bot', __name__)


def is_first_time_user():
    """Check if this is a first-time user (no setup completed)"""
    resources_dir = Path(__file__).resolve().parents[2] / 'resources'
    user_data_file = resources_dir / 'resource_user_data.json'
    return not user_data_file.exists()


def get_assistant_name():
    """Get the assistant name from config"""
    resources_dir = Path(__file__).resolve().parents[2] / 'resources'
    personality_file = resources_dir / 'resource_assistant_personality_data.json'
    
    if personality_file.exists():
        try:
            with open(personality_file, 'r') as f:
                data = json.load(f)
                return data.get('name', 'Emi')
        except:
            return 'Emi'
    return 'Emi'


@chat_bot_bp.route('/chat_bot', methods=['POST', 'GET'])
def chat_bot():
    # Redirect first-time users to setup wizard
    if is_first_time_user():
        return redirect(url_for('setup.setup_wizard'))
    
    # Get assistant name from config
    assistant_name = get_assistant_name()
    
    # No login required - direct access to chatbot
    return render_template('chat_bot.html', assistant_name=assistant_name)
