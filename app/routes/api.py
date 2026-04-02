from typing import Callable, Optional
from flask import Blueprint, request, jsonify, session, g, current_app
from app.extensions import db
from app.models.user import User
from app.models.file import File, Folder
from app.models.system import SystemMetric
from app.models.system_setting import SystemSetting
from app.security_policy import (
    log_security_event, SecureErrorHandler, sanitize_error_message,
    PasswordPolicy, LoginLockout
)
from app.utils.security_logger import SensitiveDataMasker  # 修复: 敏感日志脱敏
from functools import wraps
import base64
import datetime
import psutil
import os
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from app import csrf

api = Blueprint('api', __name__)

# Exempt all API routes from CSRF since they use Basic Auth
csrf.exempt(api)

def _safe_disk_usage(path: str):
    try:
        return psutil.disk_usage(path)
    except Exception:
        fallback = os.path.abspath(os.sep)
        return psutil.disk_usage(fallback)

def _parse_basic_auth(auth_header: str) -> tuple[str, str]:
    if not auth_header or 'Basic ' not in auth_header:
        raise ValueError('Authentication required')

    encoded_credentials = auth_header.split(' ', 1)[1].strip()
    if not encoded_credentials:
        raise ValueError('Invalid credentials')

    # Try standard Basic auth (base64), fallback to plain user:pass if provided
    try:
        decoded = base64.b64decode(encoded_credentials).decode('utf-8')
    except Exception:
        decoded = encoded_credentials

    if ':' not in decoded:
        raise ValueError('Invalid credentials')

    username, password = decoded.split(':', 1)
    if not username or not password:
        raise ValueError('Invalid credentials')

    return username, password


# API authentication
def api_login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        try:
            username, password = _parse_basic_auth(auth_header)

            user = User.query.filter_by(username=username).first()

            if not user or not user.verify_password(password):
                # 记录API认证失败
                log_security_event(
                    'api_auth_failed',
                    f"API authentication failed for user: {username}",
                    username=username,
                    level='WARNING'
                )
                return jsonify({'error': SecureErrorHandler.get_message('auth_failed')}), 401

            # Store user in g for this request
            g.user = user
            
            # 记录API认证成功
            log_security_event(
                'api_auth_success',
                f"API authentication successful",
                user_id=user.id,
                username=user.username,
                level='INFO'
            )
            
            return f(*args, **kwargs)
        except ValueError as e:
            # 记录认证错误
            log_security_event(
                'api_auth_error',
                f"API authentication error: {str(e)}",
                level='WARNING'
            )
            return jsonify({'error': SecureErrorHandler.get_message('auth_failed')}), 401
        except Exception as e:
            # 记录异常（不暴露详细信息）
            log_security_event(
                'api_auth_exception',
                f"API authentication exception: {type(e).__name__}",
                level='ERROR'
            )
            return jsonify({'error': SecureErrorHandler.get_message('server_error')}), 500

    return decorated_function


def api_admin_required(f: Callable) -> Callable:
    """
    API admin privilege decorator with real-time role verification.
    
    Security features:
    1. Real-time database query for user role (not relying solely on cached data)
    2. Role change detection - detects if user's role was changed after login
    3. Comprehensive audit logging for security events
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')

        try:
            username, password = _parse_basic_auth(auth_header)

            user = User.query.filter_by(username=username).first()

            if not user or not user.verify_password(password):
                # 记录API认证失败
                log_security_event(
                    'api_admin_auth_failed',
                    f"API admin authentication failed for user: {username}",
                    username=username,
                    level='WARNING'
                )
                return jsonify({'error': SecureErrorHandler.get_message('auth_failed')}), 401

            # Real-time admin role check - query database every time
            if user.role != 'admin':
                # Log failed admin access attempt for audit
                log_security_event(
                    'api_admin_access_denied',
                    f"User {user.id} ({user.username}) attempted admin operation with role '{user.role}'",
                    user_id=user.id,
                    username=user.username,
                    level='WARNING'
                )
                return jsonify({'error': SecureErrorHandler.get_message('permission_denied')}), 403

            # Store user in g for this request
            g.user = user
            
            # 记录管理员API访问
            log_security_event(
                'api_admin_access',
                f"Admin API access granted",
                user_id=user.id,
                username=user.username,
                level='INFO'
            )
            
            return f(*args, **kwargs)
        except ValueError as e:
            return jsonify({'error': SecureErrorHandler.get_message('auth_failed')}), 401
        except Exception as e:
            # 记录异常（不暴露详细信息）
            current_app.logger.error(f"API admin auth error: {type(e).__name__}")
            return jsonify({'error': SecureErrorHandler.get_message('auth_failed')}), 401

    return decorated_function


# =============================================================================
# 安全的API错误处理装饰器
# =============================================================================

def api_error_handler(f: Callable) -> Callable:
    """包装API函数，提供统一的错误处理"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            # 记录错误详情到日志
            error_msg = sanitize_error_message(str(e))
            log_security_event(
                'api_error',
                f"API error in {f.__name__}: {error_msg}",
                level='ERROR'
            )
            # 返回安全的错误消息
            return jsonify({'error': SecureErrorHandler.get_message('server_error')}), 500
    return decorated_function


