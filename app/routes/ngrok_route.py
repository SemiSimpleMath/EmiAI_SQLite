"""
Flask routes for managing ngrok tunnel
"""
from flask import Blueprint, jsonify, current_app
import subprocess
import threading
import time
import requests
import os
from app.assistant.lib.tools.send_email.utils.send_email import send_email
from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)

ngrok_route_bp = Blueprint('ngrok', __name__)

# Global variable to track ngrok process
ngrok_process = None
ngrok_url = None

def get_ngrok_url():
    """Get the public URL from ngrok API"""
    try:
        time.sleep(2)  # Wait for ngrok to initialize
        response = requests.get('http://localhost:4040/api/tunnels')
        data = response.json()
        
        if data['tunnels']:
            # Get the first HTTPS tunnel
            for tunnel in data['tunnels']:
                if tunnel['proto'] == 'https':
                    return tunnel['public_url']
            # Fallback to first tunnel if no HTTPS found
            return data['tunnels'][0]['public_url']
        return None
    except Exception as e:
        logger.error(f"Error getting ngrok URL: {e}")
        return None

def send_ngrok_email(url):
    """Send email with ngrok URL"""
    try:
        subject = "🌐 Emi Ngrok Access Link"
        message = f"""
Hello!

Your EmiAI instance is now accessible via ngrok:

🔗 URL: {url}

This link will remain active until you stop the ngrok tunnel.

Best regards,
Emi
        """
        
        from_addr = "semisimplemath@gmail.com"
        to = "semisimplemath@gmail.com"  # You can change this or make it configurable
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        username = "semisimplemath@gmail.com"
        password = os.getenv("GMAIL_APP_PASSWORD")
        
        result, error = send_email(
            subject=subject,
            message=message,
            from_addr=from_addr,
            to=to,
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            username=username,
            password=password
        )
        
        if error:
            logger.error(f"Failed to send ngrok email: {error}")
            return False
        
        logger.info(f"Ngrok email sent successfully to {to}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending ngrok email: {e}")
        return False

@ngrok_route_bp.route('/ngrok/start', methods=['POST'])
def start_ngrok():
    """Start ngrok tunnel"""
    global ngrok_process, ngrok_url
    
    try:
        if ngrok_process is not None:
            return jsonify({
                'success': False,
                'message': 'Ngrok is already running',
                'url': ngrok_url
            }), 400
        
        # Get the port from the app config or default to 8000
        port = current_app.config.get('PORT', 8000)
        
        # Start ngrok in a separate thread
        def run_ngrok():
            global ngrok_process, ngrok_url
            try:
                # Start ngrok process
                ngrok_process = subprocess.Popen(
                    ['ngrok', 'http', str(port)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Get the public URL
                ngrok_url = get_ngrok_url()
                
                if ngrok_url:
                    logger.info(f"Ngrok started successfully: {ngrok_url}")
                    # Send email with the URL
                    send_ngrok_email(ngrok_url)
                else:
                    logger.error("Failed to get ngrok URL")
                    
            except Exception as e:
                logger.error(f"Error in ngrok thread: {e}")
        
        thread = threading.Thread(target=run_ngrok, daemon=True)
        thread.start()
        
        # Wait a bit for ngrok to start
        time.sleep(3)
        
        if ngrok_url:
            return jsonify({
                'success': True,
                'message': 'Ngrok started successfully',
                'url': ngrok_url
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Ngrok started but could not retrieve URL. Check if ngrok is installed.'
            }), 500
            
    except FileNotFoundError:
        logger.error("Ngrok not found. Please install ngrok.")
        return jsonify({
            'success': False,
            'message': 'Ngrok not found. Please install ngrok from https://ngrok.com/'
        }), 500
    except Exception as e:
        logger.error(f"Error starting ngrok: {e}")
        return jsonify({
            'success': False,
            'message': f'Error starting ngrok: {str(e)}'
        }), 500

@ngrok_route_bp.route('/ngrok/stop', methods=['POST'])
def stop_ngrok():
    """Stop ngrok tunnel"""
    global ngrok_process, ngrok_url
    
    try:
        if ngrok_process is None:
            return jsonify({
                'success': False,
                'message': 'Ngrok is not running'
            }), 400
        
        # Terminate the ngrok process
        ngrok_process.terminate()
        ngrok_process.wait(timeout=5)
        ngrok_process = None
        ngrok_url = None
        
        logger.info("Ngrok stopped successfully")
        
        return jsonify({
            'success': True,
            'message': 'Ngrok stopped successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Error stopping ngrok: {e}")
        return jsonify({
            'success': False,
            'message': f'Error stopping ngrok: {str(e)}'
        }), 500

@ngrok_route_bp.route('/ngrok/status', methods=['GET'])
def ngrok_status():
    """Get ngrok status"""
    global ngrok_process, ngrok_url
    
    is_running = ngrok_process is not None
    
    return jsonify({
        'running': is_running,
        'url': ngrok_url if is_running else None
    }), 200
