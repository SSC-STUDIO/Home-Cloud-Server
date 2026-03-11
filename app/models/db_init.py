from app.models.user import User
from app.models.file import File, Folder
from app.models.system import SystemMetric
from app.models.system_setting import SystemSetting
from app.models.activity import Activity
from app.extensions import db
from werkzeug.security import generate_password_hash
import os

def initialize_db(app):
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        max_upload_size = str(app.config.get('MAX_CONTENT_LENGTH', 1073741824))
        default_trash_retention_days = str(app.config.get('DEFAULT_TRASH_RETENTION_DAYS', 30))
        auto_clean_trash = 'true' if app.config.get('AUTO_CLEAN_TRASH', True) else 'false'
        cache_path = app.config.get('TEMP_UPLOAD_PATH', '/tmp/home_cloud_cache')

        # Create default system settings (will insert only if not already present)
        default_settings = [
            SystemSetting(key='max_upload_size', value=max_upload_size, value_type='integer', description='Maximum file size for upload (bytes)', is_advanced=False),
            SystemSetting(key='default_user_quota', value='5368709120', value_type='integer', description='Default storage quota for new users (bytes)', is_advanced=False),
            SystemSetting(key='allowed_file_types', value='*', value_type='string', description='Comma-separated list of allowed file extensions (* for all)', is_advanced=True),
            SystemSetting(key='enable_registration', value='true', value_type='boolean', description='Allow new user registrations', is_advanced=False),
            SystemSetting(key='maintenance_mode', value='false', value_type='boolean', description='Put the system in maintenance mode', is_advanced=True),
            # Cache-related settings
            SystemSetting(key='enable_cache', value='false', value_type='boolean', description='Enable file caching for previews', is_advanced=False),
            SystemSetting(key='cache_path', value=cache_path, value_type='string', description='Directory path for cache storage', is_advanced=False),
            SystemSetting(key='direct_write_upload', value='false', value_type='boolean', description='Write uploads directly to target storage without using temp cache', is_advanced=False),
            SystemSetting(key='default_trash_retention_days', value=default_trash_retention_days, value_type='integer', description='Default trash retention period (days)', is_advanced=False),
            SystemSetting(key='auto_clean_trash', value=auto_clean_trash, value_type='boolean', description='Automatically clean expired trash items', is_advanced=False)
        ]

        for setting in default_settings:
            existing = SystemSetting.query.filter_by(key=setting.key).first()
            if not existing:
                db.session.add(setting)

        db.session.commit()

        # Check if admin user already exists (create only if missing)
        admin_exists = User.query.filter_by(username='admin').first()
        if not admin_exists:
            # Create admin user
            admin = User(
                username='admin',
                email='admin@example.com',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                storage_quota=10 * 1024 * 1024 * 1024  # 10 GB
            )
            db.session.add(admin)
            db.session.commit()
            
            # Create default folders for admin
            admin_root_folder = Folder(
                name='root',
                user_id=admin.id
            )
            db.session.add(admin_root_folder)
            db.session.commit()
        
        return db 