# User API endpoints
@api.route('/api/user/info')
@api_login_required
@api_error_handler
def user_info():
    user = g.user
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'storage_quota': user.storage_quota,
        'storage_used': user.storage_used,
        'storage_percent': user.get_storage_usage_percent(),
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None
    })

# File API endpoints
@api.route('/api/files')
@api_login_required
@api_error_handler
def list_files():
    user = g.user
    folder_id = request.args.get('folder_id', type=int)
    
    if folder_id:
        folder = Folder.query.filter_by(id=folder_id, user_id=user.id, is_deleted=False).first()
        if not folder:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
        files = File.query.filter_by(folder_id=folder_id, user_id=user.id, is_deleted=False).all()
        subfolders = Folder.query.filter_by(parent_id=folder_id, user_id=user.id, is_deleted=False).all()
    else:
        # Get root folder
        folder = Folder.query.filter_by(user_id=user.id, parent_id=None, is_deleted=False).first()
        if not folder:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
        
        files = File.query.filter_by(folder_id=folder.id, user_id=user.id, is_deleted=False).all()
        subfolders = Folder.query.filter_by(parent_id=folder.id, user_id=user.id, is_deleted=False).all()
    
    # Convert to dict for JSON response
    folder_dict = folder.to_dict() if folder else None
    files_list = [file.to_dict() for file in files]
    subfolders_list = [subfolder.to_dict() for subfolder in subfolders]
    
    return jsonify({
        'folder': folder_dict,
        'files': files_list,
        'subfolders': subfolders_list
    })

@api.route('/api/folders/create', methods=['POST'])
@api_login_required
@api_error_handler
def api_create_folder():
    user = g.user
    data = request.json
    if not data:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    folder_name = data.get('name')
    parent_id = data.get('parent_id')

    from app.routes.files import normalize_item_name, folder_name_exists

    folder_name = normalize_item_name(folder_name)

    if not folder_name:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400

    if parent_id is not None:
        parent = Folder.query.filter_by(id=parent_id, user_id=user.id, is_deleted=False).first()
        if not parent:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    # Check if folder already exists in the same parent
    if folder_name_exists(user.id, parent_id, folder_name):
        return jsonify({'error': 'A folder with this name already exists'}), 400
    
    # Create new folder
    new_folder = Folder(
        name=folder_name,
        user_id=user.id,
        parent_id=parent_id
    )
    
    db.session.add(new_folder)
    db.session.commit()
    
    # 记录文件夹创建
    log_security_event(
        'folder_created',
        f"Folder created: {folder_name}",
        user_id=user.id,
        username=user.username,
        level='INFO'
    )
    
    return jsonify({'success': True, 'folder': new_folder.to_dict()})

