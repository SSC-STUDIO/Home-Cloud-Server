from __future__ import annotations

import os
import hashlib
import mimetypes
import shutil
import zipfile
import io
from flask import send_file, Response   
from werkzeug.utils import secure_filename
import uuid

# 导入安全验证模块
from app.utils.security_validation import (
    PathValidator, MagicBytesValidator, 
    InputLengthValidator, SecurityValidator
)


def get_file_hash(file_path: str) -> str:
    """
    Calculate MD5 hash of a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: MD5 hash of the file
    """
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def get_mime_type(file_path: str) -> str:
    """
    Get MIME type of a file
    
    Args:
        file_path: Path to the file
        
    Returns:
        str: MIME type of the file
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or 'application/octet-stream'

def create_unique_filename(original_filename: str) -> str:
    """
    Create a unique filename to avoid conflicts
    修复: 添加文件名验证和魔术字节检查准备
    
    Args:
        original_filename: Original filename
        
    Returns:
        str: Unique filename
    """
    # 安全验证 - 修复漏洞1,3,4
    valid, result = SecurityValidator.validate_filename(original_filename)
    if not valid:
        # 如果验证失败，使用安全文件名
        filename = "file"
    else:
        filename = secure_filename(result)
    
    if not filename:
        filename = "file"
    
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    
    # 检查最终长度
    if len(unique_filename) > 300:
        unique_filename = unique_filename[:300]
    
    return unique_filename

def get_file_size(file_path: str) -> int:
    """
    Get file size in bytes
    
    Args:
        file_path: Path to the file
        
    Returns:
        int: File size in bytes
    """
    return os.path.getsize(file_path)

def create_zip_archive(file_paths: list[str], zip_name: str = 'archive.zip') -> io.BytesIO:
    """
    Create a zip archive from multiple files
    
    Args:
        file_paths: List of file paths to include in the archive
        zip_name: Name of the zip file
        
    Returns:
        BytesIO: In-memory zip file
    """
    memory_file = io.BytesIO()
    
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                # Add file to zip with just the filename, not the full path
                zf.write(file_path, os.path.basename(file_path))
    
    memory_file.seek(0)
    return memory_file

def send_files_as_zip(file_paths: list[str], zip_name: str = 'archive.zip') -> Response:
    """
    Send multiple files as a zip archive
    
    Args:
        file_paths: List of file paths to include in the archive
        zip_name: Name of the zip file
        
    Returns:
        Response: Flask response with the zip file
    """
    memory_file = create_zip_archive(file_paths, zip_name)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=zip_name
    )

def delete_file_safely(file_path: str) -> bool:
    """
    Safely delete a file, handling errors
    
    Args:
        file_path: Path to the file to delete
        
    Returns:
        bool: True if file was deleted successfully, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except Exception as e:
        print(f"Error deleting file {file_path}: {e}")
    return False

def delete_folder_safely(folder_path: str) -> bool:
    """
    Safely delete a folder and its contents, handling errors
    
    Args:
        folder_path: Path to the folder to delete
        
    Returns:
        bool: True if folder was deleted successfully, False otherwise
    """
    try:
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            return True
    except Exception as e:
        print(f"Error deleting folder {folder_path}: {e}")
    return False 


def validate_file_path(file_path: str, base_dir: str) -> bool:
    """
    验证文件路径安全 - 修复目录遍历漏洞
    
    Args:
        file_path: 文件路径
        base_dir: 基础目录
        
    Returns:
        bool: 是否安全
    """
    valid, _ = SecurityValidator.validate_filepath(file_path, base_dir)
    return valid


def validate_file_type(file_path: str, allowed_types: set = None) -> bool:
    """
    验证文件类型 - 修复魔术字节检查漏洞
    
    Args:
        file_path: 文件路径
        allowed_types: 允许的MIME类型集合
        
    Returns:
        bool: 是否安全
    """
    valid, _ = SecurityValidator.validate_file_content(file_path, allowed_types=allowed_types)
    return valid


def sanitize_filename(filename: str) -> str:
    """
    清理文件名 - 修复特殊字符过滤漏洞
    
    Args:
        filename: 原始文件名
        
    Returns:
        str: 安全的文件名
    """
    valid, result = SecurityValidator.validate_filename(filename)
    if valid:
        return result
    return "file"
