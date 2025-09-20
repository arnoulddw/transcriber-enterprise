# tests/functional/config/test_config.py

import os

class TestConfig:
    """
    Test configuration settings.
    """
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Fixes from errors
    DEPLOYMENT_MODE = 'multi'
    LOG_DIR = '/tmp'
    LOG_FILE = '/tmp/test_app.log'
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_ENABLED = False
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    SECRET_KEY = 'a-super-secret-key-for-testing'
    
    # Database settings
    MYSQL_USER = 'test'
    MYSQL_PASSWORD = 'test'
    MYSQL_DB = 'test_db'
    MYSQL_HOST = 'mysql-test'
    MYSQL_PORT = 3306
    MYSQL_CONFIG = {
        'host': MYSQL_HOST,
        'port': MYSQL_PORT,
        'user': MYSQL_USER,
        'password': MYSQL_PASSWORD,
        'database': MYSQL_DB,
        'pool_name': 'transcriber_test_pool',
        'pool_size': 5
    }
    
    # Other settings to prevent errors
    WTF_CSRF_ENABLED = False
    BCRYPT_LOG_ROUNDS = 4
    
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    RUNTIME_DIR = os.path.join(BASE_DIR, 'runtime')
    TASK_LOCK_FILE = os.path.join(RUNTIME_DIR, 'transcriber_task_test.lock')
    INIT_MARKER_FILE = os.path.join(RUNTIME_DIR, '.initialized_test')
    TEMP_UPLOADS_DIR = os.path.join(RUNTIME_DIR, 'test_uploads')
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'nl']
    SUPPORTED_LANGUAGE_NAMES = {
        'auto': 'Automatic Detection',
        'en': 'English',
        'nl': 'Dutch',
        'fr': 'French',
        'es': 'Spanish',
    }
    API_PROVIDER_NAME_MAP = {}
    TRANSCRIPTION_PROVIDERS = ["whisper"]
    # Add any other necessary config variables here
    MAIL_DEFAULT_SENDER = 'test@example.com'
    GOOGLE_CLIENT_ID = None
    SERVER_NAME = 'localhost'
    DEFAULT_LANGUAGE = 'en'
    DEFAULT_TRANSCRIPTION_PROVIDER = 'whisper'
    DEFAULT_TRANSCRIPTION_PROVIDER = 'whisper'