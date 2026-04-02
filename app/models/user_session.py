from datetime import datetime, timedelta
from ..extensions import db
import secrets
import hashlib


class UserSession(db.Model):
    """
    用户会话模型 - 用于并发登录检测和会话管理
    
    安全功能：
    1. 跟踪用户活跃会话
    2. 支持单点登录（一个用户只能有一个活跃会话）
    3. 检测会话异常（IP变化、UA变化等）
    4. 支持强制下线特定会话
    """
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    session_hash = db.Column(db.String(64), nullable=False)  # 用于验证的session哈希
    
    # 设备/浏览器信息
    ip_address = db.Column(db.String(45), nullable=True)  # 支持IPv6
    user_agent = db.Column(db.String(512), nullable=True)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    
    # 状态
    is_active = db.Column(db.Boolean, default=True)
    is_revoked = db.Column(db.Boolean, default=False)
    
    # 关联用户
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic'))
    
    def __init__(self, user_id, session_token, ip_address=None, user_agent=None, 
                 expires_hours=24):
        self.user_id = user_id
        self.session_token = session_token
        self.session_hash = self._hash_session(session_token)
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.expires_at = datetime.utcnow() + timedelta(hours=expires_hours)
    
    @staticmethod
    def _hash_session(token):
        """对session token进行哈希，用于存储验证"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    @classmethod
    def create_session(cls, user_id, ip_address=None, user_agent=None, 
                       expires_hours=24, allow_multiple=False):
        """
        创建新会话
        
        Args:
            user_id: 用户ID
            ip_address: IP地址
            user_agent: 用户代理字符串
            expires_hours: 过期时间（小时）
            allow_multiple: 是否允许多个并发会话（False时会使其他会话失效）
        """
        # 生成唯一的session token
        session_token = secrets.token_urlsafe(32)
        
        # 如果不允许多会话，使该用户的其他活跃会话失效
        if not allow_multiple:
            cls.invalidate_user_sessions(user_id, exclude_token=None)
        
        # 创建新会话
        session = cls(
            user_id=user_id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_hours=expires_hours
        )
        
        db.session.add(session)
        db.session.commit()
        
        return session
    
    @classmethod
    def validate_session(cls, session_token, ip_address=None, user_agent=None):
        """
        验证会话是否有效
        
        Returns:
            (is_valid, session_obj, message)
        """
        if not session_token:
            return False, None, "No session token provided"
        
        # 查找会话
        session_hash = cls._hash_session(session_token)
        session_obj = cls.query.filter_by(session_hash=session_hash).first()
        
        if not session_obj:
            return False, None, "Session not found"
        
        # 检查是否已撤销
        if session_obj.is_revoked:
            return False, None, "Session has been revoked"
        
        # 检查是否过期
        if datetime.utcnow() > session_obj.expires_at:
            session_obj.is_active = False
            db.session.commit()
            return False, None, "Session has expired"
        
        # 更新最后活动时间
        session_obj.last_activity = datetime.utcnow()
        db.session.commit()
        
        return True, session_obj, "Session valid"
    
    @classmethod
    def invalidate_session(cls, session_token):
        """使特定会话失效"""
        session_hash = cls._hash_session(session_token)
        session_obj = cls.query.filter_by(session_hash=session_hash).first()
        
        if session_obj:
            session_obj.is_active = False
            session_obj.is_revoked = True
            db.session.commit()
            return True
        return False
    
    @classmethod
    def invalidate_user_sessions(cls, user_id, exclude_token=None):
        """使用户的所有会话失效（可用于密码修改后强制下线）"""
        query = cls.query.filter_by(user_id=user_id, is_active=True)
        
        if exclude_token:
            exclude_hash = cls._hash_session(exclude_token)
            query = query.filter(cls.session_hash != exclude_hash)
        
        sessions = query.all()
        for session_obj in sessions:
            session_obj.is_active = False
            session_obj.is_revoked = True
        
        db.session.commit()
        return len(sessions)
    
    @classmethod
    def get_active_sessions(cls, user_id):
        """获取用户的活跃会话列表"""
        return cls.query.filter_by(
            user_id=user_id, 
            is_active=True,
            is_revoked=False
        ).filter(cls.expires_at > datetime.utcnow()).all()
    
    @classmethod
    def cleanup_expired_sessions(cls):
        """清理过期会话（可定期执行）"""
        expired = cls.query.filter(
            cls.expires_at < datetime.utcnow(),
            cls.is_active == True
        ).all()
        
        for session_obj in expired:
            session_obj.is_active = False
        
        db.session.commit()
        return len(expired)
    
    def to_dict(self):
        """转换为字典（用于管理界面显示）"""
        return {
            'id': self.id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent[:50] + '...' if self.user_agent and len(self.user_agent) > 50 else self.user_agent,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_activity': self.last_activity.strftime('%Y-%m-%d %H:%M:%S') if self.last_activity else None,
            'expires_at': self.expires_at.strftime('%Y-%m-%d %H:%M:%S') if self.expires_at else None,
            'is_active': self.is_active
        }
