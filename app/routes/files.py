from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, send_file, session, Response
from app.extensions import db
from app.models.user import User
from app.models.file import File, Folder
from app.models.system_setting import SystemSetting
from app.models.activity import Activity
from app.routes.auth import login_required
from requests.adapters import HTTPAdapter
from werkzeug.utils import secure_filename
import ipaddress
import os
import socket
import uuid
import re
from contextlib import closing
from datetime import datetime
import mimetypes
import time
from flask import after_this_request
import json
import zipfile
import io
from app.utils.transfer_tracker import TransferSpeedTracker
from app.utils.security_validation import (
    PathValidator, InputLengthValidator, 
    SpecialCharFilter, SecurityValidator,
    MagicBytesValidator
)
import shutil  # 新增，用于磁盘空间检测
from sqlalchemy import func
from urllib.parse import unquote, urlparse
from typing import Dict, List, Optional, Any, Tuple, Union
from functools import wraps

files = Blueprint('files', __name__)

# =============================================================================
# 权限验证装饰器和辅助函数 - 修复 IDOR 水平越权漏洞
# =============================================================================

def require_file_owner(f):
    """装饰器：验证当前用户是否拥有指定的文件"""
    @wraps(f)
    def decorated_function(file_id, *args, **kwargs):
        user_id = session.get('user_id')
        file = File.query.filter_by(id=file_id, user_id=user_id).first()
        if not file:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'File not found or access denied'}), 403
            flash('File not found or access denied', 'danger')
            return redirect(url_for('files.index'))
        return f(file_id, *args, **kwargs)
    return decorated_function

def require_folder_owner(f):
    """装饰器：验证当前用户是否拥有指定的文件夹"""
    @wraps(f)
    def decorated_function(folder_id, *args, **kwargs):
        user_id = session.get('user_id')
        folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
        if not folder:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Folder not found or access denied'}), 403
            flash('Folder not found or access denied', 'danger')
            return redirect(url_for('files.index'))
        return f(folder_id, *args, **kwargs)
    return decorated_function

def verify_file_ownership(file_id: int, user_id: int) -> bool:
    """验证文件是否属于指定用户"""
    if not file_id:
        return False
    return File.query.filter_by(id=file_id, user_id=user_id).first() is not None

def verify_folder_ownership(folder_id: int, user_id: int) -> bool:
    """验证文件夹是否属于指定用户"""
    if not folder_id:
        return False
    return Folder.query.filter_by(id=folder_id, user_id=user_id).first() is not None

def get_user_file_or_404(file_id: int, user_id: int, include_deleted: bool = False):
    """获取用户的文件，如果不存在则返回404"""
    query = File.query.filter_by(id=file_id, user_id=user_id)
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    return query.first_or_404()

def get_user_folder_or_404(folder_id: int, user_id: int, include_deleted: bool = False):
    """获取用户的文件夹，如果不存在则返回404"""
    query = Folder.query.filter_by(id=folder_id, user_id=user_id)
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    return query.first_or_404()

def get_user_files_in_folder(folder_id: int, user_id: int, include_deleted: bool = False):
    """安全地获取用户文件夹中的所有文件（带权限验证）"""
    # 首先验证文件夹所有权
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not folder:
        return []
    query = File.query.filter_by(folder_id=folder_id, user_id=user_id)
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    return query.all()

def get_user_subfolders(folder_id: int, user_id: int, include_deleted: bool = False):
    """安全地获取用户文件夹中的所有子文件夹（带权限验证）"""
    # 首先验证文件夹所有权
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not folder:
        return []
    query = Folder.query.filter_by(parent_id=folder_id, user_id=user_id)
    if not include_deleted:
        query = query.filter_by(is_deleted=False)
    return query.all()

def wants_json_response() -> bool:
    """Check if the request wants a JSON response."""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or request.accept_mimetypes.best == 'application/json'
    )

def get_files_page_context(user_id: int, folder_id: Optional[int] = None) -> Dict[str, Any]:
    """Get context data for the files page."""
    if folder_id:
        current_folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first_or_404()
        # 验证父文件夹所有权
        parent_folder = Folder.query.filter_by(id=current_folder.parent_id, user_id=user_id).first() if current_folder.parent_id else None
    else:
        current_folder = Folder.query.filter_by(user_id=user_id, parent_id=None, is_deleted=False).first()
        if not current_folder:
            current_folder = Folder(name='root', user_id=user_id)
            db.session.add(current_folder)
            db.session.commit()
        parent_folder = None

    subfolders = Folder.query.filter_by(parent_id=current_folder.id, user_id=user_id, is_deleted=False).all()
    files = File.query.filter_by(folder_id=current_folder.id, user_id=user_id, is_deleted=False).all()

    user = User.query.get(user_id)
    storage_used = sync_user_storage_used(user)
    storage_quota = user.storage_quota
    storage_percent = (storage_used / storage_quota) * 100 if storage_quota > 0 else 100
    all_folders = Folder.query.filter_by(user_id=user_id, is_deleted=False).all()

    return {
        'current_folder': current_folder,
        'parent_folder': parent_folder,
        'subfolders': subfolders,
        'files': files,
        'storage_used': storage_used,
        'storage_quota': storage_quota,
        'storage_percent': storage_percent,
        'all_folders': all_folders,
    }

def build_upload_feedback(uploaded_count: int, error_count: int) -> Dict[str, str]:
    """Build feedback message for upload operations."""
    if uploaded_count == 0:
        return {
            'state': 'error',
            'title': 'Upload failed',
            'message': 'No files were uploaded. Review the selection and try again.',
        }

    if error_count > 0:
        return {
            'state': 'progress',
            'title': 'Upload finished with warnings',
            'message': f'{uploaded_count} file(s) uploaded successfully, {error_count} failed.',
        }

    return {
        'state': 'success',
        'title': 'Upload complete',
        'message': f'All {uploaded_count} file(s) uploaded successfully.',
    }

