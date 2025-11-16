# config.py
import os

# Import the unified database configuration
try:
    from app.models.base import get_database_uri
except ImportError:
    # Fallback for when app.models.base is not available
    def get_database_uri():
        if os.environ.get('USE_TEST_DB') == 'true':
            # Test database configuration - prefer explicit TEST_DATABASE_URI_EMI
            test_db_uri = os.environ.get('TEST_DATABASE_URI_EMI')
            if not test_db_uri:
                # Fallback to default test database name
                dev_uri = os.environ.get('DEV_DATABASE_URI_EMI', '')
                test_db_name = os.environ.get('TEST_DB_NAME', 'test_emidb')
                test_db_uri = dev_uri.rsplit('/', 1)[0] + '/' + test_db_name
            return test_db_uri
        else:
            # Production/development database
            return os.environ.get('DEV_DATABASE_URI_EMI')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'default-secret-key'
    OPEN_AI = os.environ.get('OPENAI_API_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'default-secret-key'

class DevelopmentConfig(Config):
    DEBUG = True
    TEMP_FOLDER_AUDIO = os.path.join('app', 'static', 'temp_audio')
    TEMP_FOLDER_AUDIO_WEB = "temp_audio/"
    AUDIO_FILE_SUFFIX = '.mp3'
    TEMP_FOLDER_IMAGE = os.path.join('app', 'static', 'temp_image')
    # Database configuration - uses unified source of truth
    SQLALCHEMY_DATABASE_URI = get_database_uri()

class TestConfig(Config):
    TESTING = True
    # Database configuration - uses unified source of truth
    SQLALCHEMY_DATABASE_URI = get_database_uri()
    TEMP_FOLDER_AUDIO = os.path.join('app', 'static', 'temp_audio')
    TEMP_FOLDER_AUDIO_WEB = "/static/temp_audio/"
    AUDIO_FILE_SUFFIX = '.mp3'
    TEMP_FOLDER_IMAGE = os.path.join('app', 'static', 'temp_image')

class ProductionConfig(Config):
    DEBUG = False

class HerokuConfig(Config):
    DEBUG = True
    TEMP_FOLDER_AUDIO = os.path.join('app', 'static', 'temp_audio')
    TEMP_FOLDER_AUDIO_WEB = "/static/temp_audio/"
    AUDIO_FILE_SUFFIX = '.mp3'
    TEMP_FOLDER_IMAGE = os.path.join('app', 'static', 'temp_image')
    uri = os.getenv("DATABASE_URL")  # or other relevant config var
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = uri