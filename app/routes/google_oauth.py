"""
Google OAuth Routes
Handles OAuth flow for Gmail, Calendar, and Tasks access
"""
from flask import Blueprint, redirect, url_for, request, jsonify, session
from pathlib import Path
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import os

# Allow HTTP for localhost OAuth (development only)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

google_oauth_bp = Blueprint('google_oauth', __name__)

# OAuth Scopes - all Google services we need
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',  # Required to mark emails as read
    'https://www.googleapis.com/auth/tasks'
]

def get_credentials_path():
    """Get path to credentials.json"""
    return Path(__file__).resolve().parents[2] / 'app' / 'assistant' / 'lib' / 'credentials' / 'credentials.json'

def get_token_path():
    """Get path to token.pickle"""
    return Path(__file__).resolve().parents[2] / 'app' / 'assistant' / 'lib' / 'credentials' / 'token.pickle'

def is_oauth_configured():
    """Check if OAuth credentials and token exist"""
    credentials_path = get_credentials_path()
    token_path = get_token_path()
    
    # Must have credentials.json
    if not credentials_path.exists():
        return False
    
    # Check if token exists and is valid
    if token_path.exists():
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
                if creds and creds.valid:
                    return True
                # If expired, try to refresh
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Save refreshed token
                        with open(token_path, 'wb') as token:
                            pickle.dump(creds, token)
                        return True
                    except Exception:
                        return False
        except Exception:
            return False
    
    return False

@google_oauth_bp.route('/api/oauth/google/status', methods=['GET'])
def oauth_status():
    """Check OAuth status"""
    configured = is_oauth_configured()
    return jsonify({
        'success': True,
        'configured': configured,
        'credentials_exist': get_credentials_path().exists(),
        'token_exists': get_token_path().exists()
    })

@google_oauth_bp.route('/api/oauth/google/start', methods=['GET'])
def start_oauth():
    """Start the OAuth flow"""
    try:
        credentials_path = get_credentials_path()
        
        if not credentials_path.exists():
            return jsonify({
                'success': False,
                'error': 'OAuth client credentials not found. Please contact administrator.'
            }), 400
        
        # Generate redirect URI (use HTTP for localhost, HTTPS for production)
        # Google allows HTTP for localhost/127.0.0.1 during development
        redirect_uri = url_for('google_oauth.oauth_callback', _external=True)
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='false',  # Don't include previously granted scopes - force re-consent for all scopes
            prompt='consent'  # Force consent screen to show all requested scopes
        )
        
        # Store state in session for security
        session['oauth_state'] = state
        
        # Store where to redirect after OAuth completes
        redirect_after = request.args.get('redirect_to', 'features_settings')
        session['oauth_redirect_after'] = redirect_after
        
        return jsonify({
            'success': True,
            'authorization_url': authorization_url
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to start OAuth flow: {str(e)}'
        }), 500

@google_oauth_bp.route('/oauth/google/callback')
def oauth_callback():
    """Handle OAuth callback"""
    try:
        # Verify state to prevent CSRF
        state = session.get('oauth_state')
        if not state:
            return "Error: Invalid session state", 400
        
        credentials_path = get_credentials_path()
        
        # Generate redirect URI (must match what we sent to Google)
        redirect_uri = url_for('google_oauth.oauth_callback', _external=True)
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        # Fetch token using authorization response
        flow.fetch_token(authorization_response=request.url)
        
        # Get credentials
        credentials = flow.credentials
        
        # Save credentials to token.pickle
        token_path = get_token_path()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[OAuth] Saving token to: {token_path}")
        with open(token_path, 'wb') as token:
            pickle.dump(credentials, token)
        print(f"[OAuth] Token saved successfully!")
        
        # Clear OAuth state from session
        session.pop('oauth_state', None)
        
        # Get redirect destination
        redirect_to = session.pop('oauth_redirect_after', 'features_settings')
        
        # Redirect based on where user came from
        if redirect_to == 'setup':
            return redirect(url_for('setup.setup_wizard') + '?oauth_success=true')
        else:
            return redirect(url_for('preferences.features_page') + '?oauth_success=true')
        
    except Exception as e:
        import traceback
        print(f"[OAuth] ERROR in callback: {e}")
        print(f"[OAuth] Traceback:\n{traceback.format_exc()}")
        return f"Error during OAuth: {str(e)}", 500

@google_oauth_bp.route('/api/oauth/google/revoke', methods=['POST'])
def revoke_oauth():
    """Revoke OAuth token (disconnect Google account)"""
    try:
        token_path = get_token_path()
        
        if token_path.exists():
            # Optionally revoke the token with Google first
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
                    if creds and creds.valid:
                        # Revoke token with Google
                        import requests
                        requests.post('https://oauth2.googleapis.com/revoke',
                            params={'token': creds.token},
                            headers={'content-type': 'application/x-www-form-urlencoded'})
            except Exception as e:
                print(f"Warning: Could not revoke token with Google: {e}")
            
            # Delete local token file
            token_path.unlink()
        
        return jsonify({
            'success': True,
            'message': 'Google account disconnected successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to revoke OAuth: {str(e)}'
        }), 500