def build_upload_json_payload(user_id: int, folder_id: Optional[int], 
                              uploaded_count: int, error_count: int, 
                              recent_items: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Build JSON payload for upload response."""
    context = get_files_page_context(user_id, folder_id)

    if context['storage_percent'] > 90:
        storage_bar_class = 'bg-danger'
    elif context['storage_percent'] > 70:
        storage_bar_class = 'bg-warning'
    else:
        storage_bar_class = 'bg-success'

    feedback = build_upload_feedback(uploaded_count, error_count)

    return {
        'feedback': feedback,
        'uploaded_count': uploaded_count,
        'error_count': error_count,
        'recent_items': recent_items or [],
        'has_items': bool(context['subfolders'] or context['files']),
        'metrics': {
            'storage_value': f"{round(context['storage_used'] / (1024 * 1024 * 1024), 2)} GB / {round(context['storage_quota'] / (1024 * 1024 * 1024), 2)} GB",
            'storage_note': f"{round(context['storage_percent'], 1)}% of your quota is currently in use.",
            'storage_percent': round(context['storage_percent'], 1),
            'storage_bar_class': storage_bar_class,
            'folders_count': len(context['subfolders']),
            'files_count': len(context['files']),
            'visible_count': len(context['subfolders']) + len(context['files']),
        },
        'rows_html': render_template(
            'files/partials/_table_rows.html',
            subfolders=context['subfolders'],
            files=context['files'],
        ),
        'destination_options_html': render_template(
            'files/partials/_destination_options.html',
            all_folders=context['all_folders'],
        ),
    }

def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed based on system settings."""
    allowed_types_setting = SystemSetting.query.filter_by(key='allowed_file_types').first()
    if allowed_types_setting:
        allowed_types = allowed_types_setting.get_typed_value()
        if not allowed_types:
            return '.' in filename
        if allowed_types == '*':
            return True
        
        allowed_extensions = {ext.strip().lower() for ext in allowed_types.split(',') if ext.strip()}
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in allowed_extensions
    
    return '.' in filename

def get_file_type(filename: str) -> str:
    """Categorize file by its type based on MIME type or extension."""
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    mime_type, _ = mimetypes.guess_type(filename)
    
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
        elif mime_type.startswith('audio/'):
            return 'audio'
        elif mime_type.startswith('text/'):
            return 'document'
        elif mime_type == 'application/pdf':
            return 'document'
        elif 'spreadsheet' in mime_type or 'excel' in mime_type:
            return 'spreadsheet'
        elif 'presentation' in mime_type or 'powerpoint' in mime_type:
            return 'presentation'
        elif mime_type.startswith('application/'):
            return 'application'
    
    if extension in ['zip', 'rar', '7z', 'tar', 'gz']:
        return 'archive'
    
    return 'other'

def get_free_space(path: str) -> int:
    """Return free space (in bytes) for the disk containing the given path."""
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except Exception as e:
        print(f"Error getting free space for {path}: {e}")
        return 0

def cleanup_saved_file(path: Optional[str]) -> None:
    """Clean up a saved file if it exists."""
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        print(f"Error cleaning up file {path}: {exc}")

def normalize_item_name(raw_value: Optional[str]) -> Optional[str]:
    """Normalize and validate item name to prevent path traversal attacks.
    修复: 强化路径验证、输入长度限制、完善特殊字符过滤
    
    Returns None if the name is invalid or potentially dangerous.
    """
    if raw_value is None:
        return None

    # 漏洞修复3: 输入长度限制检查
    valid, msg = InputLengthValidator.validate(raw_value, 'filename', min_length=1)
    if not valid:
        return None
    
    # 漏洞修复4: 控制字符检查
    if any(ord(c) < 32 for c in raw_value):
        return None
    
    # 空字节检查
    if '\x00' in raw_value:
        return None
    
    import unicodedata
    try:
        value = unicodedata.normalize('NFC', raw_value.strip())
    except (TypeError, ValueError):
        return None
    
    if not value:
        return None
    
    if value in {'.', '..'}:
        return None
    
    # 漏洞修复1: 强化路径验证 - 扩展危险模式列表
    dangerous_patterns = [
        '../', '..\\', '/..', '\\..',
        '..%2f', '..%2F', '%2e%2e', '%252e%252e',
        '....', '.....', '....\\',
        '%2e%2e%2f', '%252e%252e%252f',
        '..%00', '..%00/',
        '\x00', '%00',
    ]
    lower_value = value.lower()
    for pattern in dangerous_patterns:
        if pattern in lower_value:
            return None
    
    # 检查路径分隔符
    if value.startswith('/') or value.startswith('\\'):
        return None
    
    # 检查Windows盘符
    if re.match(r'^[a-zA-Z]:', value):
        return None
    
    # 漏洞修复4: 完善特殊字符过滤
    # 移除或替换危险Unicode字符
    value = SpecialCharFilter.sanitize_unicode(value)
    
    # 移除控制字符
    value = SpecialCharFilter.sanitize_control_chars(value)
    
    # 移除路径分隔符
    if any(separator in value for separator in ('/', '\\')):
        return None
    
    # 检查保留文件名 (Windows)
    reserved_names = {
        'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4',
        'com5', 'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 
        'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
    }
    base_name = value.lower().split('.')[0]
    if base_name in reserved_names:
        return None
    
    # 漏洞修复4: 检查脚本注入特征
    if SpecialCharFilter.has_script_content(value):
        return None

    return value

def build_storage_filename(filename: str) -> str:
    """Build a unique storage filename with UUID prefix."""
    safe_name = secure_filename(filename)
    if safe_name:
        return f"{uuid.uuid4().hex}_{safe_name}"

    _, extension = os.path.splitext(filename)
    fallback_name = f"file{extension}" if extension else "file"
    return f"{uuid.uuid4().hex}_{fallback_name}"


def sync_user_storage_used(user: Optional[User]) -> int:
    """Synchronize user's storage usage by calculating total file sizes."""
    if user is None:
        return 0

    total_size = db.session.query(func.sum(File.size)).filter_by(user_id=user.id, is_deleted=False).scalar() or 0
    user.storage_used = total_size
    return total_size


def resolve_managed_file_path(file_path: str) -> Optional[str]:
    """Resolve and validate file path is within upload folder.
    修复: 强化路径验证，防止目录遍历攻击
    """
    # 漏洞修复1 & 3: 路径验证和长度限制
    valid, result = SecurityValidator.validate_filepath(
        file_path, 
        base_dir=current_app.config.get('UPLOAD_FOLDER')
    )
    if not valid:
        return None
    
    upload_root = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
    target_path = os.path.realpath(result)

    try:
        common_path = os.path.commonpath([upload_root, target_path])
    except ValueError:
        return None

    if common_path != upload_root or not os.path.isfile(target_path):
        return None

    return target_path


def is_blocked_remote_ip(ip_text: str) -> bool:
    """Check if IP address is blocked (private, loopback, etc.)."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def validate_remote_download_url(file_url: str) -> Any:
    """Validate remote download URL is safe."""
    parsed = urlparse(file_url)
    if parsed.scheme not in {'http', 'https'}:
        raise ValueError('Invalid URL')

    hostname = parsed.hostname
    if not hostname:
        raise ValueError('Invalid URL')

    return parsed


def resolve_remote_connect_target(parsed_url: Any) -> Dict[str, Any]:
    """Resolve remote connect target with IP validation."""
    hostname = parsed_url.hostname
    if not hostname:
        raise ValueError('Invalid URL')

    connect_port = parsed_url.port
    if connect_port is None:
        connect_port = 443 if parsed_url.scheme == 'https' else 80

    try:
        resolved_addresses = socket.getaddrinfo(hostname, connect_port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('Invalid URL') from exc

    if not resolved_addresses:
        raise ValueError('Invalid URL')

    allowed_target = None
    blocked_detected = False
    for family, socktype, proto, canonname, sockaddr in resolved_addresses:
        resolved_ip = sockaddr[0]
        if is_blocked_remote_ip(resolved_ip):
            blocked_detected = True
            continue

        if allowed_target is None:
            allowed_target = {
                'family': family,
                'socktype': socktype,
                'proto': proto,
                'canonname': canonname,
                'sockaddr': sockaddr,
                'resolved_ip': resolved_ip,
                'connect_port': connect_port,
                'hostname': hostname,
            }

    if blocked_detected:
        raise ValueError('Blocked remote address')

    if allowed_target is None:
        raise ValueError('Invalid URL')

    return allowed_target


def prepare_remote_request(request_url: str) -> Dict[str, Any]:
    """Prepare remote download request with security checks."""
    parsed = validate_remote_download_url(request_url)
    target = resolve_remote_connect_target(parsed)
    direct_url = build_direct_connect_url(parsed, target['resolved_ip'], target['connect_port'])

    return {
        'parsed_url': parsed,
        'target': target,
        'direct_url': direct_url,
        'headers': {'Host': target['hostname']},
        'verify': target['hostname'],
    }


def create_remote_download_session() -> Any:
    """Create a requests session for remote downloads with custom adapter."""
    import requests
    session = requests.Session()
    session.trust_env = False
    adapter = RemoteDownloadAdapter()
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def build_direct_connect_url(parsed_url: Any, resolved_ip: str, connect_port: int) -> str:
    """Build direct connect URL with resolved IP."""
    if ':' in resolved_ip and not resolved_ip.startswith('['):
        netloc_host = f'[{resolved_ip}]'
    else:
        netloc_host = resolved_ip

    default_port = 443 if parsed_url.scheme == 'https' else 80
    if connect_port != default_port:
        netloc = f'{netloc_host}:{connect_port}'
    else:
        netloc = netloc_host

    return parsed_url._replace(netloc=netloc).geturl()


def folder_name_exists(user_id: int, parent_id: Optional[int], folder_name: str, 
                       exclude_folder_id: Optional[int] = None) -> bool:
    """Check if a folder with the given name already exists."""
    query = Folder.query.filter(
        Folder.user_id == user_id,
        Folder.parent_id == parent_id,
        Folder.is_deleted.is_(False),
        func.lower(Folder.name) == folder_name.lower(),
    )
    if exclude_folder_id is not None:
        query = query.filter(Folder.id != exclude_folder_id)
    return query.first() is not None

def file_name_exists(user_id: int, folder_id: int, filename: str, 
                     exclude_file_id: Optional[int] = None) -> bool:
    """Check if a file with the same name exists in the folder."""
    query = File.query.filter(
        File.user_id == user_id,
        File.folder_id == folder_id,
        File.is_deleted.is_(False),
        func.lower(File.original_filename) == filename.lower(),
    )
    if exclude_file_id is not None:
        query = query.filter(File.id != exclude_file_id)
    return query.first() is not None

def generate_unique_filename(user_id: int, folder_id: int, filename: str, 
                             max_attempts: int = 100) -> Optional[str]:
    """Generate a unique filename, handling race conditions."""
    base_name, extension = os.path.splitext(filename)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    for attempt in range(max_attempts):
        if attempt == 0:
            candidate = filename
        else:
            candidate = f"{base_name}_{timestamp}_{attempt}{extension}"
        
        existing = File.query.filter(
            File.user_id == user_id,
            File.folder_id == folder_id,
            File.is_deleted.is_(False),
            func.lower(File.original_filename) == candidate.lower()
        ).with_for_update().first()
        
        if not existing:
            return candidate
    
    return None

def escaped_like_query(value: str) -> str:
    """Escape special characters for SQL LIKE queries."""
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

@files.route('/files')
@login_required
def index():
    user_id = session.get('user_id')
    folder_id = request.args.get('folder_id', type=int)
    return render_template('files/index.html', **get_files_page_context(user_id, folder_id))

@files.route('/files/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload, supporting both regular file and folder uploads"""
    user_id = session.get('user_id')
    is_folder_upload = request.form.get('is_folder_upload') == 'true'
    folder_id = request.form.get('folder_id', type=int)
    wants_json = wants_json_response()
    
    if not request.files.getlist('files[]'):
        if wants_json:
            return jsonify({'feedback': {
                'state': 'error',
                'title': 'No files selected',
                'message': 'Choose at least one file or folder before starting the upload.',
            }}), 400
        flash('No files selected for upload', 'warning')
        return redirect(url_for('files.index'))
    
    # Get current folder
    current_folder = None
    if folder_id:
        current_folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    if not current_folder:
        current_folder = Folder.query.filter_by(user_id=user_id, parent_id=None).first()
        if not current_folder:
            current_folder = Folder(name='root', user_id=user_id)
            db.session.add(current_folder)
            db.session.commit()
    
    # Get max upload size from settings
    max_size_setting = SystemSetting.query.filter_by(key='max_upload_size').first()
    max_size = current_app.config.get('MAX_CONTENT_LENGTH', 2000 * 1024 * 1024 * 1024)  # Default 2TB
    if max_size_setting:
        try:
            max_size = int(max_size_setting.get_typed_value())
        except (TypeError, ValueError):
            pass
    
    # Get user info
    user = User.query.get(user_id)
    
    # Dictionary to keep track of created folders
    created_folders = {}
    uploaded_count = 0
    error_count = 0
    recent_items = []
    saved_file_paths = []
    
    def direct_save_file(file_obj, save_path):
        """Directly save file to target location without using temporary storage"""
        try:
            with open(save_path, 'wb') as f:
                while True:
                    chunk = file_obj.read(8192)  # Read in 8KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
            return True
        except Exception as e:
            print(f"Error in direct_save_file: {str(e)}")
            return False
    
    # Determine if we should force direct write based on system setting
    direct_write_setting = SystemSetting.query.filter_by(key='direct_write_upload').first()
    force_direct_write = False
    if direct_write_setting:
        try:
            force_direct_write = bool(direct_write_setting.get_typed_value())
        except Exception:
            force_direct_write = False

    # Process each uploaded file
    for uploaded_file in request.files.getlist('files[]'):
        if not uploaded_file.filename:
            continue
        
        try:
            # Get the relative path for folder uploads
            relative_path = uploaded_file.filename.replace('\\', '/').lstrip('/')
            
            # Handle folder structure
            parent_folder = current_folder
            if is_folder_upload and '/' in relative_path:
                # Split path into folder parts
                path_parts = [p for p in relative_path.split('/') if p not in ('', '.', '..')]
                if not path_parts:
                    continue
                filename = normalize_item_name(path_parts.pop())
                if not filename:
                    error_count += 1
                    continue

                # Create folder structure
                current_path = ""
                for raw_folder_name in path_parts:
                    folder_name = normalize_item_name(raw_folder_name)
                    if not folder_name:
                        parent_folder = None
                        break

                    # Build current path for folder tracking
                    current_path = os.path.join(current_path, folder_name) if current_path else folder_name

                    # Check if we've already created this folder
                    if current_path in created_folders:
                        parent_folder = created_folders[current_path]
                    else:
                        # Check for existing folder
                        existing_folder = Folder.query.filter_by(
                            name=folder_name,
                            parent_id=parent_folder.id,
                            user_id=user_id,
                            is_deleted=False
                        ).first()

                        if existing_folder:
                            parent_folder = existing_folder
                        else:
                            # Create new folder
                            new_folder = Folder(
                                name=folder_name,
                                parent_id=parent_folder.id,
                                user_id=user_id
                            )
                            db.session.add(new_folder)
                            db.session.flush()  # Get the ID without committing
                            parent_folder = new_folder

                            if parent_folder.parent_id == current_folder.id:
                                recent_items.append({
                                    'kind': 'folder',
                                    'id': parent_folder.id,
                                })

                        created_folders[current_path] = parent_folder

                if parent_folder is None:
                    error_count += 1
                    continue
            else:
                filename = normalize_item_name(os.path.basename(relative_path))

            if not filename:
                continue
            
            # Generate unique filename (handles race conditions)
            unique_filename = generate_unique_filename(user_id, parent_folder.id, filename)
            if not unique_filename:
                flash(f'Could not generate unique filename for: {filename}', 'danger')
                error_count += 1
                continue
            filename = unique_filename
            
            # Check file type
            if not allowed_file(filename):
                flash(f'File type not allowed: {filename}', 'danger')
                error_count += 1
                continue
            
            # Get file size
            uploaded_file.seek(0, os.SEEK_END)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)
            
            # Check file size
            if file_size > max_size:
                flash(f'File too large: {filename}', 'danger')
                error_count += 1
                continue
            
            # Check user quota
            if not user.has_space_for_file(file_size):
                flash('Not enough storage space', 'danger')
                error_count += 1
                break
            
            # Generate unique filename for storage
            storage_filename = build_storage_filename(filename)
            
            # Create folder structure in storage if needed
            folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(parent_folder.id))
            if not os.path.exists(folder_path):
                os.makedirs(folder_path, exist_ok=True)
            
            save_path = os.path.join(folder_path, storage_filename)
            
            # Decide whether to use temp cache or direct write
            use_temp_cache = False
            if not force_direct_write:
                temp_dir = current_app.config.get('TEMP_UPLOAD_PATH')
                if temp_dir and os.path.isdir(temp_dir):
                    free_space = get_free_space(temp_dir)
                    if free_space >= file_size + 10 * 1024 * 1024:  # 保留10MB余量
                        use_temp_cache = True

            try:
                if use_temp_cache:
                    # 使用本地缓存目录
                    tmp_path = os.path.join(temp_dir, storage_filename)
                    uploaded_file.save(tmp_path)
                    shutil.move(tmp_path, save_path)
                else:
                    # 直接写入目标存储
                    if not direct_save_file(uploaded_file, save_path):
                        raise Exception('direct_save_file failed')

                saved_file_paths.append(save_path)
                
                # SECURITY FIX: Validate file magic bytes to prevent fake extension attacks
                allowed_mimes = {
                    'image/jpeg', 'image/png', 'image/gif', 'image/bmp', 'image/webp', 'image/tiff',
                    'application/pdf', 'text/plain', 'text/csv',
                    'application/zip', 'application/x-zip-compressed',
                    'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                }
                is_valid, validation_msg = MagicBytesValidator.validate_file_type(
                    save_path, allowed_types=allowed_mimes
                )
                if not is_valid:
                    cleanup_saved_file(save_path)
                    saved_file_paths.remove(save_path)
                    flash(f'File validation failed: {validation_msg}', 'danger')
                    error_count += 1
                    continue

                # Create file record
                file_type = get_file_type(filename)
                new_file = File(
                    filename=storage_filename,
                    original_filename=filename,
                    file_path=save_path,
                    size=file_size,
                    file_type=file_type,
                    user_id=user_id,
                    folder_id=parent_folder.id
                )
                
                db.session.add(new_file)
                db.session.flush()

                if parent_folder.id == current_folder.id:
                    recent_items.append({
                        'kind': 'file',
                        'id': new_file.id,
                    })
                
                sync_user_storage_used(user)
                
                # Log activity
                activity = Activity(
                    user_id=user_id,
                    action='upload',
                    target=filename,
                    details=f'Uploaded to folder {parent_folder.name}',
                    file_size=file_size,
                    file_type=file_type
                )
                db.session.add(activity)
                
                uploaded_count += 1
            except Exception as e:
                cleanup_saved_file(save_path)
                if save_path in saved_file_paths:
                    saved_file_paths.remove(save_path)
                print(f"Error saving file {filename}: {str(e)}")
                error_count += 1
                continue
            
        except Exception as e:
            print(f"Error processing file {uploaded_file.filename}: {str(e)}")
            error_count += 1
            continue
    
    # Commit all changes
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        for save_path in saved_file_paths:
            cleanup_saved_file(save_path)
        print(f"Error committing changes: {str(e)}")
        if wants_json:
            return jsonify({'feedback': {
                'state': 'error',
                'title': 'Upload failed',
                'message': 'The server could not save the uploaded files to the database.',
            }}), 500
        flash('Error saving files to database', 'danger')
        return redirect(url_for('files.index'))
    
    # Show appropriate message
    if uploaded_count == 0:
        flash('No files were uploaded', 'warning')
    elif error_count > 0:
        flash(f'{uploaded_count} files uploaded successfully, {error_count} failed', 'info')
    else:
        flash(f'All {uploaded_count} files uploaded successfully', 'success')

    if wants_json:
        payload = build_upload_json_payload(user_id, folder_id, uploaded_count, error_count, recent_items=recent_items)
        status_code = 200 if uploaded_count > 0 else 400
        return jsonify(payload), status_code
    
    return redirect(url_for('files.index', folder_id=folder_id))

@files.route('/files/download/<int:file_id>')
@login_required
def download_file(file_id):
    """Download a file with speed tracking"""
    
    user_id = session.get('user_id')
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first_or_404()
    
    # Record activity upfront (duration and speed to be filled after response)
    activity = Activity(
        user_id=user_id,
        action='download',
        target=file.original_filename,
        file_size=file.size,
        file_type=file.file_type
    )
    db.session.add(activity)
    db.session.commit()

    start_time = time.time()

    @after_this_request
    def update_metrics(response):
        duration = max(time.time() - start_time, 0.0001)  # avoid division by zero
        speed = file.size / duration
        activity.duration = duration
        activity.transfer_speed = speed
        db.session.commit()
        return response

    managed_file_path = resolve_managed_file_path(file.file_path)
    if not managed_file_path:
        return '', 404

    # Determine mime type from filename for better browser handling
    mime_type, _ = mimetypes.guess_type(file.original_filename)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    response = send_file(
        managed_file_path,
        mimetype=mime_type,
        as_attachment=True,
        download_name=file.original_filename
    )
    # Ensure Content-Disposition includes both filename and filename* (UTF-8)
    from urllib.parse import quote
    ascii_filename = secure_filename(file.original_filename)
    if not ascii_filename:
        ascii_filename = 'download'
    disposition = f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quote(file.original_filename)}"
    response.headers['Content-Disposition'] = disposition
    return response

