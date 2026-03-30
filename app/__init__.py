# This file initializes the app package 
from flask import Flask, render_template, redirect, url_for
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
csrf = CSRFProtect()

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
    
    # Initialize Flask-Migrate
    migrate = Migrate(app, db)
    
    # Initialize system monitoring
    SystemMonitor(app, interval=300)  # Monitor every 5 minutes
    
    # # Create upload directory if it doesn't exist
    # upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'uploads')
    # if not os.path.exists(upload_dir):
    #     os.makedirs(upload_dir)

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
    
    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403
    
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400
    
    return app
