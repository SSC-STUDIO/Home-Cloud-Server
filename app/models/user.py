from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from ..extensions import db

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='user')  # 'user' or 'admin'
    storage_quota = db.Column(db.BigInteger, default=5 * 1024 * 1024 * 1024)  # 5GB default
    storage_used = db.Column(db.BigInteger, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    trash_retention_days = db.Column(db.Integer, default=30)  # Default 30 days for trash retention
    
    # Password reset token fields
    reset_token = db.Column(db.String(64), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    @property
    def password(self) -> str:
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self) -> bool:
        return self.role == 'admin'
    
    def get_storage_usage_percent(self) -> float:
        if self.storage_quota > 0:
            return (self.storage_used / self.storage_quota) * 100
        return 100
    
    def update_storage_used(self) -> int:
        """Update the user's storage usage by calculating the total size of their files"""
        from app.models.file import File
        # Only count files that are not in trash
        total_size = db.session.query(db.func.sum(File.size)).filter_by(user_id=self.id, is_deleted=False).scalar() or 0
        self.storage_used = total_size
        db.session.commit()
        return self.storage_used
    
    def has_space_for_file(self, file_size: int) -> bool:
        """Check if user has enough space for a file of the given size"""
        return (self.storage_used + file_size) <= self.storage_quota
    
    def generate_reset_token(self) -> str:
        """Generate a password reset token"""
        import secrets
        from datetime import datetime, timedelta
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        return self.reset_token
    
    def verify_reset_token(self, token: str) -> bool:
        """Verify if the reset token is valid and not expired"""
        from datetime import datetime
        if self.reset_token != token:
            return False
        if not self.reset_token_expires:
            return False
        return datetime.utcnow() <= self.reset_token_expires
    
    def clear_reset_token(self) -> None:
        """Clear the reset token after use"""
        self.reset_token = None
        self.reset_token_expires = None
        db.session.commit() 