@files.route('/files/trash')
@login_required
def trash():
    """View files in trash bin"""
    user_id = session.get('user_id')
    
    # Get trashed files and folders
    deleted_files = File.query.filter_by(user_id=user_id, is_deleted=True).all()
    deleted_folders = Folder.query.filter_by(user_id=user_id, is_deleted=True, parent_id=None).all()
    
    # Get folder structures for display
    folder_structures = []
    for folder in deleted_folders:
        # Get immediate children
        # subfolders = Folder.query.filter_by(parent_id=folder.id, is_deleted=True).all()
        # folder_files = File.query.filter_by(folder_id=folder.id, is_deleted=True).all()
        
        # Function to recursively get all subfolders with ownership verification
        def get_subfolder_tree(parent_folder):
            result = {
                'folder': parent_folder,
                'subfolders': [],
                # 只查询当前用户的文件
                'files': File.query.filter_by(folder_id=parent_folder.id, user_id=user_id, is_deleted=True).all()
            }
            
            # Find all direct subfolders with ownership verification
            direct_subfolders = Folder.query.filter_by(parent_id=parent_folder.id, user_id=user_id, is_deleted=True).all()
            for subfolder in direct_subfolders:
                result['subfolders'].append(get_subfolder_tree(subfolder))
                
            return result
        
        # Create structure for this root folder
        folder_structure = get_subfolder_tree(folder)
        folder_structures.append(folder_structure)
    
    # Calculate trash size
    trash_size = sum(file.size for file in deleted_files)
    
    # Get user's storage info for context (recalculate to ensure up-to-date)
    user = User.query.get(user_id)
    storage_used = sync_user_storage_used(user)
    db.session.commit()
    storage_quota = user.storage_quota
    storage_percent = (storage_used / storage_quota) * 100 if storage_quota > 0 else 100
    
    # Get trash settings
    retention_days = 30  # Default
    setting = SystemSetting.query.filter_by(key='default_trash_retention_days').first()
    if setting:
        try:
            retention_days = int(setting.value)
        except (ValueError, TypeError):
            pass
    
    return render_template('files/trash.html',
                          deleted_files=deleted_files,
                          deleted_folders=deleted_folders,
                          folder_structures=folder_structures,
                          trash_size=trash_size,
                          storage_used=storage_used,
                          storage_quota=storage_quota,
                          storage_percent=storage_percent,
                          retention_days=retention_days)