@api.route('/api/files/upload', methods=['POST'])
@api_login_required
@api_error_handler
def api_upload_file():
    user = g.user
    folder_id = request.form.get('folder_id', type=int)
    
    if 'file' not in request.files:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    uploaded_file = request.files['file']
    
    if uploaded_file.filename == '':
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    # Validate filename to prevent path traversal
    from app.routes.files import normalize_item_name
    safe_filename = normalize_item_name(uploaded_file.filename)
    if not safe_filename:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    uploaded_file.filename = safe_filename
    
    # Resolve destination folder (default to root)
    if folder_id:
        folder = Folder.query.filter_by(id=folder_id, user_id=user.id, is_deleted=False).first()
        if not folder:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    else:
        folder = Folder.query.filter_by(user_id=user.id, parent_id=None, is_deleted=False).first()
        if not folder:
            folder = Folder(name='root', user_id=user.id)
            db.session.add(folder)
            db.session.commit()

    # Get max upload size from settings
    max_size_setting = SystemSetting.query.filter_by(key='max_upload_size').first()
    max_size = 1024 * 1024 * 1024  # Default 1GB
    if max_size_setting:
        try:
            max_size = int(max_size_setting.get_typed_value())
        except (TypeError, ValueError):
            pass
    
    # Check file size
    uploaded_file.seek(0, os.SEEK_END)
    file_size = uploaded_file.tell()
    uploaded_file.seek(0)
    
    if file_size > max_size:
        return jsonify({'error': 'File too large'}), 400
    
    # Check if user has enough space
    if not user.has_space_for_file(file_size):
        return jsonify({'error': 'Not enough storage space'}), 400
    
    # Validate file type using shared logic
    from app.routes.files import allowed_file, get_file_type, normalize_item_name, build_storage_filename, sync_user_storage_used
    original_filename = normalize_item_name(uploaded_file.filename)
    if not original_filename:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400

    if not allowed_file(original_filename):
        return jsonify({'error': 'File type not allowed'}), 400

    # Save file
    # Generate unique filename to avoid conflicts
    filename = build_storage_filename(original_filename)
    
    # Create uploads directory if it doesn't exist (use folder id for consistency)
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], str(folder.id))
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    file_path = os.path.join(upload_dir, filename)
    uploaded_file.save(file_path)
    
    # Create file record in database
    file_type = get_file_type(original_filename)
    new_file = File(
        filename=filename,
        original_filename=original_filename,
        file_path=file_path,
        size=file_size,
        file_type=file_type,
        user_id=user.id,
        folder_id=folder.id
    )
    
    db.session.add(new_file)
    sync_user_storage_used(user)
    db.session.commit()
    
    return jsonify({'success': True, 'file': new_file.to_dict()})


# =============================================================================
# 文件操作 API 端点 - 修复 IDOR 水平越权漏洞
# =============================================================================

def verify_file_ownership_api(file_id: int, user_id: int) -> Optional[File]:
    """验证文件所有权并返回文件对象，如果不存在或无权访问则返回None"""
    return File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first()

def verify_folder_ownership_api(folder_id: int, user_id: int) -> Optional[Folder]:
    """验证文件夹所有权并返回文件夹对象，如果不存在或无权访问则返回None"""
    return Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first()

@api.route('/api/files/<int:file_id>', methods=['GET'])
@api_login_required
@api_error_handler
def api_get_file(file_id):
    """获取单个文件信息"""
    user = g.user
    file = verify_file_ownership_api(file_id, user.id)
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    return jsonify({'success': True, 'file': file.to_dict()})

@api.route('/api/files/<int:file_id>/download', methods=['GET'])
@api_login_required
@api_error_handler
def api_download_file(file_id):
    """下载文件 - 带权限验证"""
    from flask import send_file
    import mimetypes
    
    user = g.user
    file = verify_file_ownership_api(file_id, user.id)
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    # 验证文件路径安全
    from app.routes.files import resolve_managed_file_path
    managed_file_path = resolve_managed_file_path(file.file_path)
    if not managed_file_path:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    # 确定 MIME 类型
    mime_type, _ = mimetypes.guess_type(file.original_filename)
    if mime_type is None:
        mime_type = 'application/octet-stream'
    
    # 记录文件下载
    log_security_event(
        'file_downloaded',
        f"File downloaded: {file.original_filename}",
        user_id=user.id,
        username=user.username,
        level='INFO'
    )
    
    return send_file(
        managed_file_path,
        mimetype=mime_type,
        as_attachment=True,
        download_name=file.original_filename
    )

@api.route('/api/files/<int:file_id>', methods=['DELETE'])
@api_login_required
@api_error_handler
def api_delete_file(file_id):
    """删除文件（移动到回收站）- 带权限验证"""
    from app.routes.files import sync_user_storage_used
    
    user = g.user
    file = verify_file_ownership_api(file_id, user.id)
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    file_name = file.original_filename
    file.move_to_trash()
    sync_user_storage_used(user)
    db.session.commit()
    
    # 记录文件删除
    log_security_event(
        'file_deleted',
        f"File moved to trash: {file_name}",
        user_id=user.id,
        username=user.username,
        level='INFO'
    )
    
    return jsonify({
        'success': True,
        'message': f'File "{file_name}" moved to trash'
    })

