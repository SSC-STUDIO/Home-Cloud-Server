from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, current_app
from app.extensions import db
from app.models.user import User
from app.models.file import File, Folder
from app.models.system import SystemMetric
from app.models.system_setting import SystemSetting
from app.routes.auth import admin_required
from werkzeug.security import generate_password_hash
import psutil
import platform
import datetime
import os
from app.utils.system_monitor import SystemMonitor

admin = Blueprint('admin', __name__)

def _safe_disk_usage(path: str):
    try:
        return psutil.disk_usage(path)
    except Exception:
        fallback = os.path.abspath(os.sep)
        return psutil.disk_usage(fallback)

@admin.route('/admin')
@admin_required
def index() -> str:
    # Count total users, files, and storage used
    total_users = User.query.count()
    total_files = File.query.filter_by(is_deleted=False).count()
    
    # Get system statistics
    disk_path = current_app.config.get('UPLOAD_FOLDER', os.path.abspath(os.sep))
    disk_usage = _safe_disk_usage(disk_path)

    system_stats = {
        'cpu_percent': psutil.cpu_percent(),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_percent': disk_usage.percent,
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'uptime': datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())
    }
    
    # Get recent metrics for graphs (last 24 hours)
    recent_metrics = SystemMetric.query.order_by(SystemMetric.timestamp.desc()).limit(24).all()
    
    # Calculate total storage
    total_storage_used = db.session.query(db.func.sum(User.storage_used)).scalar() or 0
    
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_files=total_files,
                           total_storage_used=total_storage_used,
                           system_stats=system_stats,
                           recent_metrics=recent_metrics)

@admin.route('/admin/users')
@admin_required
def users() -> str:
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin.route('/admin/users/create', methods=['GET', 'POST'])
@admin_required
def create_user() -> str:
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        storage_quota = request.form.get('storage_quota', type=int)
        trash_retention_days = request.form.get('trash_retention_days', type=int, default=30)
        
        # Convert GB to bytes
        if storage_quota:
            storage_quota = storage_quota * 1024 * 1024 * 1024
        else:
            # Get default from settings
            default_quota_setting = SystemSetting.query.filter_by(key='default_user_quota').first()
            storage_quota = default_quota_setting.get_typed_value() if default_quota_setting else (5 * 1024 * 1024 * 1024)
        
        # Validate input
        if not username or not email or not password:
            flash('All fields are required', 'danger')
            return render_template('admin/create_user.html')
        
        # Check if username or email already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists', 'danger')
            return render_template('admin/create_user.html')
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            storage_quota=storage_quota,
            trash_retention_days=trash_retention_days
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        # Create root folder for user
        user_root_folder = Folder(
            name='root',
            user_id=new_user.id
        )
        db.session.add(user_root_folder)
        db.session.commit()
        
        flash('User created successfully', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/create_user.html')

@admin.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id: int) -> str:
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        email = request.form.get('email')
        role = request.form.get('role')
        storage_quota = request.form.get('storage_quota', type=int)
        new_password = request.form.get('new_password')
        trash_retention_days = request.form.get('trash_retention_days', type=int)
        
        # Update email
        if email and email != user.email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email and existing_email.id != user.id:
                flash('Email already in use', 'danger')
            else:
                user.email = email
        
        # Update role
        if role:
            user.role = role
        
        # Update storage quota (GB to bytes)
        if storage_quota:
            user.storage_quota = storage_quota * 1024 * 1024 * 1024
        
        # Update trash retention days
        if trash_retention_days and trash_retention_days > 0:
            user.trash_retention_days = trash_retention_days
        
        # Update password if provided
        if new_password:
            user.password_hash = generate_password_hash(new_password)
        
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('admin.users'))
    
    # Convert bytes to GB for display
    storage_quota_gb = user.storage_quota / (1024 * 1024 * 1024)
    
    return render_template('admin/edit_user.html', user=user, storage_quota_gb=storage_quota_gb)

@admin.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id: int) -> str:
    if user_id == session.get('user_id'):
        flash('Cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))
    
    user = User.query.get_or_404(user_id)
    
    # Delete user's files from storage
    files = File.query.filter_by(user_id=user_id).all()
    for file in files:
        if os.path.exists(file.file_path):
            try:
                os.remove(file.file_path)
            except:
                pass
    
    # Delete user's records from database
    File.query.filter_by(user_id=user_id).delete()
    Folder.query.filter_by(user_id=user_id).delete()
    
    db.session.delete(user)
    db.session.commit()
    
    flash('User and all associated data deleted successfully', 'success')
    return redirect(url_for('admin.users'))

@admin.route('/admin/settings')
@admin_required
def settings() -> str:
    settings = SystemSetting.query.all()
    return render_template('admin/settings.html', settings=settings)

@admin.route('/admin/settings/update', methods=['POST'])
@admin_required
def update_settings() -> str:
    for key, value in request.form.items():
        if key.startswith('setting_'):
            setting_id = int(key.split('_')[1])
            setting = SystemSetting.query.get(setting_id)
            
            if setting:
                setting.value = value
                setting.updated_by = session.get('user_id')
                setting.updated_at = datetime.datetime.utcnow()
    
    db.session.commit()
    flash('Settings updated successfully', 'success')
    return redirect(url_for('admin.settings'))

@admin.route('/admin/settings/add', methods=['POST'])
@admin_required
def add_setting() -> str:
    key = request.form.get('key')
    value = request.form.get('value')
    value_type = request.form.get('value_type')
    description = request.form.get('description')
    is_advanced = 'is_advanced' in request.form
    
    # Check if key already exists
    existing_setting = SystemSetting.query.filter_by(key=key).first()
    if existing_setting:
        flash('Setting with this key already exists', 'danger')
        return redirect(url_for('admin.settings'))
    
    # Create new setting
    new_setting = SystemSetting(
        key=key,
        value=value,
        value_type=value_type,
        description=description,
        is_advanced=is_advanced,
        updated_by=session.get('user_id')
    )
    
    db.session.add(new_setting)
    db.session.commit()
    
    flash('Setting added successfully', 'success')
    return redirect(url_for('admin.settings'))

@admin.route('/admin/system')
@admin_required
def system() -> str:
    # Get real-time system stats
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    
    # Get total disk usage across all partitions
    monitor = SystemMonitor()
    disk = monitor.get_disk_usage()
    
    # Network stats
    net_io_counters = psutil.net_io_counters()
    
    # Process stats
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'username', 'memory_percent', 'cpu_percent']):
        try:
            proc_info = proc.info
            proc_info['memory_mb'] = proc.memory_info().rss / (1024 * 1024)
            processes.append(proc_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Sort processes by memory usage
    processes = sorted(processes, key=lambda p: p.get('memory_percent', 0), reverse=True)[:10]
    
    # Record metrics
    new_metric = SystemMetric(
        cpu_usage=cpu_percent,
        memory_usage=memory.percent,
        disk_usage=disk['percent'],
        network_rx=net_io_counters.bytes_recv,
        network_tx=net_io_counters.bytes_sent,
        active_connections=len(psutil.net_connections())
    )
    
    db.session.add(new_metric)
    db.session.commit()
    
    return render_template('admin/system.html',
                           cpu_percent=cpu_percent,
                           memory=memory,
                           disk=disk,
                           net_io_counters=net_io_counters,
                           processes=processes) 
