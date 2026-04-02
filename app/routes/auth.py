from typing import Callable
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, Response, abort, g, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.user import User
from app.models.user_session import UserSession  # 修复: 并发登录检测
from app.models.system_setting import SystemSetting
from app.security_policy import (
    PasswordPolicy, LoginLockout, check_login_lockout,
    log_security_event, SecureErrorHandler
)
from app.utils.security_logger import SensitiveDataMasker  # 修复: Token日志脱敏
from functools import wraps
from datetime import datetime, timedelta
import secrets
import re

auth = Blueprint('auth', __name__)

# Authentication middleware
def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f: Callable) -> Callable:
    """
    Admin privilege decorator with real-time role verification.
    
    Security features:
    1. Real-time database query for user role (not relying solely on session)
    2. Role change detection - detects if user's role was changed after login
    3. Session invalidation on role downgrade for security
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        # Real-time database query to get current user state
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('User account not found.', 'danger')
            return redirect(url_for('auth.login'))
        
        # Check if user is currently an admin (real-time check)
        if user.role != 'admin':
            # Role change detection: if session says admin but DB says otherwise
            if session.get('role') == 'admin':
                # Admin role was revoked - clear session for security
                session.clear()
                
                # 记录安全事件
                log_security_event(
                    'admin_privilege_revoked',
                    'Admin privileges were revoked, session cleared',
                    user_id=user.id,
                    username=user.username,
                    level='WARNING'
                )
                
                flash('Your admin privileges have been revoked. Please login again.', 'warning')
                return redirect(url_for('auth.login'))
            
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('files.index'))
        
        # Role consistency check: verify session role matches database
        # This detects if role was changed by another admin
        if session.get('role') != user.role:
            # Update session to match current database state
            session['role'] = user.role
            # Log role sync for audit
            log_security_event(
                'role_sync',
                f"Session role updated from '{session.get('role')}' to '{user.role}'",
                user_id=user.id,
                username=user.username,
                level='INFO'
            )
        
        # Store user object in g for potential reuse in the view
        g.current_user = user
        
        return f(*args, **kwargs)
    return decorated_function

@auth.route('/login', methods=['GET', 'POST'])
@check_login_lockout
def login() -> str:
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # 检查账户是否被锁定
        is_locked, remaining = LoginLockout.is_locked(request.remote_addr)
        if is_locked:
            minutes = remaining // 60
            seconds = remaining % 60
            if minutes > 0:
                message = f"登录失败次数过多，请 {minutes} 分 {seconds} 秒后再试"
            else:
                message = f"登录失败次数过多，请 {seconds} 秒后再试"
            flash(message, 'danger')
            
            # 记录尝试
            log_security_event(
                'login_attempt_locked',
                f"Account locked, attempt blocked",
                username=username,
                level='WARNING'
            )
            
            return render_template('auth/login.html')
        
        # 验证输入
        if not username or not password:
            flash('请输入用户名和密码', 'danger')
            return render_template('auth/login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.verify_password(password):
            # =========================================================================
            # 修复漏洞: 会话固定攻击 - 登录后重新生成session ID
            # =========================================================================
            # 保存旧session数据（如果有）
            old_session_data = dict(session)
            
            # 清除旧session并重新生成session ID
            session.clear()
            session.permanent = True  # 启用持久化session
            
            # 恢复必要的session数据（如果有）
            for key, value in old_session_data.items():
                if key not in ['user_id', 'username', 'role', 'session_token', '_csrf_token']:
                    session[key] = value
            
            # 设置用户session数据
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # 更新最后登录时间
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # =========================================================================
            # 修复漏洞: 会话验证 - 并发登录检测
            # =========================================================================
            if current_app.config.get('CONCURRENT_LOGIN_DETECTION', True):
                # 创建服务器端会话记录
                allow_multiple = current_app.config.get('ALLOW_MULTIPLE_SESSIONS', False)
                expires_hours = current_app.config.get('SESSION_EXPIRE_HOURS', 24)
                
                user_session = UserSession.create_session(
                    user_id=user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string if request.user_agent else None,
                    expires_hours=expires_hours,
                    allow_multiple=allow_multiple
                )
                
                # 将session token保存到客户端session
                session['session_token'] = user_session.session_token
                
                if not allow_multiple:
                    # 记录并发登录检测事件
                    log_security_event(
                        'concurrent_login_detected',
                        f"Previous sessions invalidated for user (single session policy)",
                        user_id=user.id,
                        username=user.username,
                        level='INFO'
                    )
            
            # 记录成功登录（脱敏处理）
            log_security_event(
                'login_success',
                SensitiveDataMasker.safe_log_message("User logged in successfully from IP: %s", request.remote_addr),
                user_id=user.id,
                username=user.username,
                level='INFO'
            )
            
            # 重置登录失败计数
            LoginLockout.record_attempt(request.remote_addr, success=True)
            
            # 获取跳转URL
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('files.index'))
        else:
            # 登录失败
            is_locked, remaining = LoginLockout.record_attempt(request.remote_addr, success=False)
            remaining_attempts = LoginLockout.get_remaining_attempts(request.remote_addr)
            
            if is_locked:
                flash(f'登录失败次数过多，账户已锁定 {remaining // 60} 分钟', 'danger')
            else:
                if remaining_attempts > 0:
                    flash(f'用户名或密码错误，还剩 {remaining_attempts} 次尝试机会', 'danger')
                else:
                    flash('用户名或密码错误', 'danger')
            
            # 记录失败登录（脱敏处理）
            masked_username = SensitiveDataMasker.mask_string(username)
            log_security_event(
                'login_failed',
                SensitiveDataMasker.safe_log_message(
                    "Login failed for user '%s' from IP: %s", 
                    masked_username, request.remote_addr
                ),
                username=masked_username,
                level='WARNING'
            )
    
    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register() -> str:
    # Check if registration is enabled
    registration_enabled = SystemSetting.query.filter_by(key='enable_registration').first()
    if registration_enabled and not registration_enabled.get_typed_value():
        flash('Registration is currently disabled', 'danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # 验证输入
        if not username or not email or not password:
            flash('请填写所有必填字段', 'danger')
            return render_template('auth/register.html')
        
        # 验证用户名格式
        if not re.match(r'^[a-zA-Z0-9_-]{3,64}$', username):
            flash('用户名必须为3-64个字符，只能包含字母、数字、下划线和连字符', 'danger')
            return render_template('auth/register.html')
        
        # 验证邮箱格式
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            flash('请输入有效的邮箱地址', 'danger')
            return render_template('auth/register.html')
        
        # 检查用户名或邮箱是否已存在
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('用户名或邮箱已被注册', 'danger')
            
            # 记录尝试注册已存在账户
            log_security_event(
                'register_duplicate',
                f"Attempt to register with existing username/email: {username}/{email}",
                level='INFO'
            )
            
            return render_template('auth/register.html')
        
        # 验证密码复杂度
        is_valid, error_msg = PasswordPolicy.validate(password, username)
        if not is_valid:
            flash(f'密码不符合要求：{error_msg}', 'danger')
            return render_template('auth/register.html')
        
        # Get default quota for new users
        default_quota_setting = SystemSetting.query.filter_by(key='default_user_quota').first()
        default_quota = 5 * 1024 * 1024 * 1024  # 5GB default
        if default_quota_setting:
            default_quota = default_quota_setting.get_typed_value()
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            role='user',
            storage_quota=default_quota
        )
        new_user.password = password
        
        db.session.add(new_user)
        db.session.commit()
        
        # Create root folder for user
        from app.models.file import Folder
        user_root_folder = Folder(
            name='root',
            user_id=new_user.id
        )
        db.session.add(user_root_folder)
        db.session.commit()
        
        # 记录注册成功
        log_security_event(
            'register_success',
            f"New user registered",
            user_id=new_user.id,
            username=new_user.username,
            level='INFO'
        )
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth.route('/logout')
@login_required
def logout() -> Response:
    user_id = session.get('user_id')
    username = session.get('username')
    session_token = session.get('session_token')
    
    # =========================================================================
    # 修复漏洞: 会话验证 - 使服务器端会话失效
    # =========================================================================
    if session_token and current_app.config.get('CONCURRENT_LOGIN_DETECTION', True):
        try:
            UserSession.invalidate_session(session_token)
        except Exception as e:
            current_app.logger.warning(f"Failed to invalidate server-side session: {e}")
    
    session.clear()
    
    # 记录登出（脱敏处理）
    if user_id:
        log_security_event(
            'logout',
            SensitiveDataMasker.safe_log_message("User logged out from IP: %s", request.remote_addr),
            user_id=user_id,
            username=username,
            level='INFO'
        )
    
    return redirect(url_for('auth.login'))

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile() -> str:
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        
        # Update email
        if email and email != user.email:
            # 验证邮箱格式
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                flash('请输入有效的邮箱地址', 'danger')
            else:
                existing_email = User.query.filter_by(email=email).first()
                if existing_email:
                    flash('Email already in use', 'danger')
                else:
                    old_email = user.email
                    user.email = email
                    flash('Email updated successfully', 'success')
                    
                    # 记录邮箱修改
                    log_security_event(
                        'email_changed',
                        f"Email changed from {old_email} to {email}",
                        user_id=user.id,
                        username=user.username,
                        level='INFO'
                    )
        
        # Update password
        if current_password and new_password:
            if user.verify_password(current_password):
                # 验证新密码复杂度
                is_valid, error_msg = PasswordPolicy.validate(new_password, user.username)
                if not is_valid:
                    flash(f'新密码不符合要求：{error_msg}', 'danger')
                else:
                    user.password = new_password
                    flash('Password updated successfully', 'success')
                    
                    # 记录密码修改
                    log_security_event(
                        'password_changed',
                        "User changed password",
                        user_id=user.id,
                        username=user.username,
                        level='INFO'
                    )
                    
                    # =========================================================================
                    # 修复漏洞: 会话验证 - 密码修改后使其他会话失效
                    # =========================================================================
                    if current_app.config.get('CONCURRENT_LOGIN_DETECTION', True):
                        # 保留当前会话，使其他会话失效
                        current_session_token = session.get('session_token')
                        invalidated_count = UserSession.invalidate_user_sessions(
                            user.id, 
                            exclude_token=current_session_token
                        )
                        
                        if invalidated_count > 0:
                            log_security_event(
                                'sessions_invalidated_password_change',
                                f"Invalidated {invalidated_count} other sessions due to password change",
                                user_id=user.id,
                                username=user.username,
                                level='INFO'
                            )
            else:
                flash('Current password is incorrect', 'danger')
                
                # 记录密码修改失败（脱敏处理）
                log_security_event(
                    'password_change_failed',
                    SensitiveDataMasker.safe_log_message(
                        "Failed password change attempt from IP: %s - incorrect current password", 
                        request.remote_addr
                    ),
                    user_id=user.id,
                    username=user.username,
                    level='WARNING'
                )
        
        db.session.commit()
    
    # Get file and folder counts
    from app.models.file import File, Folder
    files_count = File.query.filter_by(user_id=user.id, is_deleted=False).count()
    folders_count = Folder.query.filter_by(user_id=user.id, is_deleted=False).count()
    
    # Get last upload date
    last_upload = File.query.filter_by(user_id=user.id, is_deleted=False).order_by(File.created_at.desc()).first()
    last_upload_date = last_upload.created_at.strftime('%Y-%m-%d %H:%M') if last_upload else None
    
    storage_used_percent = user.get_storage_usage_percent()
    
    # 获取密码要求信息
    password_requirements = PasswordPolicy.get_requirements()
    
    return render_template('auth/profile.html', 
                           user=user, 
                           storage_used_percent=storage_used_percent,
                           files_count=files_count,
                           folders_count=folders_count,
                           last_upload_date=last_upload_date,
                           password_requirements=password_requirements)

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password() -> str:
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a token
            token = user.generate_reset_token()
            
            # Here you would send an email with the reset link
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # For demo purposes, just show the reset URL
            flash(f'Please check your email for the reset link. Demo: {reset_url}', 'info')
            
            # 记录密码重置请求
            log_security_event(
                'password_reset_requested',
                f"Password reset token generated",
                user_id=user.id,
                username=user.username,
                level='INFO'
            )
        else:
            # Don't reveal that the user doesn't exist
            flash('If your email is in our system, you will receive a password reset link shortly.', 'info')
            
            # 记录不存在的邮箱请求（但不暴露邮箱是否存在）- 脱敏处理
            masked_email = SensitiveDataMasker.mask_string(email)
            log_security_event(
                'password_reset_not_found',
                f"Password reset requested for non-existent email: {masked_email}",
                level='INFO'
            )
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token: str) -> str:
    # Find user with valid token
    user = User.query.filter_by(reset_token=token).first()
    
    # Validate token
    if not user or not user.verify_reset_token(token):
        flash('Invalid or expired reset link. Please request a new one.', 'danger')
        
        # 记录无效令牌尝试
        log_security_event(
            'password_reset_invalid_token',
            f"Attempt to use invalid or expired reset token",
            level='WARNING'
        )
        
        return redirect(url_for('auth.forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        # 验证密码复杂度
        is_valid, error_msg = PasswordPolicy.validate(password, user.username)
        if not is_valid:
            flash(f'密码不符合要求：{error_msg}', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        # Update password
        user.password_hash = generate_password_hash(password)
        user.clear_reset_token()
        db.session.commit()
        
        # =========================================================================
        # 修复漏洞: 会话验证 - 密码重置后使所有会话失效
        # =========================================================================
        if current_app.config.get('CONCURRENT_LOGIN_DETECTION', True):
            invalidated_count = UserSession.invalidate_user_sessions(user.id)
            
            if invalidated_count > 0:
                log_security_event(
                    'sessions_invalidated_password_reset',
                    f"Invalidated {invalidated_count} sessions due to password reset",
                    user_id=user.id,
                    username=user.username,
                    level='INFO'
                )
        
        # 记录密码重置成功（脱敏处理）
        log_security_event(
            'password_reset_success',
            SensitiveDataMasker.safe_log_message(
                "Password reset completed successfully from IP: %s", 
                request.remote_addr
            ),
            user_id=user.id,
            username=user.username,
            level='INFO'
        )
        
        flash('Your password has been reset successfully. Please login with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)
