"""
User Settings Routes
API endpoints for managing user settings
"""

from flask import Blueprint, jsonify, request
from app.assistant.user_settings_manager.user_settings import get_settings_manager
from app.assistant.ServiceLocator.service_locator import DI

user_settings_bp = Blueprint('user_settings', __name__)


def notify_settings_changed():
    """Publish settings_changed event to EventHub"""
    try:
        if hasattr(DI, 'event_hub') and DI.event_hub:
            from app.assistant.utils.pydantic_classes import Message
            msg = Message(content="Settings updated")
            msg.event_topic = "settings_changed"
            DI.event_hub.publish(msg)
    except Exception as e:
        print(f"Warning: Could not publish settings_changed event: {e}")


@user_settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    """Get all user settings (public, no API keys)"""
    try:
        settings_manager = get_settings_manager()
        public_settings = settings_manager.get_public_settings()
        
        return jsonify({
            'success': True,
            'settings': public_settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving settings: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/<setting_key>', methods=['GET'])
def get_setting(setting_key):
    """Get a specific setting value"""
    try:
        settings_manager = get_settings_manager()
        value = settings_manager.get(setting_key)
        
        return jsonify({
            'success': True,
            'key': setting_key,
            'value': value
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving setting: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/<setting_key>', methods=['PUT'])
def update_setting(setting_key):
    """Update a specific setting value"""
    try:
        data = request.get_json()
        
        if 'value' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing "value" in request body'
            }), 400
        
        settings_manager = get_settings_manager()
        settings_manager.set(setting_key, data['value'])
        
        # Notify that settings changed
        notify_settings_changed()
        
        return jsonify({
            'success': True,
            'key': setting_key,
            'value': data['value'],
            'message': 'Setting updated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error updating setting: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/api-keys/status', methods=['GET'])
def get_api_keys_status():
    """Get status of API keys from environment variables (whether they're set, not the actual keys)"""
    try:
        settings_manager = get_settings_manager()
        
        providers = ['openai', 'google', 'anthropic', 'elevenlabs', 'deepgram']
        status = {}
        
        for provider in providers:
            api_key = settings_manager.get_api_key(provider)
            status[provider] = {
                'configured': bool(api_key and api_key.strip()),
                'source': 'environment_variable'
            }
        
        return jsonify({
            'success': True,
            'api_keys': status,
            'note': 'API keys are read from environment variables only'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving API key status: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/features', methods=['GET'])
def get_features():
    """Get all feature flags"""
    try:
        settings_manager = get_settings_manager()
        features = settings_manager.get('features', {})
        
        # Auto-disable features that can't run (missing OAuth/API keys)
        availability = settings_manager.get_available_features()
        for feature_name, status in availability.items():
            feature_key = f"enable_{feature_name}"
            if feature_key in features:
                # If feature is enabled but missing requirements, auto-disable it
                if features[feature_key] and not status['can_enable']:
                    features[feature_key] = False
                    settings_manager.enable_feature(feature_name, False)
        
        return jsonify({
            'success': True,
            'features': features
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving features: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/features/availability', methods=['GET'])
def get_features_availability():
    """Get feature availability status based on dependencies"""
    try:
        settings_manager = get_settings_manager()
        availability = settings_manager.get_available_features()
        
        return jsonify({
            'success': True,
            'features': availability
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving feature availability: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/features/<feature_name>/check', methods=['GET'])
def check_feature_availability(feature_name):
    """Check if a specific feature can be enabled"""
    try:
        settings_manager = get_settings_manager()
        check_result = settings_manager.check_feature_can_be_enabled(feature_name)
        
        return jsonify({
            'success': True,
            'feature': feature_name,
            'availability': check_result
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error checking feature availability: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/features/<feature_name>', methods=['PUT'])
def toggle_feature(feature_name):
    """Toggle a feature on/off"""
    try:
        data = request.get_json()
        
        if 'enabled' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing "enabled" in request body'
            }), 400
        
        settings_manager = get_settings_manager()
        settings_manager.enable_feature(feature_name, data['enabled'])
        
        # Notify that settings changed
        notify_settings_changed()
        
        return jsonify({
            'success': True,
            'feature': feature_name,
            'enabled': data['enabled'],
            'message': f'Feature {feature_name} {"enabled" if data["enabled"] else "disabled"}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error toggling feature: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/preferences', methods=['GET'])
def get_preferences():
    """Get all user preferences"""
    try:
        settings_manager = get_settings_manager()
        preferences = settings_manager.get('preferences', {})
        
        return jsonify({
            'success': True,
            'preferences': preferences
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error retrieving preferences: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/preferences/<pref_name>', methods=['PUT'])
def update_preference(pref_name):
    """Update a user preference"""
    try:
        data = request.get_json()
        
        if 'value' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing "value" in request body'
            }), 400
        
        settings_manager = get_settings_manager()
        settings_manager.set_preference(pref_name, data['value'])
        
        # Notify that settings changed
        notify_settings_changed()
        
        return jsonify({
            'success': True,
            'preference': pref_name,
            'value': data['value'],
            'message': f'Preference {pref_name} updated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error updating preference: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/validate', methods=['GET'])
def validate_settings():
    """Validate current settings"""
    try:
        settings_manager = get_settings_manager()
        validation_result = settings_manager.validate_settings()
        
        return jsonify({
            'success': True,
            'validation': validation_result,
            'is_valid': len(validation_result['errors']) == 0
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error validating settings: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/export', methods=['GET'])
def export_settings():
    """Export settings (without API keys)"""
    try:
        settings_manager = get_settings_manager()
        public_settings = settings_manager.get_public_settings()
        
        return jsonify({
            'success': True,
            'settings': public_settings,
            'timestamp': settings_manager.get('system.last_updated')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error exporting settings: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/import', methods=['POST'])
def import_settings():
    """Import settings"""
    try:
        data = request.get_json()
        
        if 'settings' not in data:
            return jsonify({
                'success': False,
                'message': 'Missing "settings" in request body'
            }), 400
        
        settings_manager = get_settings_manager()
        
        # Merge imported settings
        merge = data.get('merge', True)
        for key, value in data['settings'].items():
            if key not in ['_comment', '_warning']:  # Skip metadata
                settings_manager.set(key, value, save=False)
        
        # Save once at the end
        settings_manager._save_settings()
        
        return jsonify({
            'success': True,
            'message': 'Settings imported successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error importing settings: {str(e)}'
        }), 500


@user_settings_bp.route('/api/settings/reset', methods=['POST'])
def reset_settings():
    """Reset settings to defaults (requires confirmation)"""
    try:
        data = request.get_json() or {}
        
        if not data.get('confirm'):
            return jsonify({
                'success': False,
                'message': 'Reset requires confirmation: set "confirm": true in request body'
            }), 400
        
        settings_manager = get_settings_manager()
        settings_manager.reset_to_defaults()
        
        return jsonify({
            'success': True,
            'message': 'Settings reset to defaults successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error resetting settings: {str(e)}'
        }), 500