@files.route('/files/restore/<int:file_id>', methods=['POST'])
@login_required
def restore_file(file_id):
    """Restore file from trash"""
    user_id = session.get('user_id')
    print(f"Attempting to restore file ID: {file_id} for user: {user_id}")
    
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=True).first_or_404()

    if file_name_exists(user_id, file.folder_id, file.original_filename):
        message = f'File "{file.original_filename}" cannot be restored because a file with the same name already exists'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': message}), 409
        flash(message, 'danger')
        return redirect(url_for('files.trash'))

    # Restore file
    file.restore_from_trash()
    
    # If parent folder (or any ancestor) is still deleted, restore it as well
    def restore_parent_folders(folder_id):
        if folder_id is None:
            return
        # 验证父文件夹所有权
        parent_folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
        if parent_folder and parent_folder.is_deleted:
            parent_folder.restore_from_trash()
            restore_parent_folders(parent_folder.parent_id)

    restore_parent_folders(file.folder_id)
    
    sync_user_storage_used(User.query.get(user_id))
    db.session.commit()
    print(f"File restored from trash: {file.original_filename}")
    
    # Log activity
    activity = Activity(
        user_id=user_id,
        action='restore_file',
        target=file.original_filename,
        file_size=file.size,
        file_type=file.file_type,
        details=f'Restored file from trash'
    )
    db.session.add(activity)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f'File "{file.original_filename}" restored successfully'})
    
    flash(f'File "{file.original_filename}" restored successfully', 'success')
    return redirect(url_for('files.trash'))