@api.route('/api/files/<int:file_id>/permanent_delete', methods=['DELETE'])
@api_login_required
@api_error_handler
def api_permanent_delete_file(file_id):
    """永久删除文件 - 带权限验证"""
    from app.routes.files import sync_user_storage_used
    
    user = g.user
    # 查询包括已删除的文件（在回收站中）
    file = File.query.filter_by(id=file_id, user_id=user.id, is_deleted=True).first()
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    file_name = file.original_filename
    file.permanently_delete()
    sync_user_storage_used(user)
    db.session.commit()
    
    # 记录永久删除
    log_security_event(
        'file_permanently_deleted',
        f"File permanently deleted: {file_name}",
        user_id=user.id,
        username=user.username,
        level='WARNING'
    )
    
    return jsonify({
        'success': True,
        'message': f'File "{file_name}" permanently deleted'
    })

@api.route('/api/files/<int:file_id>/restore', methods=['POST'])
@api_login_required
@api_error_handler
def api_restore_file(file_id):
    """从回收站恢复文件 - 带权限验证"""
    from app.routes.files import sync_user_storage_used
    
    user = g.user
    file = File.query.filter_by(id=file_id, user_id=user.id, is_deleted=True).first()
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    file.restore_from_trash()
    sync_user_storage_used(user)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'File "{file.original_filename}" restored'
    })

@api.route('/api/files/<int:file_id>/rename', methods=['PUT', 'PATCH'])
@api_login_required
@api_error_handler
def api_rename_file(file_id):
    """重命名文件 - 带权限验证"""
    user = g.user
    file = verify_file_ownership_api(file_id, user.id)
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    from app.routes.files import normalize_item_name, file_name_exists
    
    new_name = normalize_item_name(data.get('name'))
    if not new_name:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    # 保留文件扩展名
    if '.' in file.original_filename and '.' not in new_name:
        extension = file.original_filename.rsplit('.', 1)[1]
        new_name = f"{new_name}.{extension}"
    
    # 检查同名文件
    if file_name_exists(user.id, file.folder_id, new_name, exclude_file_id=file.id):
        return jsonify({'error': 'A file with this name already exists'}), 409
    
    old_name = file.original_filename
    file.original_filename = new_name
    file.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    
    # 记录重命名
    log_security_event(
        'file_renamed',
        f"File renamed from '{old_name}' to '{new_name}'",
        user_id=user.id,
        username=user.username,
        level='INFO'
    )
    
    return jsonify({
        'success': True,
        'message': 'File renamed successfully',
        'file': file.to_dict()
    })

@api.route('/api/files/<int:file_id>/move', methods=['PUT', 'PATCH'])
@api_login_required
@api_error_handler
def api_move_file(file_id):
    """移动文件到指定文件夹 - 带权限验证"""
    user = g.user
    file = verify_file_ownership_api(file_id, user.id)
    if not file:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    data = request.json
    if not data or 'folder_id' not in data:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    target_folder_id = data.get('folder_id')
    
    # 验证目标文件夹所有权
    if target_folder_id is not None:
        target_folder = verify_folder_ownership_api(target_folder_id, user.id)
        if not target_folder:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    file.folder_id = target_folder_id
    file.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'File moved successfully',
        'file': file.to_dict()
    })

# =============================================================================
# 文件夹操作 API 端点 - 修复 IDOR 水平越权漏洞
# =============================================================================

@api.route('/api/folders/<int:folder_id>', methods=['GET'])
@api_login_required
@api_error_handler
def api_get_folder(folder_id):
    """获取单个文件夹信息"""
    user = g.user
    folder = verify_folder_ownership_api(folder_id, user.id)
    if not folder:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    return jsonify({'success': True, 'folder': folder.to_dict()})

@api.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@api_login_required
@api_error_handler
def api_delete_folder(folder_id):
    """删除文件夹（移动到回收站）- 带权限验证"""
    from app.routes.files import sync_user_storage_used, get_user_files_in_folder, get_user_subfolders
    
    user = g.user
    folder = verify_folder_ownership_api(folder_id, user.id)
    if not folder:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    folder.move_to_trash()
    
    # 递归移动所有子文件夹和文件到回收站
    def trash_subfolders_recursively(parent_id):
        subfolders = get_user_subfolders(parent_id, user.id, include_deleted=False)
        for subfolder in subfolders:
            subfolder.move_to_trash()
            files = get_user_files_in_folder(subfolder.id, user.id, include_deleted=False)
            for file in files:
                file.move_to_trash()
            trash_subfolders_recursively(subfolder.id)
    
    # 移动当前文件夹中的所有文件
    folder_files = get_user_files_in_folder(folder.id, user.id, include_deleted=False)
    for file in folder_files:
        file.move_to_trash()
    
    trash_subfolders_recursively(folder.id)
    sync_user_storage_used(user)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': f'Folder "{folder.name}" moved to trash'
    })

