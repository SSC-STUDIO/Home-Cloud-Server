from typing import Callable
from flask import Blueprint, render_template, redirect, url_for, request, flash, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.user import User
from app.models.system_setting import SystemSetting
from functools import wraps
from datetime import datetime, timedelta
import secrets

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
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login', next=request.url))
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'admin':
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('files.index'))
        
        return f(*args, **kwargs)
    return decorated_function

@auth.route('/login', methods=['GET', 'POST'])
def login() -> str:
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            
            # Update last login time
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            return redirect(url_for('files.index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('auth/login.html')

@auth.route('/register', methods=['GET', 'POST'])
def register() -> str:
    # Check if registration is enabled
    registration_enabled = SystemSetting.query.filter_by(key='enable_registration').first()
    if registration_enabled and not registration_enabled.get_typed_value():
        flash('Registration is currently disabled', 'danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
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
            password_hash=generate_password_hash(password),
            role='user',
            storage_quota=default_quota
        )
        
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
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html')

@auth.route('/logout')
def logout() -> Response:
    session.clear()
    return redirect(url_for('auth.login'))

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile() -> str:
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        # Update email
        if email and email != user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already in use', 'danger')
            else:
                user.email = email
                flash('Email updated successfully', 'success')
        
        # Update password
        if current_password and new_password:
            if check_password_hash(user.password_hash, current_password):
                user.password_hash = generate_password_hash(new_password)
                flash('Password updated successfully', 'success')
            else:
                flash('Current password is incorrect', 'danger')
        
        db.session.commit()
    
    # Get file and folder counts
    from app.models.file import File, Folder
    files_count = File.query.filter_by(user_id=user.id, is_deleted=False).count()
    folders_count = Folder.query.filter_by(user_id=user.id, is_deleted=False).count()
    
    # Get last upload date
    last_upload = File.query.filter_by(user_id=user.id, is_deleted=False).order_by(File.created_at.desc()).first()
    last_upload_date = last_upload.created_at.strftime('%Y-%m-%d %H:%M') if last_upload else None
    
    storage_used_percent = user.get_storage_usage_percent()
    return render_template('auth/profile.html', 
                           user=user, 
                           storage_used_percent=storage_used_percent,
                           files_count=files_count,
                           folders_count=folders_count,
                           last_upload_date=last_upload_date)

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password() -> str:
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Generate a token
            token = secrets.token_urlsafe(32)
            
            # In a real application, you would store this token in the database
            # with an expiration time. For this demo, we're just using the token directly.
            
            # Here you would send an email with the reset link
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            
            # For demo purposes, just show the reset URL
            flash(f'Please check your email for the reset link. Demo: {reset_url}', 'info')
        else:
            # Don't reveal that the user doesn't exist
            flash('If your email is in our system, you will receive a password reset link shortly.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot_password.html')

@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token: str) -> str:
    # In a real application, you would validate the token against the database
    # For this demo, we're accepting any token
    
    if request.method == 'POST':
        password = request.form.get('password')
        
        # In a real application, you would find the user associated with the token
        # For this demo, we'll just show a success message
        
        flash('Your password has been reset successfully. Please login with your new password.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token) 