@files.route('/files/restore_folder/<int:folder_id>', methods=['POST'])
@login_required
def restore_folder(folder_id):
    """Restore folder from trash"""
    user_id = session.get('user_id')
    print(f"Attempting to restore folder ID: {folder_id} for user: {user_id}")
    
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=True).first_or_404()
    print(f"Found folder to restore: {folder.name}")

    if folder_name_exists(user_id, folder.parent_id, folder.name):
        message = f'Folder "{folder.name}" cannot be restored because a folder with the same name already exists'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': message}), 409
        flash(message, 'danger')
        return redirect(url_for('files.trash'))

    # Restore folder
    folder.restore_from_trash()
    
    # Also restore all files in this folder (verified ownership)
    files_count = 0
    folder_files = File.query.filter_by(folder_id=folder.id, user_id=user_id, is_deleted=True).all()
    for file in folder_files:
        file.restore_from_trash()
        files_count += 1
    
    # Recursively restore all subfolders and their contents with ownership verification
    folders_count = 0
    def restore_subfolders_recursively(parent_id):
        nonlocal folders_count, files_count
        # 只查询当前用户的子文件夹
        subfolders = Folder.query.filter_by(parent_id=parent_id, user_id=user_id, is_deleted=True).all()
        for subfolder in subfolders:
            subfolder.restore_from_trash()
            folders_count += 1
            
            # Restore all files in this subfolder (verified ownership)
            subfolder_files = File.query.filter_by(folder_id=subfolder.id, user_id=user_id, is_deleted=True).all()
            for file in subfolder_files:
                file.restore_from_trash()
                files_count += 1
            
            # Recursively restore sub-subfolders
            restore_subfolders_recursively(subfolder.id)
    
    # Execute recursive restoration
    restore_subfolders_recursively(folder.id)
    
    sync_user_storage_used(User.query.get(user_id))
    db.session.commit()
    print(f"Folder restored from trash: {folder.name}, with {files_count} files and {folders_count} subfolders")
    
    # Log activity
    activity = Activity(
        user_id=user_id,
        action='restore_folder',
        target=folder.name,
        details=f'Restored folder and its contents from trash: {files_count} files, {folders_count} subfolders'
    )
    db.session.add(activity)
    db.session.commit()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': f'Folder "{folder.name}" and its contents restored successfully'})
    
    flash(f'Folder "{folder.name}" and its contents restored successfully', 'success')
    return redirect(url_for('files.trash'))

