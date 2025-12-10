# app/routes/preferences.py
"""
User and Assistant preferences management
"""
from flask import Blueprint, render_template, request, jsonify
from pathlib import Path
import json
import os
from app.assistant.ServiceLocator.service_locator import DI
from jinja2 import Template

preferences_bp = Blueprint('preferences', __name__)

def get_resources_dir():
    """Get the resources directory path"""
    return Path(__file__).resolve().parents[2] / 'resources'

def update_resource_data(resource_id, json_data):
    """
    Update a resource's JSON data file and global blackboard.
    
    Templates are rendered on-demand at injection time, so we just need to update the data.
    """
    resources_dir = get_resources_dir()
    
    # Save JSON file
    json_file = resources_dir / f'{resource_id}.json'
    with open(json_file, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    # Update global blackboard - templates will use this data on next render
    if hasattr(DI, 'global_blackboard') and DI.global_blackboard:
        DI.global_blackboard.update_state_value(resource_id, json_data)

def get_project_root():
    """Get the project root directory path"""
    return Path(__file__).resolve().parents[2]

@preferences_bp.route('/preferences/general', methods=['GET'])
def user_settings_page():
    """Render user settings page"""
    return render_template('user_settings.html')

@preferences_bp.route('/settings/assistant', methods=['GET'])
def assistant_settings_page():
    """Render assistant settings page"""
    return render_template('assistant_settings.html')

@preferences_bp.route('/settings/api-keys', methods=['GET'])
def api_keys_page():
    """Render API keys settings page"""
    return render_template('api_keys_settings.html')

@preferences_bp.route('/settings/features', methods=['GET'])
def features_page():
    """Render features settings page"""
    return render_template('features_settings.html')


@preferences_bp.route('/settings/quiet-mode', methods=['GET'])
def quiet_mode_page():
    """Render quiet mode settings page"""
    return render_template('quiet_mode_settings.html')

# ============= User Profile API =============

@preferences_bp.route('/api/user-profile', methods=['GET'])
def get_user_profile():
    """Get user profile data"""
    try:
        resources_dir = get_resources_dir()
        user_data_file = resources_dir / 'resource_user_data.json'
        
        if not user_data_file.exists():
            return jsonify({'success': False, 'error': 'User profile not found'}), 404
        
        with open(user_data_file, 'r') as f:
            user_data = json.load(f)
        
        return jsonify({'success': True, 'profile': user_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@preferences_bp.route('/api/user-profile', methods=['PUT'])
def update_user_profile():
    """Update user profile data"""
    try:
        data = request.json
        
        # Split pronouns into subjective/objective
        pronouns_str = data.get('pronouns', 'they/them')
        pronouns = pronouns_str.split('/')
        pronoun_subjective = pronouns[0] if len(pronouns) > 0 else 'they'
        pronoun_objective = pronouns[1] if len(pronouns) > 1 else 'them'
        
        user_data = {
            'first_name': data.get('first_name'),
            'middle_name': data.get('middle_name'),
            'last_name': data.get('last_name'),
            'preferred_name': data.get('preferred_name'),
            'full_name': data.get('full_name'),
            'pronouns': {
                'subjective': pronoun_subjective,
                'objective': pronoun_objective
            },
            'birthdate': data.get('birthdate'),
            'job': data.get('job'),
            'additional_context': data.get('additional_context'),
            'important_people': data.get('important_people', [])
        }
        
        # Save to file and reload resources
        resources_dir = get_resources_dir()
        resources_dir.mkdir(exist_ok=True)
        update_resource_data('resource_user_data', user_data)
        
        # TODO: Update entity cards for user and important people
        
        return jsonify({'success': True, 'message': 'User profile updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= Assistant Personality API =============

@preferences_bp.route('/api/assistant-personality', methods=['GET'])
def get_assistant_personality():
    """Get assistant personality data"""
    try:
        resources_dir = get_resources_dir()
        personality_file = resources_dir / 'resource_assistant_personality_data.json'
        
        if not personality_file.exists():
            return jsonify({'success': True, 'data': {'name': 'Emi'}})
        
        with open(personality_file, 'r') as f:
            personality_data = json.load(f)
        
        return jsonify({'success': True, 'data': personality_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@preferences_bp.route('/api/assistant-personality', methods=['PUT'])
def update_assistant_personality():
    """Update assistant personality data"""
    try:
        data = request.json
        
        personality_data = {
            'name': data.get('name', 'Emi'),
            'personality': data.get('personality'),
            'backstory': data.get('backstory')
        }
        
        # Save to file and reload resources
        resources_dir = get_resources_dir()
        resources_dir.mkdir(exist_ok=True)
        update_resource_data('resource_assistant_personality_data', personality_data)
        
        return jsonify({'success': True, 'message': 'Assistant personality updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= Relationship Config API =============

@preferences_bp.route('/api/assistant-relationship', methods=['GET'])
def get_assistant_relationship():
    """Get assistant relationship config"""
    try:
        resources_dir = get_resources_dir()
        relationship_file = resources_dir / 'resource_relationship_config.json'
        
        if not relationship_file.exists():
            return jsonify({'success': True, 'data': {'type': 'friend', 'description': '', 'role': ''}})
        
        with open(relationship_file, 'r') as f:
            relationship_data = json.load(f)
        
        return jsonify({'success': True, 'data': relationship_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@preferences_bp.route('/api/assistant-relationship', methods=['PUT'])
def update_assistant_relationship():
    """Update assistant relationship config"""
    try:
        data = request.json
        
        relationship_data = {
            'type': data.get('type', 'friend'),
            'description': data.get('description', ''),
            'role': data.get('role', '')
        }
        
        # Save to file
        resources_dir = get_resources_dir()
        resources_dir.mkdir(exist_ok=True)
        
        relationship_file = resources_dir / 'resource_relationship_config.json'
        with open(relationship_file, 'w') as f:
            json.dump(relationship_data, f, indent=2)
        
        # Update global blackboard for immediate effect
        if hasattr(DI, 'resource_manager') and DI.resource_manager:
            DI.resource_manager.update_resource('resource_relationship_config', relationship_data, persist=False)
        
        return jsonify({'success': True, 'message': 'Relationship config updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= Chat Guidelines API =============

@preferences_bp.route('/api/chat-guidelines', methods=['GET'])
def get_chat_guidelines():
    """Get chat guidelines"""
    try:
        resources_dir = get_resources_dir()
        guidelines_file = resources_dir / 'resource_chat_guidelines_data.json'
        
        if not guidelines_file.exists():
            return jsonify({'success': True, 'data': {'style': 'direct', 'guidelines': ''}})
        
        with open(guidelines_file, 'r') as f:
            guidelines_data = json.load(f)
        
        return jsonify({'success': True, 'data': guidelines_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@preferences_bp.route('/api/chat-guidelines', methods=['PUT'])
def update_chat_guidelines():
    """Update chat guidelines"""
    try:
        data = request.json
        
        guidelines_data = {
            'style': data.get('style', 'direct'),
            'guidelines': data.get('guidelines', '')
        }
        
        # Save to file and reload resources
        resources_dir = get_resources_dir()
        resources_dir.mkdir(exist_ok=True)
        update_resource_data('resource_chat_guidelines_data', guidelines_data)
        
        return jsonify({'success': True, 'message': 'Chat guidelines updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= Environment Settings API =============

@preferences_bp.route('/api/env-settings', methods=['GET'])
def get_env_settings():
    """Get environment settings (non-sensitive values only)"""
    try:
        project_root = get_project_root()
        env_file = project_root / '.env'
        
        env_content = {}
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_content[key.strip()] = value.strip()
        
        # Return non-sensitive values only
        settings = {
            'timezone': env_content.get('TIMEZONE', ''),
            'email_addr': env_content.get('EMAIL_ADDR', ''),
            'email_imap_url': env_content.get('EMAIL_IMAP_URL', 'imap.gmail.com')
        }
        
        return jsonify({'success': True, 'settings': settings})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@preferences_bp.route('/api/env-settings', methods=['PUT'])
def update_env_settings():
    """Update environment settings (.env file)"""
    try:
        data = request.json
        
        project_root = get_project_root()
        env_file = project_root / '.env'
        
        # Read existing .env if it exists
        env_content = {}
        if env_file.exists():
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_content[key.strip()] = value.strip()
        
        # Update with new values (only if provided)
        if data.get('openai_api_key'):
            env_content['OPENAI_API_KEY'] = data['openai_api_key']
        
        if data.get('google_api_key'):
            env_content['GOOGLE_API_KEY'] = data['google_api_key']
        
        if data.get('anthropic_api_key'):
            env_content['ANTHROPIC_API_KEY'] = data['anthropic_api_key']
        
        if data.get('elevenlabs_api_key'):
            env_content['ELEVENLABS_API_KEY'] = data['elevenlabs_api_key']
        
        if data.get('deepgram_api_key'):
            env_content['DEEPGRAM_API_KEY'] = data['deepgram_api_key']
        
        if data.get('timezone'):
            env_content['TIMEZONE'] = data['timezone']
        
        if data.get('gmail_address'):
            env_content['EMAIL_ADDR'] = data['gmail_address']
        
        if data.get('gmail_app_password'):
            env_content['EMAIL_PASSWORD'] = data['gmail_app_password']
            env_content['EMAIL_IMAP_URL'] = 'imap.gmail.com'
        
        # Write back to .env
        with open(env_file, 'w') as f:
            f.write("# Emi Configuration\n")
            f.write(f"# Updated: {Path(__file__).name}\n\n")
            
            # Core settings
            if 'OPENAI_API_KEY' in env_content:
                f.write("# Core Settings\n")
                f.write(f"OPENAI_API_KEY={env_content['OPENAI_API_KEY']}\n")
                f.write(f"TIMEZONE={env_content.get('TIMEZONE', '')}\n\n")
            
            # Optional API keys
            optional_keys = ['GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 'DEEPGRAM_API_KEY']
            has_optional = any(key in env_content for key in optional_keys)
            if has_optional:
                f.write("# Optional API Keys\n")
                for key in optional_keys:
                    if key in env_content:
                        f.write(f"{key}={env_content[key]}\n")
                f.write("\n")
            
            # Email settings
            if 'EMAIL_ADDR' in env_content:
                f.write("# Gmail Integration\n")
                f.write(f"EMAIL_ADDR={env_content['EMAIL_ADDR']}\n")
                if 'EMAIL_PASSWORD' in env_content:
                    f.write(f"EMAIL_PASSWORD={env_content['EMAIL_PASSWORD']}\n")
                f.write(f"EMAIL_IMAP_URL={env_content.get('EMAIL_IMAP_URL', 'imap.gmail.com')}\n\n")
            
            # Write any other existing keys
            skip_keys = ['OPENAI_API_KEY', 'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'ELEVENLABS_API_KEY', 
                        'DEEPGRAM_API_KEY', 'TIMEZONE', 'EMAIL_ADDR', 'EMAIL_PASSWORD', 'EMAIL_IMAP_URL']
            for key, value in env_content.items():
                if key not in skip_keys:
                    f.write(f"{key}={value}\n")
        
        return jsonify({'success': True, 'message': 'Environment settings updated'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

