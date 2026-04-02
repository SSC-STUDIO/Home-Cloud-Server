"""
安全策略与防护模块
包含：密码策略、登录锁定机制、安全审计日志
"""

import re
import time
import hashlib
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, current_app, session, flash
from typing import Optional, Tuple

# =============================================================================
# 安全审计日志配置
# =============================================================================

# 创建安全日志记录器
security_logger = logging.getLogger('security')


def init_security_logging(app):
    """初始化安全审计日志"""
    # 创建文件处理器
    from logging.handlers import RotatingFileHandler
    import os
    
    # 确保日志目录存在
    log_dir = os.path.join(app.root_path, '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # 安全日志文件 - 最多保留10个备份，每个10MB
    security_log_path = os.path.join(log_dir, 'security.log')
    handler = RotatingFileHandler(
        security_log_path,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10,
        encoding='utf-8'
    )
    
    # 设置格式
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s | src_ip=%(src_ip)s user_agent=%(user_agent)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    
    # 配置记录器
    security_logger.setLevel(logging.INFO)
    security_logger.addHandler(handler)
    
    # 防止日志传播到根记录器
    security_logger.propagate = False


def log_security_event(event_type: str, message: str, user_id: Optional[int] = None, 
                       username: Optional[str] = None, level: str = 'INFO'):
    """
    记录安全审计日志
    
    Args:
        event_type: 事件类型 (login, logout, password_change, access_denied, etc.)
        message: 日志消息
        user_id: 用户ID
        username: 用户名
        level: 日志级别 (INFO, WARNING, ERROR, CRITICAL)
    """
    extra = {
        'src_ip': request.remote_addr if request else 'unknown',
        'user_agent': request.user_agent.string if request and request.user_agent else 'unknown'
    }
    
    # 构建详细消息
    details = f"event={event_type}"
    if user_id:
        details += f" user_id={user_id}"
    if username:
        details += f" username={username}"
    details += f" {message}"
    
    # 记录日志
    log_func = getattr(security_logger, level.lower(), security_logger.info)
    log_func(details, extra=extra)


# =============================================================================
# 密码策略
# =============================================================================

class PasswordPolicy:
    """
    密码复杂度策略
    
    要求：
    - 最少8个字符
    - 最多128个字符
    - 至少包含1个大写字母
    - 至少包含1个小写字母  
    - 至少包含1个数字
    - 至少包含1个特殊字符 (!@#$%^&*等)
    - 不能包含用户名
    - 不能是常见弱密码
    """
    
    MIN_LENGTH = 8
    MAX_LENGTH = 128
    
    # 常见弱密码列表（简化版，实际应使用更完整的列表）
    COMMON_PASSWORDS = {
        'password', '123456', '12345678', 'qwerty', 'abc123',
        'password123', 'admin', 'letmein', 'welcome', 'monkey',
        '1234567890', 'football', 'iloveyou', 'admin123', 'welcome123',
        'password1', '123123', '654321', 'superman', 'batman',
        'trustno1', 'access', 'master', 'michael', 'shadow'
    }
    
    @classmethod
    def validate(cls, password: str, username: str = '') -> Tuple[bool, str]:
        """
        验证密码复杂度
        
        Returns:
            (is_valid, error_message)
        """
        if not password:
            return False, "密码不能为空"
        
        # 长度检查
        if len(password) < cls.MIN_LENGTH:
            return False, f"密码长度不能少于 {cls.MIN_LENGTH} 个字符"
        
        if len(password) > cls.MAX_LENGTH:
            return False, f"密码长度不能超过 {cls.MAX_LENGTH} 个字符"
        
        # 复杂度检查
        checks = [
            (re.search(r'[A-Z]', password), "至少包含1个大写字母"),
            (re.search(r'[a-z]', password), "至少包含1个小写字母"),
            (re.search(r'\d', password), "至少包含1个数字"),
            (re.search(r'[!@#$%^&*(),.?":{}|<>\[\]\\;\'\/\`\~\_\-\+\=]', password), "至少包含1个特殊字符"),
        ]
        
        for passed, requirement in checks:
            if not passed:
                return False, f"密码必须包含{requirement}"
        
        # 不能包含用户名（不区分大小写）
        if username and username.lower() in password.lower():
            return False, "密码不能包含用户名"
        
        # 不能是常见弱密码
        if password.lower() in cls.COMMON_PASSWORDS:
            return False, "密码过于常见，容易被猜测，请使用更复杂的密码"
        
        return True, "密码符合要求"
    
    @classmethod
    def get_requirements(cls) -> str:
        """获取密码要求描述"""
        return (
            f"密码必须满足以下要求：\n"
            f"- 长度 {cls.MIN_LENGTH}-{cls.MAX_LENGTH} 个字符\n"
            f"- 至少包含1个大写字母\n"
            f"- 至少包含1个小写字母\n"
            f"- 至少包含1个数字\n"
            f"- 至少包含1个特殊字符 (!@#$%^&*等)\n"
            f"- 不能包含用户名\n"
            f"- 不能使用常见弱密码"
        )


# =============================================================================
# 登录锁定机制
# =============================================================================

class LoginLockout:
    """
    登录失败锁定机制
    
    策略：
    - 5分钟内连续失败5次，锁定30分钟
    - 失败次数和锁定状态存储在内存中（生产环境应使用Redis）
    """
    
    # 配置参数
    MAX_ATTEMPTS = 5              # 最大尝试次数
    LOCKOUT_DURATION = 1800       # 锁定时间（秒）= 30分钟
    ATTEMPT_WINDOW = 300          # 尝试窗口（秒）= 5分钟
    
    # 存储结构: {ip_hash: {'attempts': [], 'locked_until': timestamp or None}}
    _attempts = {}
    
    @classmethod
    def _get_ip_hash(cls, ip: str) -> str:
        """获取IP地址的哈希值（保护隐私）"""
        return hashlib.sha256(ip.encode()).hexdigest()[:16]
    
    @classmethod
    def is_locked(cls, ip: str) -> Tuple[bool, Optional[int]]:
        """
        检查IP是否被锁定
        
        Returns:
            (is_locked, remaining_seconds)
        """
        ip_hash = cls._get_ip_hash(ip)
        data = cls._attempts.get(ip_hash)
        
        if not data:
            return False, None
        
        locked_until = data.get('locked_until')
        if locked_until:
            now = time.time()
            if now < locked_until:
                remaining = int(locked_until - now)
                return True, remaining
            else:
                # 锁定已过期，清理数据
                cls._attempts[ip_hash] = {'attempts': [], 'locked_until': None}
                return False, None
        
        return False, None
    
    @classmethod
    def record_attempt(cls, ip: str, success: bool = False) -> Tuple[bool, Optional[int]]:
        """
        记录登录尝试
        
        Args:
            ip: 客户端IP
            success: 是否成功
            
        Returns:
            (is_locked, remaining_seconds)
        """
        ip_hash = cls._get_ip_hash(ip)
        now = time.time()
        
        if success:
            # 登录成功，清理该IP的记录
            if ip_hash in cls._attempts:
                del cls._attempts[ip_hash]
            return False, None
        
        # 获取或创建记录
        if ip_hash not in cls._attempts:
            cls._attempts[ip_hash] = {'attempts': [], 'locked_until': None}
        
        data = cls._attempts[ip_hash]
        
        # 清理过期的尝试记录
        cutoff = now - cls.ATTEMPT_WINDOW
        data['attempts'] = [t for t in data['attempts'] if t > cutoff]
        
        # 添加新尝试
        data['attempts'].append(now)
        
        # 检查是否需要锁定
        if len(data['attempts']) >= cls.MAX_ATTEMPTS:
            data['locked_until'] = now + cls.LOCKOUT_DURATION
            remaining = cls.LOCKOUT_DURATION
            
            # 记录安全日志
            log_security_event(
                'login_lockout',
                f"IP {ip} 因多次登录失败被锁定 {cls.LOCKOUT_DURATION} 秒",
                level='WARNING'
            )
            
            return True, remaining
        
        return False, None
    
    @classmethod
    def get_remaining_attempts(cls, ip: str) -> int:
        """获取剩余尝试次数"""
        ip_hash = cls._get_ip_hash(ip)
        data = cls._attempts.get(ip_hash)
        
        if not data:
            return cls.MAX_ATTEMPTS
        
        # 清理过期记录
        now = time.time()
        cutoff = now - cls.ATTEMPT_WINDOW
        data['attempts'] = [t for t in data['attempts'] if t > cutoff]
        
        return max(0, cls.MAX_ATTEMPTS - len(data['attempts']))
    
    @classmethod
    def reset(cls, ip: str):
        """手动重置IP的锁定状态（管理员使用）"""
        ip_hash = cls._get_ip_hash(ip)
        if ip_hash in cls._attempts:
            del cls._attempts[ip_hash]


# =============================================================================
# 安全装饰器
# =============================================================================

def check_login_lockout(f):
    """装饰器：检查登录锁定状态"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            is_locked, remaining = LoginLockout.is_locked(request.remote_addr)
            if is_locked:
                minutes = remaining // 60
                seconds = remaining % 60
                if minutes > 0:
                    message = f"登录失败次数过多，请 {minutes} 分 {seconds} 秒后再试"
                else:
                    message = f"登录失败次数过多，请 {seconds} 秒后再试"
                flash(message, 'danger')
                
                # 记录尝试突破锁定的行为
                log_security_event(
                    'lockout_violation_attempt',
                    f"IP 尝试在锁定期间登录",
                    level='WARNING'
                )
                
                return f(*args, **kwargs)
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# 错误信息处理
# =============================================================================

class SecureErrorHandler:
    """
    安全错误信息处理
    避免向用户暴露敏感信息
    """
    
    # 用户友好的错误消息映射
    ERROR_MESSAGES = {
        'auth_failed': '用户名或密码错误',
        'account_locked': '账户已被锁定，请稍后再试',
        'invalid_token': '链接无效或已过期',
        'permission_denied': '您没有权限执行此操作',
        'resource_not_found': '请求的资源不存在',
        'invalid_input': '输入数据无效',
        'server_error': '服务器内部错误，请稍后重试',
        'rate_limited': '请求过于频繁，请稍后再试',
    }
    
    @classmethod
    def get_message(cls, error_key: str, default: str = '操作失败') -> str:
        """获取安全的错误消息"""
        return cls.ERROR_MESSAGES.get(error_key, default)
    
    @classmethod
    def log_and_respond(cls, error_key: str, exception: Exception = None, 
                       level: str = 'ERROR', **context) -> str:
        """
        记录错误并返回安全的消息
        
        Args:
            error_key: 错误类型标识
            exception: 原始异常（用于日志记录）
            level: 日志级别
            **context: 额外的上下文信息
        """
        # 记录详细错误到日志（不暴露给用户）
        if exception:
            log_security_event(
                error_key,
                f"Error: {str(exception)} | Context: {context}",
                level=level
            )
        
        # 返回安全的错误消息
        return cls.get_message(error_key)


def sanitize_error_message(message: str) -> str:
    """
    清理错误消息，移除敏感信息
    
    移除：
    - 文件路径
    - SQL语句
    - 堆栈跟踪
    - 内部错误代码
    """
    if not message:
        return '操作失败'
    
    # 移除文件路径模式
    import re
    patterns = [
        (r'/[\w\-./]+/\w+\.py', '[FILE]'),  # 文件路径
        (r'SELECT\s+.+?FROM', '[SQL]'),      # SQL查询
        (r'INSERT\s+INTO\s+\w+', '[SQL]'),   # SQL插入
        (r'UPDATE\s+\w+\s+SET', '[SQL]'),    # SQL更新
        (r'DELETE\s+FROM\s+\w+', '[SQL]'),   # SQL删除
        (r'Traceback\s*\(most\s+recent\s+call\s+last\):.*', '[TRACEBACK]'),
    ]
    
    sanitized = message
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE | re.DOTALL)
    
    # 如果消息过长，截断
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + '...'
    
    return sanitized
