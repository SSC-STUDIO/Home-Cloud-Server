import os
import secrets
import platform
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / 'VERSION'


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

def _project_ssl_path(filename: str) -> str:
    """Get SSL file path inside project directory."""
    return str(Path(__file__).parent / 'ssl' / filename)


def read_version_file(default: str = '0.0.0') -> str:
    try:
        version = VERSION_FILE.read_text(encoding='utf-8').strip()
    except OSError:
        return default

    return version or default


def read_secret_setting(name: str) -> str | None:
    value = os.environ.get(name)
    if value:
        return value.strip() or None

    file_path = os.environ.get(f'{name}_FILE')
    if not file_path:
        return None

    try:
        secret_value = Path(file_path).read_text(encoding='utf-8').strip()
    except OSError:
        return None

    return secret_value or None

def get_base_storage_path():
    """Get the base storage path based on the operating system"""
    env_storage_path = os.environ.get('BASE_STORAGE_PATH')
    if env_storage_path:
        return Path(env_storage_path).expanduser()

    system = platform.system().lower()
    if system == 'windows':
        windows_default = Path('D:/cloud_storage')
        if Path('D:/').exists():
            return windows_default
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


# Database connection pool settings
DB_POOL_SIZE = get_env_int('DB_POOL_SIZE', 10)
DB_MAX_OVERFLOW = get_env_int('DB_MAX_OVERFLOW', 20)
DB_POOL_TIMEOUT = get_env_int('DB_POOL_TIMEOUT', 30)
DB_POOL_RECYCLE = get_env_int('DB_POOL_RECYCLE', 1800)

class Config:
    # Basic configuration
    APP_VERSION = read_version_file()
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY environment variable is required. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    if len(SECRET_KEY) < 32:
        raise ValueError("SECRET_KEY must be at least 32 characters (256 bits)")
    DEFAULT_ADMIN_PASSWORD = read_secret_setting('DEFAULT_ADMIN_PASSWORD')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # =========================================================================
    # Session Cookie Security Configuration
    # 修复漏洞: 会话Cookie安全 - 缺少Secure/HttpOnly/SameSite
    # =========================================================================
    # Session cookie secure flag - 仅通过HTTPS传输
    SESSION_COOKIE_SECURE = get_env_bool('SESSION_COOKIE_SECURE', True)
    
    # Session cookie HttpOnly flag - 防止XSS攻击访问cookie
    SESSION_COOKIE_HTTPONLY = get_env_bool('SESSION_COOKIE_HTTPONLY', True)
    
    # Session cookie SameSite flag - 防止CSRF攻击
    # 可选值: 'Strict', 'Lax', 'None'
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    
    # Session cookie name (避免使用默认的'session')
    SESSION_COOKIE_NAME = os.environ.get('SESSION_COOKIE_NAME', 'home_cloud_session')
    
    # Session permanent lifetime (默认24小时)
    PERMANENT_SESSION_LIFETIME = get_env_int('PERMANENT_SESSION_LIFETIME', 86400)
    
    # Session type (filesystem for better security than client-side cookie)
    SESSION_TYPE = os.environ.get('SESSION_TYPE', 'filesystem')
    
    # Session file directory (当SESSION_TYPE为filesystem时使用)
    SESSION_FILE_DIR = os.environ.get('SESSION_FILE_DIR', '/tmp/flask_sessions')
    
    # =========================================================================
    # Concurrent Login Detection Configuration
    # 修复漏洞: 会话验证 - 并发登录检测
    # =========================================================================
    # 是否启用并发登录检测
    CONCURRENT_LOGIN_DETECTION = get_env_bool('CONCURRENT_LOGIN_DETECTION', True)
    
    # 是否允许多设备同时登录 (False = 新登录会使旧会话失效)
    ALLOW_MULTIPLE_SESSIONS = get_env_bool('ALLOW_MULTIPLE_SESSIONS', False)
    
    # 会话过期时间（小时）
    SESSION_EXPIRE_HOURS = get_env_int('SESSION_EXPIRE_HOURS', 24)
    
    # Database connection pool configuration
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': DB_POOL_SIZE,
        'max_overflow': DB_MAX_OVERFLOW,
        'pool_timeout': DB_POOL_TIMEOUT,
        'pool_recycle': DB_POOL_RECYCLE,
    }
    
    # Cache configuration
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')  # 'simple', 'redis', 'memcached'
    CACHE_DEFAULT_TIMEOUT = get_env_int('CACHE_DEFAULT_TIMEOUT', 300)  # 5 minutes
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', 'redis://localhost:6379/0')
    CACHE_REDIS_DB = get_env_int('CACHE_REDIS_DB', 0)
    
    # Celery configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/1')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
    
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
    TRUST_PROXY_HEADERS = get_env_bool('TRUST_PROXY_HEADERS', False)
    
    # Security warning for proxy headers
    if TRUST_PROXY_HEADERS:
        import warnings
        warnings.warn(
            "TRUST_PROXY_HEADERS is enabled. "
            "Ensure your deployment is behind a trusted reverse proxy (nginx/traefik) "
            "and the proxy properly sanitizes X-Forwarded-* headers."
        )
    
    # SSL certificate configuration
    system = platform.system().lower()
    if system == 'linux':
        SSL_CERT = '/etc/ssl/certs/home-cloud.crt'
        SSL_KEY = '/etc/ssl/private/home-cloud.key'
    else:
        SSL_CERT = _project_ssl_path('home-cloud.crt')
        SSL_KEY = _project_ssl_path('home-cloud.key')
    
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
        
        # Create SSL certificate directory when SSL certs are stored in project
        if platform.system().lower() != 'linux':
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
