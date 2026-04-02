# This file initializes the app package 
from flask import Flask, render_template, redirect, url_for, request, session
import os
from config import config
from app.models.db_init import initialize_db
from datetime import datetime
from app.utils.system_monitor import SystemMonitor
from flask_migrate import Migrate
import ssl
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_wtf.csrf import CSRFProtect
from app.utils.performance import init_cache, PerformanceMonitor
from app.security_middleware import init_security_headers, SecurityHeaders
from app.security_policy import init_security_logging, log_security_event, SecureErrorHandler
from flask_session import Session  # 修复: 服务器端session支持

csrf = CSRFProtect()
session_manager = Session()  # 修复: 初始化Flask-Session

def create_app(config_name='default'):
    if config_name == 'default':
        config_name = os.environ.get('APP_CONFIG', 'production')
    if config_name not in config:
        config_name = 'default'

    # Specify the template folder explicitly
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir)
    app.config.from_object(config[config_name])
    if hasattr(config[config_name], 'init_app'):
        config[config_name].init_app(app)

    if app.config.get('TRUST_PROXY_HEADERS', True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
    
    # Ensure custom temp directory (for large file uploads) is used system-wide
    temp_dir = app.config.get('TEMP_UPLOAD_PATH')
    if temp_dir:
        try:
            os.makedirs(temp_dir, exist_ok=True)
            # Set environment variables recognized by tempfile
            os.environ['TMPDIR'] = temp_dir
            os.environ['TEMP'] = temp_dir
            os.environ['TMP'] = temp_dir

            # Also set Python's internal default tempdir for current process
            import tempfile
            tempfile.tempdir = temp_dir
        except Exception as e:
            # Log a warning but continue; fallback to default tmp if failed
            print(f"Warning: unable to set custom temp directory {temp_dir}: {e}")
    
    # Initialize database
    db = initialize_db(app)
    
    # Initialize cache
    init_cache(app)
    
    # Initialize performance monitoring
    PerformanceMonitor(app)
    
    # Initialize CSRF protection
    csrf.init_app(app)
    
    # =========================================================================
    # Initialize Server-Side Session Management
    # 修复漏洞: 会话Cookie安全 - 使用服务器端session更安全
    # =========================================================================
    if app.config.get('SESSION_TYPE') == 'filesystem':
        session_file_dir = app.config.get('SESSION_FILE_DIR', '/tmp/flask_sessions')
        os.makedirs(session_file_dir, exist_ok=True)
    
    session_manager.init_app(app)
    
    # 添加Session安全管理请求处理器
    @app.before_request
    def session_security_checks():
        """
        请求前的session安全检查
        1. 验证session是否过期
        2. 检测IP地址变化（可选）
        3. 更新最后活动时间
        """
        if 'user_id' in session:
            from datetime import datetime
            
            # 更新最后活动时间
            session['last_activity'] = datetime.utcnow().isoformat()
            
            # 如果启用了并发登录检测，验证会话有效性
            if app.config.get('CONCURRENT_LOGIN_DETECTION', True):
                from app.models.user_session import UserSession
                
                session_token = session.get('session_token')
                if session_token:
                    is_valid, session_obj, message = UserSession.validate_session(
                        session_token,
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string if request.user_agent else None
                    )
                    
                    if not is_valid:
                        # Session无效，清除并记录
                        log_security_event(
                            'session_validation_failed',
                            f"Session validation failed: {message}",
                            user_id=session.get('user_id'),
                            level='WARNING'
                        )
                        session.clear()
                        from flask import flash
                        flash('Your session has expired or is invalid. Please log in again.', 'warning')
                        return redirect(url_for('auth.login'))
    
    # Initialize Flask-Migrate
    migrate = Migrate(app, db)
    
    # Initialize system monitoring
    SystemMonitor(app, interval=300)  # Monitor every 5 minutes
    
    # Initialize security headers
    init_security_headers(app)
    
    # Initialize security logging
    init_security_logging(app)
    
    # Register blueprints
    from app.routes.auth import auth as auth_blueprint
    from app.routes.files import files as files_blueprint
    from app.routes.admin import admin as admin_blueprint
    from app.routes.api import api as api_blueprint
    from app.routes.files_optimized import files_optimized as files_optimized_blueprint
    
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(files_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(files_optimized_blueprint)
    
    # Add template globals
    @app.context_processor
    def inject_app_vars():
        return {
            'now': datetime.now,
            'app_version': app.config.get('APP_VERSION', '0.0.0')
        }
    
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.route('/healthz')
    def healthz():
        return {'status': 'ok', 'version': app.config.get('APP_VERSION', '0.0.0')}, 200
    
    # =========================================================================
    # 安全错误处理
    # =========================================================================
    
    @app.errorhandler(404)
    def page_not_found(e):
        # 记录404错误
        log_security_event(
            'page_not_found',
            f"404 error for {request.path}",
            level='INFO'
        )
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        # 记录500错误（不包含敏感信息）
        log_security_event(
            'server_error',
            f"500 error: {type(e).__name__}",
            level='ERROR'
        )
        # 返回安全的错误消息
        flash('服务器内部错误，请稍后重试', 'danger')
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        # 记录403错误
        log_security_event(
            'access_forbidden',
            f"403 error for {request.path}",
            level='WARNING'
        )
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(400)
    def bad_request(e):
        # 记录400错误
        log_security_event(
            'bad_request',
            f"400 error for {request.path}",
            level='INFO'
        )
        return render_template('errors/400.html'), 400
    
    @app.errorhandler(429)  # Rate limit exceeded
    def rate_limit_handler(e):
        log_security_event(
            'rate_limit_exceeded',
            f"Rate limit exceeded for {request.path}",
            level='WARNING'
        )
        flash('请求过于频繁，请稍后再试', 'danger')
        return render_template('errors/429.html'), 429
    
    @app.errorhandler(Exception)
    def handle_unhandled_exception(e):
        """处理未捕获的异常，避免泄露敏感信息"""
        # 记录异常（使用安全的日志消息）
        log_security_event(
            'unhandled_exception',
            f"Unhandled {type(e).__name__}: {str(e)[:100]}",
            level='ERROR'
        )
        # 返回通用错误页面
        return render_template('errors/500.html'), 500
    
    # 记录应用启动
    with app.app_context():
        log_security_event(
            'app_startup',
            f"Application started in {config_name} mode",
            level='INFO'
        )
    
    return app
