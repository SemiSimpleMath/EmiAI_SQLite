# tts_module.py

import os
from flask import url_for
from flask_socketio import SocketIO
from openai import OpenAI
import tempfile
import config
import sys

from app.assistant.utils.logging_config import get_logger
logger = get_logger(__name__)

# Initialize SocketIO (This will be assigned from the main Flask app)
socketio = SocketIO()

# Initialize OpenAI client with API key from environment variables
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set.")

client = OpenAI(api_key=OPENAI_API_KEY)

def stream_audio_from_openai(text, file_path):
    try:
        print("\nGenerating audio for text:", text)
        temp_raw_path = file_path + ".raw.mp3"  # Temp file before boost

        # Save original audio to temp_raw_path
        response = client.audio.speech.create(
            model="tts-1",
            voice="nova",
            input=text,
        )
        with open(temp_raw_path, 'wb') as f:
            for chunk in response.iter_bytes(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        # Boost volume and save to final file_path
        success = boost_audio_volume(temp_raw_path, file_path, gain=2.0)
        if not success:
            print("Warning: using unboosted audio due to ffmpeg error.")
            os.rename(temp_raw_path, file_path)
        else:
            os.remove(temp_raw_path)

        print(f"Final audio file saved to: {file_path}")
    except Exception as e:
        print(f"Error in stream_audio_from_openai: {e}", file=sys.stderr)
        raise e


def create_temp_audio_file(audio_file_suffix, temp_audio_dir):
    """
    Creates a temporary file path for storing the audio file.

    Args:
        audio_file_suffix (str): The suffix for the audio file (e.g., '.mp3').
        temp_audio_dir (str): The directory where the audio file will be stored.

    Returns:
        str: The path to the temporary audio file.
    """
    try:

        # Create a temporary file in the specified directory
        fd, temp_file_path = tempfile.mkstemp(suffix=audio_file_suffix, dir=temp_audio_dir)
        os.close(fd)  # Close the file descriptor as we will write to it later
        print(f"Temporary audio file created at: {temp_file_path}")
        return temp_file_path
    except Exception as e:
        print(f"Error in create_temp_audio_file: {e}", file=sys.stderr)
        return None

def create_audio_file_path_for_web(temp_file_path):
    """
    Converts the filesystem path of the audio file to a web-accessible URL path.

    Args:
        temp_file_path (str): The filesystem path to the audio file.

    Returns:
        str: The web-accessible path to the audio file.
    """
    try:
        # Extract the filename from the absolute path
        filename = os.path.basename(temp_file_path)

        # Construct the web path relative to the 'static' folder
        web_path = os.path.join(config.DevelopmentConfig.TEMP_FOLDER_AUDIO_WEB, filename)

        # Replace backslashes with forward slashes for web compatibility (important for Windows)
        web_path = web_path.replace("\\", "/")

        print("\nWeb-accessible audio file path:", web_path)
        return web_path
    except Exception as e:
        print(f"Error in create_audio_file_path_for_web: {e}", file=sys.stderr)
        return None

def process_text(text, sid, socket_io):
    """
    Processes the given text to generate a TTS audio file and emits its URL via SocketIO.

    Args:
        text (str): The text to convert to speech.
        sid (str): The SocketIO session ID to emit the message to.
        app (Flask): The Flask application instance.
    """
    try:
        # Define paths
        temp_audio_dir = config.DevelopmentConfig.TEMP_FOLDER_AUDIO

        # Create a temporary audio file
        temp_file_path = create_temp_audio_file(
            config.DevelopmentConfig.AUDIO_FILE_SUFFIX,
            temp_audio_dir
        )

        if not temp_file_path:
            raise ValueError("Failed to create a temporary audio file.")

        # Generate and save the audio file
        stream_audio_from_openai(text, temp_file_path)

        # Create web-accessible path
        file_url = "static/" + create_audio_file_path_for_web(temp_file_path)
        if not file_url:
            raise ValueError("Failed to create web path for the audio file.")

        # Prepare the payload
        payload = {
            "message": "Audio file generated",
            "audio_url": file_url,
            "text": text
        }

        print(file_url)
        # Emit the payload to the specified SocketIO room
        socket_io.emit('audio_file', payload, room=sid)
        print(f"Audio URL emitted to room {sid}")
    except Exception as e:
        print(f"Error in process_text: {e}", file=sys.stderr)
        error_payload = {"error": str(e), "text": text}
        socket_io.emit('audio_file_error', error_payload, room=sid)
        print(f"Error payload emitted to room {sid}")


import subprocess

def boost_audio_volume(input_path, output_path, gain=2.0):
    """
    Uses ffmpeg to boost the volume of an audio file.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, "-filter:a", f"volume={gain}", output_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"Boosted volume saved to: {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Volume boost failed: {e}", file=sys.stderr)
        return False



if __name__ == "__main__":
    """
    Main block for standalone testing.
    Generates a TTS audio file from sample text and prints the file path and URL.
    Note: SocketIO emit may not work as expected in standalone mode without a running SocketIO server.
    """
    from flask import Flask

    # Sample text to convert to speech
    sample_text = "Bonjour! Le vin blanc est délicieux. Chaque chasseur sait où se trouve le lièvre."

    # Sample SocketIO session ID (for testing purposes)
    sample_sid = "test_sid_12345"

    try:
        # Define Flask app for context
        app = Flask(__name__)
        app.config.from_object('config.DevelopmentConfig')

        # Initialize SocketIO with the Flask app
        socketio.init_app(app)

        # Create a temporary audio file
        temp_file = create_temp_audio_file(
            config.DevelopmentConfig.AUDIO_FILE_SUFFIX,
            config.DevelopmentConfig.TEMP_FOLDER_AUDIO
        )
        if not temp_file:
            raise ValueError("Failed to create a temporary audio file.")

        # Generate TTS audio and save to the temporary file
        stream_audio_from_openai(sample_text, temp_file)

        # Create web-accessible path
        file_url = create_audio_file_path_for_web(temp_file)
        if not file_url:
            raise ValueError("Failed to create web path for the audio file.")

        # Generate the full URL within Flask app context
        with app.app_context():
            audio_url = url_for('static', filename=file_url, _external=True)
            print("\nGenerated Audio URL:", audio_url)

        # Prepare the payload
        payload = {
            "message": "Audio file generated",
            "audio_url": audio_url,
            "text": sample_text
        }
        print("\nPayload to emit via SocketIO:", payload)

        # Note: Emitting requires a running SocketIO server, which isn't active in this standalone script
    except Exception as e:
        print(f"Error during standalone testing: {e}", file=sys.stderr)