@files.route('/files/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    """Move file to trash or permanently delete if already in trash"""
    user_id = session.get('user_id')
    file = File.query.filter_by(id=file_id, user_id=user_id).first_or_404()
    user = User.query.get(user_id)
    
    if file.is_deleted:
        # Permanently delete
        file_name = file.original_filename
        file.permanently_delete()
        sync_user_storage_used(user)
        db.session.commit()
        flash(f'File "{file_name}" permanently deleted', 'success')
    else:   
        # Move to trash
        file.move_to_trash()
        sync_user_storage_used(user)
        db.session.commit()
        flash(f'File "{file.original_filename}" moved to trash', 'success')

    # Record activity
    action = 'permanent_delete' if file.is_deleted else 'trash'
    activity = Activity(
        user_id=user_id,
        action=action,
        target=file.original_filename,
        file_size=file.size,
        file_type=file.file_type
    )
    db.session.add(activity)
    db.session.commit()
    
    # Recalculate user's storage usage
    if user:
        sync_user_storage_used(user)
        db.session.commit()
    
    return redirect(request.referrer or url_for('files.index'))

@files.route('/files/delete_folder/<int:folder_id>', methods=['POST'])
@login_required
def delete_folder(folder_id):
    """Move folder to trash or permanently delete if already in trash"""
    user_id = session.get('user_id')
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first_or_404()
    
    if folder.is_deleted:
        # Permanently delete folder and all its contents
        folder_name = folder.name
        
        # Get all files in this folder (verified ownership)
        files_in_folder = get_user_files_in_folder(folder.id, user_id, include_deleted=True)
        for file in files_in_folder:
            file.permanently_delete()
        
        # Handle subfolders recursively with ownership verification
        def delete_subfolders_recursively(parent_id):
            # 只查询当前用户的子文件夹
            subfolders = Folder.query.filter_by(parent_id=parent_id, user_id=user_id).all()
            for subfolder in subfolders:
                # Delete all files in this subfolder (verified ownership)
                subfolder_files = File.query.filter_by(folder_id=subfolder.id, user_id=user_id).all()
                for file in subfolder_files:
                    file.permanently_delete()
                
                # Recursively handle sub-subfolders
                delete_subfolders_recursively(subfolder.id)
                
                # Delete the subfolder itself
                db.session.delete(subfolder)
        
        # Execute recursive deletion
        delete_subfolders_recursively(folder.id)

        # Finally delete the main folder
        db.session.delete(folder)
        user = User.query.get(user_id)
        sync_user_storage_used(user)
        db.session.commit()
        flash(f'Folder "{folder_name}" permanently deleted', 'success')
    else:
        # Move to trash
        folder.move_to_trash()
        user = User.query.get(user_id)
        total_moved_size = 0
        
        # Also mark all contained files as deleted (verified ownership)
        folder_files = get_user_files_in_folder(folder.id, user_id, include_deleted=False)
        for file in folder_files:
            total_moved_size += file.size
            file.move_to_trash()
        
        # And all subfolders with ownership verification
        def trash_subfolders_recursively(parent_id):
            nonlocal total_moved_size
            # 只查询当前用户的子文件夹
            subfolders = Folder.query.filter_by(parent_id=parent_id, user_id=user_id, is_deleted=False).all()
            for subfolder in subfolders:
                subfolder.move_to_trash()
                
                # Move all files in subfolder to trash (verified ownership)
                subfolder_files = File.query.filter_by(folder_id=subfolder.id, user_id=user_id, is_deleted=False).all()
                for file in subfolder_files:
                    total_moved_size += file.size
                    file.move_to_trash()
                
                # Recursively handle sub-subfolders
                trash_subfolders_recursively(subfolder.id)
        
        # Execute recursive trash operation
        trash_subfolders_recursively(folder.id)
        
        # Deduct storage usage
        if user:
            sync_user_storage_used(user)

        db.session.commit()
        flash(f'Folder "{folder.name}" moved to trash', 'success')
    
    # Record activity
    action = 'permanent_delete_folder' if folder.is_deleted else 'trash_folder'
    activity = Activity(
        user_id=user_id,
        action=action,
        target=folder.name
    )
    db.session.add(activity)
    db.session.commit()
    
    # Recalculate user's storage usage
    if user:
        sync_user_storage_used(user)
        db.session.commit()
    
    return redirect(request.referrer or url_for('files.index'))

@files.route('/files/empty_trash', methods=['POST'])
@login_required
def empty_trash():
    """Permanently delete all files and folders in trash"""
    user_id = session.get('user_id')
    
    # Get all trashed files
    trashed_files = File.query.filter_by(user_id=user_id, is_deleted=True).all()
    for file in trashed_files:
        file.permanently_delete()
    
    # Get all trashed folders
    trashed_folders = Folder.query.filter_by(user_id=user_id, is_deleted=True).all()
    for folder in trashed_folders:
        db.session.delete(folder)
    
    db.session.commit()
    
    # Record activity
    activity = Activity(
        user_id=user_id,
        action='empty_trash',
        details=f'Emptied trash with {len(trashed_files)} files and {len(trashed_folders)} folders'
    )
    db.session.add(activity)
    db.session.commit()
    
    # Recalculate user's storage usage
    user = User.query.get(user_id)
    if user:
        sync_user_storage_used(user)
        db.session.commit()
    
    flash('Trash emptied successfully', 'success')
    return redirect(url_for('files.trash'))

@files.route('/folders/create', methods=['POST'])
@login_required
def create_folder():
    user_id = session.get('user_id')
    folder_name = normalize_item_name(request.form.get('folder_name'))
    parent_id = request.form.get('parent_id', type=int)
    
    if not folder_name:
        flash('Enter a valid folder name without path separators', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    # Check if folder already exists in the same parent
    if folder_name_exists(user_id, parent_id, folder_name):
        flash('A folder with this name already exists', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    # Create new folder
    new_folder = Folder(
        name=folder_name,
        user_id=user_id,
        parent_id=parent_id
    )
    
    db.session.add(new_folder)
    db.session.commit()
    
    flash('Folder created successfully', 'success')
    return redirect(url_for('files.index', folder_id=parent_id))

@files.route('/files/search')
@login_required
def search_files():
    user_id = session.get('user_id')
    query = request.args.get('query', '').strip()
    
    # 漏洞修复3: 搜索查询长度限制
    if not query:
        return redirect(url_for('files.index'))
    
    valid, msg = InputLengthValidator.validate(query, 'search_query')
    if not valid:
        flash('搜索查询过长', 'warning')
        return redirect(url_for('files.index'))
    
    # 漏洞修复4: 检查搜索查询中的危险内容
    if SpecialCharFilter.has_script_content(query):
        flash('搜索查询包含非法内容', 'warning')
        return redirect(url_for('files.index'))

    like_query = f"%{escaped_like_query(query)}%"
    
    # Search for files and folders matching the query
    files = File.query.filter(
        File.user_id == user_id,
        File.is_deleted.is_(False),
        File.original_filename.ilike(like_query, escape='\\')
    ).all()
    
    folders = Folder.query.filter(
        Folder.user_id == user_id,
        Folder.is_deleted.is_(False),
        Folder.name.ilike(like_query, escape='\\')
    ).all()

    total_count = len(files) + len(folders)

    if wants_json_response():
        return jsonify({
            'query': query,
            'total_count': total_count,
            'html': render_template(
                'files/partials/_search_results.html',
                query=query,
                files=files,
                folders=folders,
                total_count=total_count,
            ),
        })
    
    return render_template('files/search.html', query=query, files=files, folders=folders)

@files.route('/files/rename/<int:file_id>', methods=['POST'])
@login_required
def rename_file(file_id):
    user_id = session.get('user_id')
    new_name = normalize_item_name(request.form.get('new_name'))
    
    if not new_name:
        flash('Enter a valid file name without path separators', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first_or_404()
    
    # Keep the file extension
    if '.' in file.original_filename and '.' not in new_name:
        extension = file.original_filename.rsplit('.', 1)[1]
        new_name = f"{new_name}.{extension}"
    
    new_name = normalize_item_name(new_name)
    if not new_name:
        flash('Enter a valid file name without path separators', 'danger')
        return redirect(request.referrer or url_for('files.index'))

    if file_name_exists(user_id, file.folder_id, new_name, exclude_file_id=file.id):
        flash('A file with this name already exists in this folder', 'danger')
        return redirect(request.referrer or url_for('files.index'))

    file.original_filename = new_name
    file.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    flash('File renamed successfully', 'success')
    return redirect(request.referrer or url_for('files.index'))

@files.route('/files/rename_folder/<int:folder_id>', methods=['POST'])
@login_required
def rename_folder(folder_id):
    user_id = session.get('user_id')
    new_name = normalize_item_name(request.form.get('new_name'))
    
    if not new_name:
        flash('Enter a valid folder name without path separators', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first_or_404()
    
    # Check if a folder with this name already exists in the same parent
    if folder_name_exists(user_id, folder.parent_id, new_name, exclude_folder_id=folder_id):
        flash('A folder with this name already exists', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    folder.name = new_name
    folder.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    flash('Folder renamed successfully', 'success')
    return redirect(request.referrer or url_for('files.index'))

@files.route('/files/history')
@login_required
def transfer_history():
    """View file transfer history"""
    user_id = session.get('user_id')
    
    # Get parameters for filtering
    action_type = request.args.get('action', 'all')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Build query
    query = Activity.query.filter_by(user_id=user_id)
    
    # Filter by action type
    if action_type == 'upload':
        query = query.filter_by(action='upload')
    elif action_type == 'download':
        query = query.filter_by(action='download')
    elif action_type == 'all':
        query = query.filter(Activity.action.in_(['upload', 'download']))
    
    # Filter by date range
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Activity.timestamp >= from_date)
        except ValueError:
            flash('Invalid date format', 'danger')
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(Activity.timestamp <= to_date)
        except ValueError:
            flash('Invalid date format', 'danger')
    
    # Order by most recent first
    activities = query.order_by(Activity.timestamp.desc()).all()
    
    # Get some stats for the summary
    upload_count = Activity.query.filter_by(user_id=user_id, action='upload').count()
    download_count = Activity.query.filter_by(user_id=user_id, action='download').count()
    
    # Calculate averages for transfer speeds (only for activities with speed data)
    upload_speeds = [a.transfer_speed for a in Activity.query.filter_by(user_id=user_id, action='upload').all() 
                     if a.transfer_speed is not None]
    download_speeds = [a.transfer_speed for a in Activity.query.filter_by(user_id=user_id, action='download').all() 
                       if a.transfer_speed is not None]
    
    avg_upload_speed = sum(upload_speeds) / len(upload_speeds) if upload_speeds else 0
    avg_download_speed = sum(download_speeds) / len(download_speeds) if download_speeds else 0
    
    return render_template('files/history.html',
                           activities=activities,
                           action_type=action_type,
                           date_from=date_from,
                           date_to=date_to,
                           upload_count=upload_count,
                           download_count=download_count,
                           avg_upload_speed=avg_upload_speed,
                           avg_download_speed=avg_download_speed)

@files.route('/files/batch_restore', methods=['POST'])
@login_required
def batch_restore():
    """Batch restore selected files and folders"""
    user_id = session.get('user_id')
    selected_items = request.form.getlist('selected_items[]')
    
    if not selected_items:
        flash('No items selected', 'warning')
        return redirect(url_for('files.trash'))
    
    restored_files = 0
    restored_folders = 0
    
    for item in selected_items:
        # Split type and ID
        item_type, item_id = item.split('-', 1)
        item_id = int(item_id)
        
        if item_type == 'file':
            # Restore file
            file = File.query.filter_by(id=item_id, user_id=user_id, is_deleted=True).first()
            if file:
                file.restore_from_trash()
                # Ensure parent folders are restored (with ownership verification)
                def restore_parents(fid):
                    if fid is None:
                        return
                    # 验证父文件夹所有权
                    pf = Folder.query.filter_by(id=fid, user_id=user_id).first()
                    if pf and pf.is_deleted:
                        pf.restore_from_trash()
                        restore_parents(pf.parent_id)

                restore_parents(file.folder_id)
                restored_files += 1
                
        elif item_type == 'folder':
            # Restore folder and its contents
            folder = Folder.query.filter_by(id=item_id, user_id=user_id, is_deleted=True).first()
            if folder:
                # Restore folder
                folder.restore_from_trash()
                
                # Restore files in folder (verified ownership)
                folder_files = File.query.filter_by(folder_id=folder.id, user_id=user_id, is_deleted=True).all()
                for file in folder_files:
                    file.restore_from_trash()
                
                # Recursively restore subfolders and their contents with ownership verification
                def restore_subfolders(parent_id):
                    # 只查询当前用户的子文件夹
                    subfolders = Folder.query.filter_by(parent_id=parent_id, user_id=user_id, is_deleted=True).all()
                    for subfolder in subfolders:
                        subfolder.restore_from_trash()
                        
                        # Restore files in subfolder (verified ownership)
                        subfolder_files = File.query.filter_by(folder_id=subfolder.id, user_id=user_id, is_deleted=True).all()
                        for file in subfolder_files:
                            file.restore_from_trash()
                        
                        # Recursively restore next level of subfolders
                        restore_subfolders(subfolder.id)
                
                # Execute recursive restoration
                restore_subfolders(folder.id)
                restored_folders += 1
    
    db.session.commit()
    
    # Log activity
    activity = Activity(
        user_id=user_id,
        action='batch_restore',
        details=f'Restored {restored_files} files and {restored_folders} folders from trash'
    )
    db.session.add(activity)
    db.session.commit()
    
    flash(f'Successfully restored {restored_files} files and {restored_folders} folders', 'success')
    return redirect(url_for('files.trash'))

@files.route('/files/batch_delete', methods=['POST'])
@login_required
def batch_delete():
    user_id = session.get('user_id')
    selected_items = request.form.getlist('selected_items[]')
    
    if not selected_items:
        flash('No items selected for deletion', 'warning')
        return redirect(url_for('files.index'))
    
    deleted_files = 0
    deleted_folders = 0

    def move_folder_to_trash(folder):
        """Recursively move folder and all its contents to trash."""
        moved_files = 0
        moved_folders = 1

        folder.move_to_trash()

        files_in_folder = File.query.filter_by(folder_id=folder.id, user_id=user_id, is_deleted=False).all()
        for file in files_in_folder:
            file.move_to_trash()
            moved_files += 1

        subfolders = Folder.query.filter_by(parent_id=folder.id, user_id=user_id, is_deleted=False).all()
        for subfolder in subfolders:
            sub_files, sub_folders = move_folder_to_trash(subfolder)
            moved_files += sub_files
            moved_folders += sub_folders

        return moved_files, moved_folders
    
    for item in selected_items:
        item_type, item_id = item.split('-')
        item_id = int(item_id)
        
        if item_type == 'file':
            file = File.query.filter_by(id=item_id, user_id=user_id, is_deleted=False).first()
            if file:
                file.move_to_trash()
                deleted_files += 1
        
        elif item_type == 'folder':
            folder = Folder.query.filter_by(id=item_id, user_id=user_id, is_deleted=False).first()
            if folder:
                moved_files, moved_folders = move_folder_to_trash(folder)
                deleted_files += moved_files
                deleted_folders += moved_folders
    
    db.session.commit()
    
    # Recalculate user's storage usage
    user = User.query.get(user_id)
    if user:
        sync_user_storage_used(user)
        db.session.commit()
    
    # Log the activity
    activity_details = {
        'files_count': deleted_files,
        'folders_count': deleted_folders
    }
    
    activity = Activity(
        user_id=user_id,
        action='batch_delete',
        details=json.dumps(activity_details)
    )
    db.session.add(activity)
    db.session.commit()
    
    if deleted_files > 0 and deleted_folders > 0:
        flash(f'Moved {deleted_files} files and {deleted_folders} folders to trash', 'success')
    elif deleted_files > 0:
        flash(f'Moved {deleted_files} files to trash', 'success')
    elif deleted_folders > 0:
        flash(f'Moved {deleted_folders} folders to trash', 'success')
    
    return redirect(url_for('files.index', folder_id=request.args.get('folder_id')))

@files.route('/files/download_folder/<int:folder_id>')
@login_required
def download_folder(folder_id):
    """Stream a folder as ZIP without waiting for full compression."""
    import zipstream  # lazily import to avoid overhead if never used
    user_id = session.get('user_id')
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first_or_404()

    # Helper: recursively yield (filepath, arcname)
    def iter_folder_files(cur_folder, path_in_zip=""):
        # files in current folder
        files = File.query.filter_by(folder_id=cur_folder.id, user_id=user_id, is_deleted=False).all()
        for f in files:
            managed_file_path = resolve_managed_file_path(f.file_path)
            if not managed_file_path:
                continue
            arc = os.path.join(path_in_zip, f.original_filename)
            yield managed_file_path, arc, f.size, f.file_type
        # subfolders
        subfolders = Folder.query.filter_by(parent_id=cur_folder.id, user_id=user_id, is_deleted=False).all()
        for sub in subfolders:
            sub_path = os.path.join(path_in_zip, sub.name)
            # even if folder empty, ZipStream will include parent paths automatically when files present
            yield from iter_folder_files(sub, sub_path)

    # Stream zip
    z = zipstream.ZipFile(mode='w', compression=zipfile.ZIP_DEFLATED)

    total_size = 0
    for file_path, arcname, fsize, ftype in iter_folder_files(folder):
        total_size += fsize
        z.write(file_path, arcname)

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    download_name = f"{folder.name}_{timestamp}.zip"

    # Log activity (size pre-zip)
    activity = Activity(
        user_id=user_id,
        action='download_folder',
        target=folder.name,
        file_size=total_size,
        details='Streamed folder as zip'
    )
    db.session.add(activity)
    db.session.commit()

    from urllib.parse import quote
    ascii_name = secure_filename(download_name) or 'download.zip'
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(download_name)}"

    return Response(
        z,  # zipstream is iterable
        mimetype='application/zip',
        headers={
            'Content-Disposition': disposition,
            'Content-Type': 'application/zip'
        }
    )

@files.route('/files/batch_move', methods=['POST'])
@login_required
def batch_move():
    """Move selected files and folders to a destination folder"""
    user_id = session.get('user_id')
    selected_items = request.form.getlist('selected_items[]')
    destination_id = request.form.get('destination_id', type=int)
    
    if destination_id is None:
        flash('No destination folder selected', 'warning')
        return redirect(request.referrer or url_for('files.index'))
    
    # Ensure destination folder exists and belongs to the user
    destination_folder = Folder.query.filter_by(id=destination_id, user_id=user_id, is_deleted=False).first()
    if not destination_folder:
        flash('Destination folder not found', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    if not selected_items:
        flash('No items selected', 'warning')
        return redirect(request.referrer or url_for('files.index'))
    
    moved_files = 0
    moved_folders = 0
    skipped = 0
    
    # Helper to check if folder_a is descendant of folder_b (with ownership verification)
    def is_descendant(folder_a_id, folder_b_id):
        # 验证目标文件夹所有权
        current = Folder.query.filter_by(id=folder_b_id, user_id=user_id).first()
        while current and current.parent_id is not None:
            if current.parent_id == folder_a_id:
                return True
            # 继续验证父文件夹所有权
            current = Folder.query.filter_by(id=current.parent_id, user_id=user_id).first()
        return False
    
    for item in selected_items:
        try:
            item_type, item_id = item.split('-', 1)
            item_id = int(item_id)
        except ValueError:
            continue
        
        if item_type == 'file':
            file = File.query.filter_by(id=item_id, user_id=user_id, is_deleted=False).first()
            if file and file.folder_id != destination_id:
                file.folder_id = destination_id
                file.updated_at = datetime.utcnow()
                moved_files += 1
        elif item_type == 'folder':
            folder = Folder.query.filter_by(id=item_id, user_id=user_id, is_deleted=False).first()
            # Prevent moving a folder into itself or its descendants
            if folder and folder.id != destination_id and not is_descendant(folder.id, destination_id):
                folder.parent_id = destination_id
                folder.updated_at = datetime.utcnow()
                moved_folders += 1
            else:
                skipped += 1
    
    db.session.commit()
    
    # Recalculate storage usage
    user = User.query.get(user_id)
    if user:
        sync_user_storage_used(user)
        db.session.commit()
    
    # Log activity
    details = {
        'moved_files': moved_files,
        'moved_folders': moved_folders,
        'skipped': skipped,
        'destination_id': destination_id
    }
    activity = Activity(
        user_id=user_id,
        action='batch_move',
        details=json.dumps(details)
    )
    db.session.add(activity)
    db.session.commit()
    
    flash(f'Moved {moved_files} files and {moved_folders} folders', 'success')
    return redirect(url_for('files.index', folder_id=destination_id)) 

@files.route('/files/raw/<int:file_id>')
@login_required
def raw_file(file_id):
    """Serve a file directly for inline preview (no attachment)."""
    user_id = session.get('user_id')
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first_or_404()

    # Determine MIME type for correct rendering in browser
    managed_file_path = resolve_managed_file_path(file.file_path)
    if not managed_file_path:
        return '', 404

    mime_type, _ = mimetypes.guess_type(managed_file_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    return send_file(managed_file_path, mimetype=mime_type, as_attachment=False, download_name=file.original_filename)


@files.route('/files/preview/<int:file_id>')
@login_required
def preview_file(file_id):
    """Render a preview page for a given file."""
    user_id = session.get('user_id')
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first_or_404()

    return render_template('files/preview.html', file=file) 

@files.route('/files/remote_download', methods=['POST'])
@login_required
def remote_download():
    """Download a remote file directly into the user's cloud storage."""
    import requests

    user_id = session.get('user_id')
    file_url = request.form.get('file_url', '').strip()
    folder_id = request.form.get('folder_id', type=int)

    try:
        validate_remote_download_url(file_url)
    except ValueError as exc:
        flash('Invalid URL' if str(exc) == 'Invalid URL' else 'Blocked remote address', 'danger')
        return redirect(url_for('files.index'))

    # Determine current folder
    if folder_id:
        current_folder = Folder.query.filter_by(id=folder_id, user_id=user_id).first()
    else:
        current_folder = Folder.query.filter_by(user_id=user_id, parent_id=None).first()
    if not current_folder:
        current_folder = Folder(name='root', user_id=user_id)
        db.session.add(current_folder)
        db.session.commit()

    # Placeholder filename from URL path; will refine after HTTP headers
    parsed = urlparse(file_url)
    filename = normalize_item_name(unquote(os.path.basename(parsed.path))) or ''

    try:
        # Max upload size from settings (default 2TB)
        max_size_setting = SystemSetting.query.filter_by(key='max_upload_size').first()
        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 2000 * 1024 * 1024 * 1024)
        if max_size_setting:
            try:
                max_size = int(max_size_setting.get_typed_value())
            except (TypeError, ValueError):
                pass

        with create_remote_download_session() as remote_session:
            current_url = file_url
            response_obj = None
            remote_request = prepare_remote_request(current_url)

            for _ in range(2):
                request_headers = dict(remote_request['headers'])

                with closing(
                    remote_session.get(
                        remote_request['direct_url'],
                        headers=request_headers,
                        stream=True,
                        timeout=30,
                        allow_redirects=False,
                        verify=remote_request['verify'],
                    )
                ) as response:
                    if 300 <= response.status_code < 400:
                        redirect_target = response.headers.get('Location')
                        if not redirect_target:
                            raise ValueError('Invalid URL')
                        current_url = requests.compat.urljoin(current_url, redirect_target)
                        remote_request = prepare_remote_request(current_url)
                        continue

                    response.raise_for_status()
                    response_obj = response
                    break

            if response_obj is None:
                raise ValueError('Invalid URL')

            r = response_obj
            file_url = current_url

            # Try to get filename from Content-Disposition header
            cd_header = r.headers.get('Content-Disposition')
            if cd_header:
                from werkzeug.http import parse_options_header
                _, params = parse_options_header(cd_header)
                fname = params.get('filename') or params.get('filename*')
                if fname:
                    filename = normalize_item_name(unquote(fname.split("''")[-1])) or filename

            # If still no extension, try to derive from content-type
            if filename and '.' not in filename and r.headers.get('Content-Type'):
                ext = mimetypes.guess_extension(r.headers['Content-Type'].split(';')[0].strip())
                if ext:
                    filename = normalize_item_name(f'{filename}{ext}') or filename

            if not filename:
                filename = 'downloaded_file'

            if not allowed_file(filename):
                flash('File type not allowed', 'danger')
                return redirect(url_for('files.index'))

            file_size = int(r.headers.get('Content-Length', 0))
            user = User.query.get(user_id)
            if file_size and file_size > max_size:
                flash('File too large', 'danger')
                return redirect(url_for('files.index'))

            if file_size and not user.has_space_for_file(file_size):
                flash('Not enough storage space', 'danger')
                return redirect(url_for('files.index'))

            if file_name_exists(user_id, current_folder.id, filename):
                name_prefix, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{name_prefix}_{timestamp}{ext}"

            storage_filename = build_storage_filename(filename)
            folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_folder.id))
            os.makedirs(folder_path, exist_ok=True)
            save_path = os.path.join(folder_path, storage_filename)

            downloaded = 0
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > max_size:
                            raise ValueError('File too large')
                        f.write(chunk)

        if not file_size:
            file_size = os.path.getsize(save_path)
            user = User.query.get(user_id)
            if not user.has_space_for_file(file_size):
                os.remove(save_path)
                flash('Not enough storage space', 'danger')
                return redirect(url_for('files.index'))

        file_type = get_file_type(filename)
        new_file = File(
            filename=storage_filename,
            original_filename=filename,
            file_path=save_path,
            size=file_size,
            file_type=file_type,
            user_id=user_id,
            folder_id=current_folder.id
        )
        db.session.add(new_file)
        sync_user_storage_used(User.query.get(user_id))

        activity = Activity(
            user_id=user_id,
            action='remote_download',
            target=filename,
            file_size=file_size,
            file_type=file_type,
            details=f'Downloaded from {file_url}'
        )
        db.session.add(activity)
        db.session.commit()

        flash('File downloaded successfully', 'success')
    except ValueError as e:
        if str(e) == 'File too large':
            if 'save_path' in locals() and os.path.exists(save_path):
                os.remove(save_path)
            flash('File too large', 'danger')
        elif str(e) == 'Blocked remote address':
            flash('Blocked remote address', 'danger')
        else:
            print(f"Remote download error: {e}")
            flash('Failed to download file', 'danger')
    except Exception as e:
        print(f"Remote download error: {e}")
        if 'save_path' in locals() and os.path.exists(save_path):
            os.remove(save_path)
        flash('Failed to download file', 'danger')
    return redirect(url_for('files.index', folder_id=current_folder.id))
