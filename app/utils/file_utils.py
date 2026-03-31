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

def get_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """
    Calculate hash of a file using secure algorithm
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm ('sha256' or 'md5' for legacy compatibility)
        
    Returns:
        str: Hash of the file
        
    Note: MD5 is deprecated for security use. Use SHA-256 for new code.
    """
    if algorithm.lower() == 'md5':
        # SECURITY WARNING: MD5 is cryptographically broken and should not be used
        # for security purposes. Kept for legacy compatibility only.
        hasher = hashlib.md5()
    else:
        hasher = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

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
    
    Args:
        original_filename: Original filename
        
    Returns:
        str: Unique filename
    """
    filename = secure_filename(original_filename)
    if not filename:
        filename = "file"
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
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
