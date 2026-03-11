from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, jsonify, send_file, session, Response
from app.extensions import db
from app.models.user import User
from app.models.file import File, Folder
from app.models.system_setting import SystemSetting
from app.models.activity import Activity
from app.routes.auth import login_required
from werkzeug.utils import secure_filename
import os
import uuid
from datetime import datetime
import mimetypes
import time
from flask import after_this_request
import json
import zipfile
import io
from app.utils.transfer_tracker import TransferSpeedTracker
import shutil  # 新增，用于磁盘空间检测

files = Blueprint('files', __name__)

def allowed_file(filename):
    # Get allowed file types from system settings
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
    
    # Default allowed extensions if setting not found
    return '.' in filename

def get_file_type(filename):
    extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    mime_type, _ = mimetypes.guess_type(filename)
    
    # Categorize files
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
    
    # Based on extension
    if extension in ['zip', 'rar', '7z', 'tar', 'gz']:
        return 'archive'
    
    return 'other'

def get_free_space(path):
    """Return free space (in bytes) for the disk containing the given path"""
    try:
        usage = shutil.disk_usage(path)
        return usage.free
    except Exception as e:
        print(f"Error getting free space for {path}: {e}")
        # 如果无法获取，返回0表示空间不足
        return 0

@files.route('/files')
@login_required
def index():
    user_id = session.get('user_id')
    folder_id = request.args.get('folder_id', type=int)
    
    # Get user's folders
    if folder_id:
        current_folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first_or_404()
        parent_folder = Folder.query.filter_by(id=current_folder.parent_id).first() if current_folder.parent_id else None
    else:
        # Get root folder
        current_folder = Folder.query.filter_by(user_id=user_id, parent_id=None, is_deleted=False).first()
        if not current_folder:
            # Create root folder if it doesn't exist
            current_folder = Folder(name='root', user_id=user_id)
            db.session.add(current_folder)
            db.session.commit()
        parent_folder = None
    
    # Get subfolders and files in current folder
    subfolders = Folder.query.filter_by(parent_id=current_folder.id, user_id=user_id, is_deleted=False).all()
    files = File.query.filter_by(folder_id=current_folder.id, user_id=user_id, is_deleted=False).all()
    
    # Get user's storage info and refresh usage to ensure accuracy
    user = User.query.get(user_id)
    storage_used = user.update_storage_used()
    storage_quota = user.storage_quota
    storage_percent = (storage_used / storage_quota) * 100 if storage_quota > 0 else 100
    
    # Fetch all folders for move-to selection (excluding deleted)
    all_folders = Folder.query.filter_by(user_id=user_id, is_deleted=False).all()
    
    return render_template('files/index.html', 
                          current_folder=current_folder,
                          parent_folder=parent_folder,
                          subfolders=subfolders,
                          files=files,
                          storage_used=storage_used,
                          storage_quota=storage_quota,
                          storage_percent=storage_percent,
                          all_folders=all_folders)

