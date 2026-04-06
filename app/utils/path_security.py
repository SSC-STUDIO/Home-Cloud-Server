"""
路径安全工具模块 - 防止路径遍历攻击

提供安全的文件路径操作函数，确保所有文件操作都在允许的目录范围内。
"""

import os
import re
from typing import Optional, Tuple
from werkzeug.utils import secure_filename


class PathSecurityError(Exception):
    """路径安全错误"""
    pass


def is_safe_path(base_path: str, target_path: str) -> bool:
    """
    验证目标路径是否在基础路径范围内（防止路径遍历）
    
    Args:
        base_path: 允许的基础目录路径
        target_path: 要验证的目标路径
        
    Returns:
        bool: 如果目标路径在基础路径范围内且安全则返回 True
    """
    try:
        # 获取绝对路径
        real_base = os.path.realpath(os.path.abspath(base_path))
        real_target = os.path.realpath(os.path.abspath(target_path))
        
        # 确保基础路径存在
        if not os.path.exists(real_base):
            return False
            
        # 使用 commonpath 验证路径关系
        try:
            common = os.path.commonpath([real_base, real_target])
        except ValueError:
            # 不同驱动器（Windows）
            return False
            
        # 目标路径必须在基础路径下
        return common == real_base or real_target.startswith(real_base + os.sep)
    except (OSError, ValueError):
        return False


def normalize_and_validate_path(base_path: str, *path_components: str) -> Optional[str]:
    """
    安全地拼接路径并验证结果是否在允许范围内
    
    Args:
        base_path: 基础目录路径
        *path_components: 路径组件
        
    Returns:
        str: 安全的目标路径，如果不安全则返回 None
    """
    try:
        # 先规范化基础路径
        real_base = os.path.realpath(os.path.abspath(base_path))
        
        # 拼接路径
        target = os.path.join(real_base, *path_components)
        real_target = os.path.realpath(target)
        
        # 验证路径安全
        if not is_safe_path(real_base, real_target):
            return None
            
        return real_target
    except (OSError, ValueError):
        return None


def validate_filename(filename: str) -> Optional[str]:
    """
    验证并清理文件名，防止路径遍历攻击
    
    Args:
        filename: 原始文件名
        
    Returns:
        str: 安全的文件名，如果不安全则返回 None
    """
    if not filename:
        return None
        
    # 检查 null 字节
    if '\x00' in filename:
        return None
        
    # 使用 werkzeug 的 secure_filename
    safe_name = secure_filename(filename)
    if not safe_name or safe_name in ('.', '..'):
        return None
        
    # 检查路径遍历模式
    dangerous_patterns = [
        '../', '..\\', '/..', '\\..',
        '..%2f', '..%2F', '%2e%2e', '%252e%252e',
        '....', '.....', '.../', '...\\'
    ]
    
    lower_name = safe_name.lower()
    for pattern in dangerous_patterns:
        if pattern in lower_name:
            return None
            
    # 拒绝绝对路径
    if safe_name.startswith('/') or safe_name.startswith('\\'):
        return None
        
    # 拒绝 Windows 驱动器路径
    if re.match(r'^[a-zA-Z]:', safe_name):
        return None
        
    return safe_name


def validate_folder_name(folder_name: str) -> Optional[str]:
    """
    验证文件夹名称，防止路径遍历攻击
    
    Args:
        folder_name: 原始文件夹名
        
    Returns:
        str: 安全的文件夹名，如果不安全则返回 None
    """
    if not folder_name:
        return None
        
    # 使用文件名验证逻辑（文件夹名不能包含扩展名相关的问题）
    return validate_filename(folder_name)


def safe_join(base_path: str, *paths: str) -> Optional[str]:
    """
    安全地拼接路径，自动验证结果
    
    Args:
        base_path: 基础目录
        *paths: 路径组件
        
    Returns:
        str: 安全的完整路径，如果不安全则返回 None
    """
    return normalize_and_validate_path(base_path, *paths)


