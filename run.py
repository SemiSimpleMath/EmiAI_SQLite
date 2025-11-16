import os
import ssl
import eventlet
from pathlib import Path

# Load environment variables from .env file FIRST
from dotenv import load_dotenv
dotenv_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=dotenv_path)

from app import create_app

app, socketio = create_app()
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default-api-key')

if __name__ == '__main__':
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain('cert.pem', 'key.pem')

    # Wrap the socket to add SSL support
    listener = eventlet.listen(('', 8000))
    ssl_listener = eventlet.wrap_ssl(listener, certfile='cert.pem', keyfile='key.pem', server_side=True)

    # Run the app
    eventlet.wsgi.server(ssl_listener, app)
