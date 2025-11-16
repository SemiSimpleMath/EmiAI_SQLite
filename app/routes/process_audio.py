# app/routes/process_audio.py
from flask import request, Blueprint, jsonify, current_app
from app.assistant.ServiceLocator.service_locator import DI
from app.create_app import socketio
from app.assistant.utils.pydantic_classes import Message
import uuid
from datetime import datetime, timezone
import os
import subprocess
from werkzeug.utils import secure_filename
from app.services.speech_to_text import SpeechToTextEngineFactory

process_audio_bp = Blueprint('process_audio', __name__)
@process_audio_bp.route('/process_audio', methods=['POST'])
def process_audio():
    print("At process audio route")
    try:
        sid = request.form.get('socket_id')
        audio_output = request.form.get('audio_output', 'false').lower() == 'true'
        streaming = request.form.get('streaming', 'false').lower() == 'true'
        speaking_mode = request.form.get('speaking_mode', 'false').lower() == 'true'

        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'error': 'Empty audio file'}), 400

        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        os.makedirs(upload_folder, exist_ok=True)

        original_filename = secure_filename(audio_file.filename)
        input_path = os.path.join(upload_folder, f"{uuid.uuid4().hex}_{original_filename}")
        audio_file.save(input_path)

        print(f"📥 Original filename: {audio_file.filename}")
        print(f"📥 Saved to: {input_path}")
        print(f"📥 Detected MIME type: {audio_file.mimetype}")

        converted_path = input_path.rsplit('.', 1)[0] + '.wav'
        print(f"📥 Target WAV path: {converted_path}")

        # 🔧 Robust ffmpeg conversion
        conversion_result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ac", "1",
                "-ar", "16000",
                converted_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if conversion_result.returncode != 0:
            print("❌ FFmpeg conversion failed:")
            print(conversion_result.stderr.decode())
            return jsonify({'error': 'Audio conversion failed'}), 500

        print(f"✅ Converted file to: {converted_path}")

        # 🎙️ Transcribe with Whisper
        stt_engine = SpeechToTextEngineFactory.create_engine("whisper")
        transcribed_text = stt_engine.transcribe(converted_path)
        text = transcribed_text.text if transcribed_text else "[No transcription]"
        print(f"📝 Transcribed Text: {text}")

        # We don't send the transcribed text directly we have the UI send it.

        # # ✅ Access event_hub via DI
        # event_hub = current_app.DI.event_hub
        # if not event_hub:
        #     print("❌ event_hub not found in DI!")
        #     return jsonify({'error': 'Internal Server Error'}), 500
        #
        # event_topic = 'emi_chat_speaking_mode_request' if speaking_mode else 'emi_chat_request'
        #
        # chat_request = Message(
        #     data_type='user_message',
        #     sender='User',
        #     receiver=None,
        #     content=None,
        #     data={'socket_id': sid},
        #     timestamp=datetime.now(),
        #     id=str(uuid.uuid4()),
        #     event_topic=event_topic,
        #     agent_input=text
        # )
        #
        # event_hub.publish(chat_request)
        # print(f"✅ EventHub: Published '{event_topic}'")

        # 🧹 Clean up files
        for path in [input_path, converted_path]:
            try:
                os.remove(path)
            except Exception as e:
                print(f"⚠️ Failed to delete {path}: {e}")

        return jsonify({'transcribed_text': text}), 200

    except Exception as e:
        print(f"❌ Error during processing audio: {e}")
        return jsonify({'error': 'Processing failed'}), 500