def safe_read_file(base_path: str, relative_path: str, mode: str = 'rb') -> Optional[bytes]:
    """
    安全地读取文件
    
    Args:
        base_path: 允许的基础目录
        relative_path: 相对路径
        mode: 文件打开模式
        
    Returns:
        bytes: 文件内容，如果路径不安全则返回 None
    """
    safe_path = normalize_and_validate_path(base_path, relative_path)
    if not safe_path or not os.path.isfile(safe_path):
        return None
        
    try:
        with open(safe_path, mode) as f:
            return f.read()
    except (OSError, IOError):
        return None


def safe_write_file(base_path: str, relative_path: str, content: bytes, mode: str = 'wb') -> bool:
    """
    安全地写入文件
    
    Args:
        base_path: 允许的基础目录
        relative_path: 相对路径
        content: 文件内容
        mode: 文件打开模式
        
    Returns:
        bool: 是否写入成功
    """
    safe_path = normalize_and_validate_path(base_path, relative_path)
    if not safe_path:
        return False
        
    # 确保目录存在
    dir_path = os.path.dirname(safe_path)
    if not os.path.exists(dir_path):
        try:
            os.makedirs(dir_path, exist_ok=True)
        except OSError:
            return False
            
    try:
        with open(safe_path, mode) as f:
            f.write(content)
        return True
    except (OSError, IOError):
        return False


def safe_delete_file(base_path: str, relative_path: str) -> bool:
    """
    安全地删除文件
    
    Args:
        base_path: 允许的基础目录
        relative_path: 相对路径
        
    Returns:
        bool: 是否删除成功
    """
    safe_path = normalize_and_validate_path(base_path, relative_path)
    if not safe_path or not os.path.isfile(safe_path):
        return False
        
    try:
        os.remove(safe_path)
        return True
    except (OSError, IOError):
        return False


def safe_list_directory(base_path: str, relative_path: str = '') -> Optional[Tuple[list, list]]:
    """
    安全地列出目录内容
    
    Args:
        base_path: 允许的基础目录
        relative_path: 相对路径
        
    Returns:
        tuple: (文件列表, 目录列表)，如果路径不安全则返回 None
    """
    safe_path = normalize_and_validate_path(base_path, relative_path) if relative_path else os.path.realpath(base_path)
    if not safe_path or not os.path.isdir(safe_path):
        return None
        
    try:
        files = []
        dirs = []
        for item in os.listdir(safe_path):
            item_path = os.path.join(safe_path, item)
            if os.path.isfile(item_path):
                files.append(item)
            elif os.path.isdir(item_path):
                dirs.append(item)
        return files, dirs
    except OSError:
        return None


def get_safe_file_path(base_path: str, *path_components: str, must_exist: bool = False) -> Optional[str]:
    """
    获取安全的文件路径
    
    Args:
        base_path: 基础目录
        *path_components: 路径组件
        must_exist: 是否要求文件必须存在
        
    Returns:
        str: 安全的文件路径，如果不安全则返回 None
    """
    safe_path = normalize_and_validate_path(base_path, *path_components)
    if not safe_path:
        return None
        
    if must_exist and not os.path.exists(safe_path):
        return None
        
    return safe_path


def validate_path_traversal(path: str) -> bool:
    """
    检查路径是否包含路径遍历攻击特征
    
    Args:
        path: 要检查的路径
        
    Returns:
        bool: 如果路径安全返回 True，否则返回 False
    """
    if not path:
        return False
        
    # 检查 null 字节
    if '\x00' in path:
        return False
        
    # 检查路径遍历模式
    dangerous_patterns = [
        '../', '..\\', '/..', '\\..',
        '..%2f', '..%2F', '%2e%2e', '%252e%252e',
        '..%252f', '..%252F', '%252e%252e%252f',
        '....//', '....\\\\',
        '.%00.', '%00'
    ]
    
    lower_path = path.lower()
    for pattern in dangerous_patterns:
        if pattern in lower_path:
            return False
            
    # 规范化路径后再次检查
    try:
        normalized = os.path.normpath(path)
        if '..' in normalized.split(os.sep):
            # 检查是否在开头或是独立的部分
            parts = normalized.split(os.sep)
            for i, part in enumerate(parts):
                if part == '..' and i == 0:
                    return False
    except (ValueError, OSError):
        return False
        
    return True
