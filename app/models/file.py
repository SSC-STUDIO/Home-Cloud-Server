from datetime import datetime, timedelta
import os
from app.extensions import db

class File(db.Model):
    __tablename__ = 'files'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(255), nullable=False)
    size = db.Column(db.BigInteger, nullable=False)
    file_type = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folders.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)  # When this file will be permanently deleted from trash
    
    def get_extension(self) -> str:
        return os.path.splitext(self.original_filename)[1].lower()
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'filename': self.original_filename,
            'size': self.size,
            'file_type': self.file_type,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_deleted': self.is_deleted,
            'deleted_at': self.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if self.deleted_at else None,
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if self.expiry_date else None
        }
    
    def move_to_trash(self, retention_days: int = 30) -> None:
        """Move file to trash with specified retention period"""
        from app.models.system_setting import SystemSetting
        from app.models.user import User
        
        # First check if user has a specific retention setting
        user = User.query.get(self.user_id)
        if user and user.trash_retention_days:
            retention_days = user.trash_retention_days
        else:
            # Fall back to system setting if user has no preference
            setting = SystemSetting.query.filter_by(key='default_trash_retention_days').first()
            if setting:
                try:
                    retention_days = int(setting.value)
                except (ValueError, TypeError):
                    pass  # Use default if setting is invalid
        
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.expiry_date = self.deleted_at + timedelta(days=retention_days)
    
    def restore_from_trash(self) -> None:
        """Restore file from trash"""
        self.is_deleted = False
        self.deleted_at = None
        self.expiry_date = None
    
    def permanently_delete(self) -> None:
        """Permanently delete the file"""
        try:
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception as e:
            # Log error but continue with database deletion
            print(f"Error deleting file {self.file_path}: {e}")
        
        db.session.delete(self)

class Folder(db.Model):
    __tablename__ = 'folders'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('folders.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)  # When this folder will be permanently deleted from trash
    
    # Define relationships
    parent = db.relationship('Folder', remote_side=[id], backref=db.backref('children', lazy='dynamic'))
    files = db.relationship('File', backref='folder', lazy='dynamic')
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'parent_id': self.parent_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_deleted': self.is_deleted,
            'deleted_at': self.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if self.deleted_at else None,
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if self.expiry_date else None
        }
    
    def get_path(self) -> str:
        """Get the full path of the folder"""
        if self.parent_id is None:
            return f"/{self.name}"
        return f"{self.parent.get_path()}/{self.name}"
    
    def move_to_trash(self, retention_days: int = 30) -> None:
        """Move folder to trash with specified retention period"""
        from app.models.system_setting import SystemSetting
        from app.models.user import User
        
        # First check if user has a specific retention setting
        user = User.query.get(self.user_id)
        if user and user.trash_retention_days:
            retention_days = user.trash_retention_days
        else:
            # Fall back to system setting if user has no preference
            setting = SystemSetting.query.filter_by(key='default_trash_retention_days').first()
            if setting:
                try:
                    retention_days = int(setting.value)
                except (ValueError, TypeError):
                    pass  # Use default if setting is invalid
        
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.expiry_date = self.deleted_at + timedelta(days=retention_days)
    
    def restore_from_trash(self) -> None:
        """Restore folder from trash"""
        self.is_deleted = False
        self.deleted_at = None
        self.expiry_date = None 
