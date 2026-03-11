import os
import secrets
import platform
import sys
from pathlib import Path


def get_env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default

    return value.strip().lower() in {'1', 'true', 'yes', 'on'}

def get_env_int(name, default):
    value = os.environ.get(name)
    if value is None or str(value).strip() == '':
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def expand_path(value):
    if not value:
        return None
    return str(Path(value).expanduser())

def get_base_storage_path():
    """Get the base storage path based on the operating system"""
    custom_storage_path = os.environ.get('BASE_STORAGE_PATH')
    if custom_storage_path:
        return Path(custom_storage_path).expanduser()

    system = platform.system().lower()
    if system == 'windows':
        preferred = Path(r'D:\cloud_storage')
        if os.path.exists(preferred.anchor):
            return preferred
        return Path.home() / 'cloud_storage'
    elif system == 'linux':
        if os.path.exists('/mnt/cloud_storage'):
            return Path('/mnt/cloud_storage')
        return Path.home() / 'cloud_storage'
    elif system == 'darwin':
        return Path.home() / 'cloud_storage'
    else:
        return Path(__file__).parent / 'storage'

def get_storage_path():
    """Get the uploads storage path"""
    base_path = get_base_storage_path()
    uploads_path = base_path / 'uploads'
    uploads_path.mkdir(parents=True, exist_ok=True)
    return str(uploads_path)

def get_db_path(env):
    """Get the database path based on environment and operating system"""
    base_path = get_base_storage_path()
    if env == 'development':
        db_path = Path(__file__).parent / 'dev.db'
    else:
        db_path = base_path / 'home-cloud' / 'production.db'
    
    # Ensure database directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)

class Config:
    # Basic configuration
    APP_VERSION = "1.0.0"  
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(16)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = expand_path(os.environ.get('UPLOAD_FOLDER')) or get_storage_path()
    MAX_CONTENT_LENGTH = get_env_int('MAX_CONTENT_LENGTH', 20000 * 1024 * 1024 * 1024)  # 20TB default
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mp3', 
                         'doc', 'docx', 'xls', 'xlsx', 'zip', 'rar', 'md', 'py', 
                         'js', 'css', 'html', 'json', 'xml'}
    
    # Server configuration
    USE_HTTPS = get_env_bool('USE_HTTPS', True)
    SERVER_PORT = int(os.environ.get('SERVER_PORT', 5000))
    SERVER_HOST = os.environ.get('SERVER_HOST', '0.0.0.0')
    APP_CONFIG = os.environ.get('APP_CONFIG', 'production')
    TRUST_PROXY_HEADERS = get_env_bool('TRUST_PROXY_HEADERS', True)
    
    # SSL certificate configuration
    system = platform.system().lower()
    if system == 'windows':
        SSL_CERT = str(Path(__file__).parent / 'ssl' / 'home-cloud.crt')
        SSL_KEY = str(Path(__file__).parent / 'ssl' / 'home-cloud.key')
    else:
        SSL_CERT = '/etc/ssl/certs/home-cloud.crt'
        SSL_KEY = '/etc/ssl/private/home-cloud.key'
    
    # Trash bin configuration
    TRASH_ENABLED = get_env_bool('TRASH_ENABLED', True)
    DEFAULT_TRASH_RETENTION_DAYS = get_env_int('DEFAULT_TRASH_RETENTION_DAYS', 30)
    AUTO_CLEAN_TRASH = get_env_bool('AUTO_CLEAN_TRASH', True)
    TRASH_PATH = expand_path(os.environ.get('TRASH_PATH')) or str(get_base_storage_path() / 'trash')
    
    # Transfer rate monitoring
    MONITOR_TRANSFER_SPEED = get_env_bool('MONITOR_TRANSFER_SPEED', True)
    
    # Upload configuration
    ALLOW_FOLDER_UPLOAD = get_env_bool('ALLOW_FOLDER_UPLOAD', True)
    TEMP_UPLOAD_PATH = expand_path(os.environ.get('TEMP_UPLOAD_PATH')) or str(get_base_storage_path() / 'temp')

    @staticmethod
    def init_app(app):
        """Initialize application configuration"""
        # Ensure all necessary directories exist
        paths = [
            Config.UPLOAD_FOLDER,
            Config.TRASH_PATH,
            Config.TEMP_UPLOAD_PATH,
            os.path.dirname(get_db_path('production'))
        ]
        
        for path in paths:
            os.makedirs(path, exist_ok=True)
        
        # Create SSL certificate directory on Windows
        if platform.system().lower() == 'windows':
            ssl_dir = os.path.dirname(Config.SSL_CERT)
            os.makedirs(ssl_dir, exist_ok=True)

class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or f'sqlite:///{get_db_path("development")}'
    # Development environment specific configuration
    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0

class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{get_db_path("production")}'
    # Production environment specific configuration
    PREFERRED_URL_SCHEME = 'https'

# Environment configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': ProductionConfig
}