@api.route('/api/folders/<int:folder_id>/rename', methods=['PUT', 'PATCH'])
@api_login_required
@api_error_handler
def api_rename_folder(folder_id):
    """重命名文件夹 - 带权限验证"""
    user = g.user
    folder = verify_folder_ownership_api(folder_id, user.id)
    if not folder:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    from app.routes.files import normalize_item_name, folder_name_exists
    
    new_name = normalize_item_name(data.get('name'))
    if not new_name:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    # 检查同名文件夹
    if folder_name_exists(user.id, folder.parent_id, new_name, exclude_folder_id=folder.id):
        return jsonify({'error': 'A folder with this name already exists'}), 409
    
    folder.name = new_name
    folder.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Folder renamed successfully',
        'folder': folder.to_dict()
    })

@api.route('/api/folders/<int:folder_id>/move', methods=['PUT', 'PATCH'])
@api_login_required
@api_error_handler
def api_move_folder(folder_id):
    """移动文件夹到指定位置 - 带权限验证"""
    user = g.user
    folder = verify_folder_ownership_api(folder_id, user.id)
    if not folder:
        return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    data = request.json
    if not data or 'parent_id' not in data:
        return jsonify({'error': SecureErrorHandler.get_message('invalid_input')}), 400
    
    target_parent_id = data.get('parent_id')
    
    # 防止移动到自身
    if target_parent_id == folder.id:
        return jsonify({'error': 'Cannot move a folder into itself'}), 400
    
    # 验证目标父文件夹所有权
    if target_parent_id is not None:
        target_parent = verify_folder_ownership_api(target_parent_id, user.id)
        if not target_parent:
            return jsonify({'error': SecureErrorHandler.get_message('resource_not_found')}), 404
    
    # 防止移动到子文件夹中（循环引用检查）
    def is_descendant(folder_a_id, folder_b_id):
        current = Folder.query.filter_by(id=folder_b_id, user_id=user.id).first()
        while current and current.parent_id is not None:
            if current.parent_id == folder_a_id:
                return True
            current = Folder.query.filter_by(id=current.parent_id, user_id=user.id).first()
        return False
    
    if target_parent_id is not None and is_descendant(folder.id, target_parent_id):
        return jsonify({'error': 'Cannot move a folder into its own subfolder'}), 400
    
    folder.parent_id = target_parent_id
    folder.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'Folder moved successfully',
        'folder': folder.to_dict()
    })

@api.route('/api/admin/users')
@api_admin_required
@api_error_handler
def api_list_users():
    users = User.query.all()
    users_list = []
    
    for user in users:
        users_list.append({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'storage_quota': user.storage_quota,
            'storage_used': user.storage_used,
            'storage_percent': user.get_storage_usage_percent(),
            'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'last_login': user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else None
        })
    
    return jsonify({'users': users_list})

@api.route('/api/admin/system/stats')
@api_admin_required
@api_error_handler
def api_system_stats():
    # Get real-time system stats
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk_path = current_app.config.get('UPLOAD_FOLDER', os.path.abspath(os.sep))
    disk = _safe_disk_usage(disk_path)
    net_io_counters = psutil.net_io_counters()
    
    # Record metrics
    new_metric = SystemMetric(
        cpu_usage=cpu_percent,
        memory_usage=memory.percent,
        disk_usage=disk.percent,
        network_rx=net_io_counters.bytes_recv,
        network_tx=net_io_counters.bytes_sent,
        active_connections=len(psutil.net_connections())
    )
    
    db.session.add(new_metric)
    db.session.commit()
    
    return jsonify({
        'cpu': {
            'percent': cpu_percent
        },
        'memory': {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent
        },
        'network': {
            'bytes_sent': net_io_counters.bytes_sent,
            'bytes_recv': net_io_counters.bytes_recv,
            'packets_sent': net_io_counters.packets_sent,
            'packets_recv': net_io_counters.packets_recv
        },
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@api.route('/api/admin/metrics/history')
@api_admin_required
@api_error_handler
def api_metrics_history():
    hours = request.args.get('hours', 24, type=int)
    
    # Get metrics for the specified time period
    since = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    metrics = SystemMetric.query.filter(SystemMetric.timestamp >= since).order_by(SystemMetric.timestamp).all()
    
    metrics_list = []
    for metric in metrics:
        metrics_list.append(metric.to_dict())
    
    return jsonify({'metrics': metrics_list})
