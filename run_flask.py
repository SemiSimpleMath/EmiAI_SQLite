# run_flask.py
import os
from pathlib import Path

# Load environment variables from .env file FIRST (before any other imports)
from dotenv import load_dotenv
dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

# Force set the environment variables BEFORE any imports
# os.environ['USE_TEST_DB'] = 'true'
# os.environ['TEST_DB_NAME'] = 'test_emidb'

from app.create_app import create_app


# Debug: Print environment variables
print("=== FLASK ENVIRONMENT DEBUG ===")
print(f"USE_TEST_DB: {os.environ.get('USE_TEST_DB')}")
print(f"DEV_DATABASE_URI_EMI: {os.environ.get('DEV_DATABASE_URI_EMI')}")
print(f"TEST_DB_NAME: {os.environ.get('TEST_DB_NAME')}")
print(f"OPENAI_API_KEY: {'✓ Set' if os.environ.get('OPENAI_API_KEY') else '✗ NOT SET'}")
print(f"TIMEZONE: {os.environ.get('TIMEZONE', 'Not set')}")
print("================================")

# Initialize the app, socketio, and event_bus
app, socketio = create_app()
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-api-key')





if __name__ == '__main__':
    # Run the SocketIO server without SSL for local development
    socketio.run(
        app,
        host='0.0.0.0',       # Listen on all interfaces
        port=8000,
        debug=False,           # Enable debug mode for development
        use_reloader=False,     # Disable the reloader for development
        allow_unsafe_werkzeug=True
    )