@files.route('/files/upload', methods=['POST'])
@login_required
def upload_file():
    """Handle file upload, supporting both regular file and folder uploads"""
    user_id = session.get('user_id')
    is_folder_upload = request.form.get('is_folder_upload') == 'true'
    folder_id = request.form.get('folder_id', type=int)
    
    if not request.files.getlist('files[]'):
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
                filename = path_parts.pop()  # Last part is the filename
                
                # Create folder structure
                current_path = ""
                for folder_name in path_parts:
                    if not folder_name:  # Skip empty folder names
                        continue
                    
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
                        
                        created_folders[current_path] = parent_folder
            else:
                filename = os.path.basename(relative_path)

            if not filename:
                continue
            
            # Check if file with same name exists
            existing_file = File.query.filter_by(
                original_filename=filename,
                folder_id=parent_folder.id,
                user_id=user_id,
                is_deleted=False
            ).first()
            
            if existing_file:
                # Add timestamp to make filename unique
                name_parts = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
            
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
            storage_filename = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
            
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
                
                # Update user storage quota
                user.storage_used += file_size
                
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
        print(f"Error committing changes: {str(e)}")
        flash('Error saving files to database', 'danger')
        return redirect(url_for('files.index'))
    
    # Show appropriate message
    if uploaded_count == 0:
        flash('No files were uploaded', 'warning')
    elif error_count > 0:
        flash(f'{uploaded_count} files uploaded successfully, {error_count} failed', 'info')
    else:
        flash(f'All {uploaded_count} files uploaded successfully', 'success')
    
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

    # Determine mime type from filename for better browser handling
    mime_type, _ = mimetypes.guess_type(file.original_filename)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    response = send_file(
        file.file_path,
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
        
        # Function to recursively get all subfolders
        def get_subfolder_tree(parent_folder):
            result = {
                'folder': parent_folder,
                'subfolders': [],
                'files': File.query.filter_by(folder_id=parent_folder.id, is_deleted=True).all()
            }
            
            # Find all direct subfolders
            direct_subfolders = Folder.query.filter_by(parent_id=parent_folder.id, is_deleted=True).all()
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
    storage_used = user.update_storage_used()
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
    print(f"Found file to restore: {file.original_filename}")
    
    # Restore file
    file.restore_from_trash()
    
    # If parent folder (or any ancestor) is still deleted, restore it as well
    def restore_parent_folders(folder_id):
        if folder_id is None:
            return
        parent_folder = Folder.query.filter_by(id=folder_id).first()
        if parent_folder and parent_folder.is_deleted:
            parent_folder.restore_from_trash()
            restore_parent_folders(parent_folder.parent_id)

    restore_parent_folders(file.folder_id)
    
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
    
    # Restore folder
    folder.restore_from_trash()
    
    # Also restore all files in this folder
    files_count = 0
    for file in File.query.filter_by(folder_id=folder.id, is_deleted=True).all():
        file.restore_from_trash()
        files_count += 1
    
    # Recursively restore all subfolders and their contents
    folders_count = 0
    def restore_subfolders_recursively(parent_id):
        nonlocal folders_count
        subfolders = Folder.query.filter_by(parent_id=parent_id, is_deleted=True).all()
        for subfolder in subfolders:
            subfolder.restore_from_trash()
            folders_count += 1
            
            # Restore all files in this subfolder
            for file in File.query.filter_by(folder_id=subfolder.id, is_deleted=True).all():
                file.restore_from_trash()
                files_count += 1
            
            # Recursively restore sub-subfolders
            restore_subfolders_recursively(subfolder.id)
    
    # Execute recursive restoration
    restore_subfolders_recursively(folder.id)
    
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
        db.session.commit()
        flash(f'File "{file_name}" permanently deleted', 'success')
    else:   
        # Move to trash
        file.move_to_trash()
        # Update user's storage usage
        user.storage_used -= file.size
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
        user.update_storage_used()
    
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
        
        # Get all files in this folder
        files_in_folder = File.query.filter_by(folder_id=folder.id).all()
        for file in files_in_folder:
            file.permanently_delete()
        
        # Handle subfolders recursively
        def delete_subfolders_recursively(parent_id):
            subfolders = Folder.query.filter_by(parent_id=parent_id).all()
            for subfolder in subfolders:
                # Delete all files in this subfolder
                for file in File.query.filter_by(folder_id=subfolder.id).all():
                    file.permanently_delete()
                
                # Recursively handle sub-subfolders
                delete_subfolders_recursively(subfolder.id)
                
                # Delete the subfolder itself
                db.session.delete(subfolder)
        
        # Execute recursive deletion
        delete_subfolders_recursively(folder.id)
        
        # Finally delete the main folder
        db.session.delete(folder)
        db.session.commit()
        flash(f'Folder "{folder_name}" permanently deleted', 'success')
    else:
        # Move to trash
        folder.move_to_trash()
        user = User.query.get(user_id)
        total_moved_size = 0
        
        # Also mark all contained files as deleted
        for file in File.query.filter_by(folder_id=folder.id, is_deleted=False).all():
            total_moved_size += file.size
            file.move_to_trash()
        
        # And all subfolders
        def trash_subfolders_recursively(parent_id):
            nonlocal total_moved_size
            subfolders = Folder.query.filter_by(parent_id=parent_id, is_deleted=False).all()
            for subfolder in subfolders:
                subfolder.move_to_trash()
                
                # Move all files in subfolder to trash
                for file in File.query.filter_by(folder_id=subfolder.id, is_deleted=False).all():
                    total_moved_size += file.size
                    file.move_to_trash()
                
                # Recursively handle sub-subfolders
                trash_subfolders_recursively(subfolder.id)
        
        # Execute recursive trash operation
        trash_subfolders_recursively(folder.id)
        
        # Deduct storage usage
        if user:
            user.storage_used = max(user.storage_used - total_moved_size, 0)
            # Ensure consistency using helper
            user.update_storage_used()
        
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
        user.update_storage_used()
    
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
        user.update_storage_used()
    
    flash('Trash emptied successfully', 'success')
    return redirect(url_for('files.trash'))

@files.route('/folders/create', methods=['POST'])
@login_required
def create_folder():
    user_id = session.get('user_id')
    folder_name = request.form.get('folder_name')
    parent_id = request.form.get('parent_id', type=int)
    
    if not folder_name:
        flash('Folder name is required', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    # Check if folder already exists in the same parent
    existing_folder = Folder.query.filter_by(
        name=folder_name, 
        parent_id=parent_id,
        user_id=user_id,
        is_deleted=False
    ).first()
    
    if existing_folder:
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
    query = request.args.get('query', '')
    
    if not query:
        return redirect(url_for('files.index'))
    
    # Search for files and folders matching the query
    files = File.query.filter(
        File.user_id == user_id,
        File.is_deleted == False,
        File.original_filename.like(f'%{query}%')
    ).all()
    
    folders = Folder.query.filter(
        Folder.user_id == user_id,
        Folder.is_deleted == False,
        Folder.name.like(f'%{query}%')
    ).all()
    
    return render_template('files/search.html', query=query, files=files, folders=folders)

@files.route('/files/rename/<int:file_id>', methods=['POST'])
@login_required
def rename_file(file_id):
    user_id = session.get('user_id')
    new_name = request.form.get('new_name')
    
    if not new_name:
        flash('File name is required', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    file = File.query.filter_by(id=file_id, user_id=user_id, is_deleted=False).first_or_404()
    
    # Keep the file extension
    if '.' in file.original_filename and '.' not in new_name:
        extension = file.original_filename.rsplit('.', 1)[1]
        new_name = f"{new_name}.{extension}"
    
    file.original_filename = secure_filename(new_name)
    file.updated_at = datetime.utcnow()
    
    db.session.commit()
    
    flash('File renamed successfully', 'success')
    return redirect(request.referrer or url_for('files.index'))

@files.route('/files/rename_folder/<int:folder_id>', methods=['POST'])
@login_required
def rename_folder(folder_id):
    user_id = session.get('user_id')
    new_name = request.form.get('new_name')
    
    if not new_name:
        flash('Folder name is required', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    folder = Folder.query.filter_by(id=folder_id, user_id=user_id, is_deleted=False).first_or_404()
    
    # Check if a folder with this name already exists in the same parent
    existing_folder = Folder.query.filter_by(
        name=new_name, 
        parent_id=folder.parent_id,
        user_id=user_id,
        is_deleted=False
    ).first()
    
    if existing_folder and existing_folder.id != folder_id:
        flash('A folder with this name already exists', 'danger')
        return redirect(request.referrer or url_for('files.index'))
    
    folder.name = secure_filename(new_name)
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
                # Ensure parent folders are restored
                def restore_parents(fid):
                    if fid is None:
                        return
                    pf = Folder.query.filter_by(id=fid).first()
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
                
                # Restore files in folder
                for file in File.query.filter_by(folder_id=folder.id, is_deleted=True).all():
                    file.restore_from_trash()
                
                # Recursively restore subfolders and their contents
                def restore_subfolders(parent_id):
                    subfolders = Folder.query.filter_by(parent_id=parent_id, is_deleted=True).all()
                    for subfolder in subfolders:
                        subfolder.restore_from_trash()
                        
                        # Restore files in subfolder
                        for file in File.query.filter_by(folder_id=subfolder.id, is_deleted=True).all():
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
        user.update_storage_used()
    
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
            arc = os.path.join(path_in_zip, f.original_filename)
            yield f.file_path, arc, f.size, f.file_type
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
    
    # Helper to check if folder_a is descendant of folder_b
    def is_descendant(folder_a_id, folder_b_id):
        current = Folder.query.filter_by(id=folder_b_id).first()
        while current and current.parent_id is not None:
            if current.parent_id == folder_a_id:
                return True
            current = Folder.query.filter_by(id=current.parent_id).first()
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
        user.update_storage_used()
    
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
    mime_type, _ = mimetypes.guess_type(file.file_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'

    return send_file(file.file_path, mimetype=mime_type, as_attachment=False, download_name=file.original_filename)


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
    from urllib.parse import urlparse, unquote

    user_id = session.get('user_id')
    file_url = request.form.get('file_url', '').strip()
    folder_id = request.form.get('folder_id', type=int)

    if not file_url or not (file_url.startswith('http://') or file_url.startswith('https://')):
        flash('Invalid URL', 'danger')
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
    filename = unquote(os.path.basename(parsed.path)) or ''

    # Get file type validation
    # We will validate after finalizing filename

    try:
        # Max upload size from settings (default 2TB)
        max_size_setting = SystemSetting.query.filter_by(key='max_upload_size').first()
        max_size = current_app.config.get('MAX_CONTENT_LENGTH', 2000 * 1024 * 1024 * 1024)
        if max_size_setting:
            try:
                max_size = int(max_size_setting.get_typed_value())
            except (TypeError, ValueError):
                pass

        with requests.get(file_url, stream=True, timeout=30) as r:
            r.raise_for_status()

            # Try to get filename from Content-Disposition header
            cd_header = r.headers.get('Content-Disposition')
            if cd_header:
                from werkzeug.http import parse_options_header
                _, params = parse_options_header(cd_header)
                fname = params.get('filename') or params.get('filename*')
                if fname:
                    filename = unquote(fname.split("''")[-1])  # handle RFC5987

            # If still no extension, try to derive from content-type
            if '.' not in filename and r.headers.get('Content-Type'):
                import mimetypes
                ext = mimetypes.guess_extension(r.headers['Content-Type'].split(';')[0].strip())
                if ext:
                    filename += ext

            if not filename:
                filename = 'downloaded_file'

            # Validate extension now
            if not allowed_file(filename):
                flash('File type not allowed', 'danger')
                return redirect(url_for('files.index'))

            # Try to get size
            file_size = int(r.headers.get('Content-Length', 0))
            if file_size and file_size > max_size:
                flash('File too large', 'danger')
                return redirect(url_for('files.index'))

            # Quota check
            user = User.query.get(user_id)
            if file_size and not user.has_space_for_file(file_size):
                flash('Not enough storage space', 'danger')
                return redirect(url_for('files.index'))

            # Check duplicate filename
            existing_file = File.query.filter_by(
                original_filename=filename,
                folder_id=current_folder.id,
                user_id=user_id,
                is_deleted=False
            ).first()
            if existing_file:
                name_prefix, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{name_prefix}_{timestamp}{ext}"

            # Prepare storage path
            storage_filename = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
            folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(current_folder.id))
            os.makedirs(folder_path, exist_ok=True)
            save_path = os.path.join(folder_path, storage_filename)

            # Write stream to file
            downloaded = 0
            with open(save_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > max_size:
                            raise ValueError('File too large')
                        f.write(chunk)

        # Final size if not known before
        if not file_size:
            file_size = os.path.getsize(save_path)
            # Re-check quota edge case
            user = User.query.get(user_id)
            if not user.has_space_for_file(file_size):
                os.remove(save_path)
                flash('Not enough storage space', 'danger')
                return redirect(url_for('files.index'))

        # Record file in DB
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
        user.storage_used += file_size

        # Activity log
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
        else:
            print(f"Remote download error: {e}")
            flash('Failed to download file', 'danger')
    except Exception as e:
        print(f"Remote download error: {e}")
        flash('Failed to download file', 'danger')
    return redirect(url_for('files.index', folder_id=current_folder.id)) 
