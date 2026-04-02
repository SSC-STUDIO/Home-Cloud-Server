"""
安全输入验证模块
修复中危漏洞：
1. 目录访问 - 路径验证不完整
2. 文件名验证 - 缺少魔术字节检查
3. 输入长度限制 - 未设置最大长度
4. 特殊字符过滤 - 过滤不完全
"""

import os
import re
import unicodedata
import struct
from pathlib import Path
from typing import Optional, Tuple, List, Set
from flask import current_app

# =============================================================================
# 漏洞修复1: 强化路径验证 - 防止目录遍历攻击
# =============================================================================

class PathValidator:
    """路径验证器 - 防止目录遍历和路径操纵攻击"""
    
    # 最大路径长度 (Windows: 260, Linux: 4096, 这里取保守值)
    MAX_PATH_LENGTH = 4096
    MAX_FILENAME_LENGTH = 255
    
    # 危险路径模式
    DANGEROUS_PATTERNS = [
        r'\.\./',           # ../
        r'\.\.\',          # ..\
        r'/\.\.',           # /..
        r'\\.\.',          # \..
        r'\.\.\.+',         # .... (多个点)
        r'%2e%2e',          # URL编码的..
        r'%252e%252e',      # 双重URL编码的..
        r'\.\.\%00',        # 空字节注入
        r'~',               # 用户目录扩展
        r'\$[A-Z]',         # 环境变量扩展
    ]
    
    # 保留文件名 (Windows)
    RESERVED_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    @classmethod
    def validate_path(cls, path: str, base_dir: Optional[str] = None) -> Optional[str]:
        """
        验证路径安全，返回规范化后的路径或None（如果不安全）
        
        Args:
            path: 要验证的路径
            base_dir: 基础目录，确保路径在此目录下
            
        Returns:
            规范化后的安全路径，如果不安全则返回None
        """
        if not path:
            return None
        
        # 检查路径长度
        if len(path) > cls.MAX_PATH_LENGTH:
            return None
        
        # 检查空字节
        if '\x00' in path:
            return None
        
        # 检查危险模式
        lower_path = path.lower()
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, lower_path):
                return None
        
        try:
            # 规范化路径
            normalized = os.path.normpath(path)
            
            # 确保不是绝对路径（除非提供了base_dir）
            if os.path.isabs(normalized) and base_dir is None:
                return None
            
            # 如果提供了基础目录，确保路径在基础目录下
            if base_dir:
                base_dir = os.path.abspath(os.path.realpath(base_dir))
                target_path = os.path.abspath(os.path.join(base_dir, normalized))
                target_path = os.path.realpath(target_path)
                
                # 使用commonpath检查路径是否在base_dir下
                try:
                    common = os.path.commonpath([base_dir, target_path])
                    if common != base_dir:
                        return None
                except ValueError:
                    return None
                
                return target_path
            
            return normalized
            
        except (ValueError, OSError):
            return None
    
    @classmethod
    def validate_filename(cls, filename: str) -> Optional[str]:
        """
        验证文件名安全
        
        Args:
            filename: 要验证的文件名
            
        Returns:
            安全的文件名，如果不安全则返回None
        """
        if not filename:
            return None
        
        # 检查长度
        if len(filename) > cls.MAX_FILENAME_LENGTH:
            return None
        
        # 检查空字节
        if '\x00' in filename:
            return None
        
        # 规范化Unicode
        try:
            filename = unicodedata.normalize('NFC', filename.strip())
        except (TypeError, ValueError):
            return None
        
        # 检查是否为.或..
        if filename in ('.', '..'):
            return None
        
        # 检查保留名
        base_name = filename.upper().split('.')[0]
        if base_name in cls.RESERVED_NAMES:
            return None
        
        # 检查危险字符
        dangerous_chars = '\x00-\x1f\x7f"<>|:*?'
        if any(c in filename for c in dangerous_chars):
            return None
        
        # 检查路径分隔符
        if '/' in filename or '\\' in filename:
            return None
        
        return filename
    
    @classmethod
    def sanitize_path_component(cls, component: str) -> Optional[str]:
        """清理路径组件"""
        if not component:
            return None
        
        # 移除危险字符
        sanitized = re.sub(r'[\x00-\x1f\x7f"<>|:*?]', '', component)
        sanitized = sanitized.strip('. ')
        
        # 检查是否为空或保留名
        if not sanitized or sanitized.upper() in cls.RESERVED_NAMES:
            return None
        
        if len(sanitized) > cls.MAX_FILENAME_LENGTH:
            sanitized = sanitized[:cls.MAX_FILENAME_LENGTH]
        
        return sanitized


# =============================================================================
# 漏洞修复2: 文件魔术字节检查 - 防止文件类型欺骗
# =============================================================================

class MagicBytesValidator:
    """魔术字节验证器 - 通过文件头验证真实文件类型"""
    
    # 已知文件类型的魔术字节
    MAGIC_BYTES = {
        # 图片格式
        'image/jpeg': [
            (b'\xff\xd8\xff', None),  # JPEG
        ],
        'image/png': [
            (b'\x89PNG\r\n\x1a\n', None),  # PNG
        ],
        'image/gif': [
            (b'GIF87a', None),  # GIF87a
            (b'GIF89a', None),  # GIF89a
        ],
        'image/bmp': [
            (b'BM', None),  # BMP
        ],
        'image/webp': [
            (b'RIFF', b'WEBP'),  # WEBP (RIFF....WEBP)
        ],
        'image/tiff': [
            (b'II\x2a\x00', None),  # TIFF little-endian
            (b'MM\x00\x2a', None),  # TIFF big-endian
        ],
        
        # 文档格式
        'application/pdf': [
            (b'%PDF', None),  # PDF
        ],
        'application/msword': [
            (b'\xd0\xcf\x11\xe0', None),  # DOC (OLE)
        ],
        'application/vnd.openxmlformats-officedocument': [
            (b'PK\x03\x04', None),  # Office Open XML (DOCX, XLSX, PPTX)
        ],
        
        # 压缩格式
        'application/zip': [
            (b'PK\x03\x04', None),  # ZIP
        ],
        'application/gzip': [
            (b'\x1f\x8b', None),  # GZIP
        ],
        'application/x-rar-compressed': [
            (b'Rar!', None),  # RAR
        ],
        'application/x-7z-compressed': [
            (b'7z\xbc\xaf\x27\x1c', None),  # 7Z
        ],
        
        # 可执行文件 (通常不允许上传)
        'application/x-executable': [
            (b'\x7fELF', None),  # ELF (Linux)
            (b'MZ', None),  # Windows executable
        ],
    }
    
    # 文件扩展名到MIME类型的映射
    EXTENSION_TO_MIME = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.webp': 'image/webp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.pdf': 'application/pdf',
        '.doc': 'application/msword',
        '.docx': 'application/vnd.openxmlformats-officedocument',
        '.xls': 'application/vnd.ms-excel',
        '.xlsx': 'application/vnd.openxmlformats-officedocument',
        '.ppt': 'application/vnd.ms-powerpoint',
        '.pptx': 'application/vnd.openxmlformats-officedocument',
        '.zip': 'application/zip',
        '.gz': 'application/gzip',
        '.rar': 'application/x-rar-compressed',
        '.7z': 'application/x-7z-compressed',
    }
    
    # 危险文件类型 (禁止上传)
    DANGEROUS_TYPES = {
        'application/x-executable',
        'application/x-dosexec',
        'application/x-msdos-program',
        'application/x-sh',
        'application/x-csh',
        'application/x-perl',
        'application/x-python-code',
        'text/x-python',
        'application/javascript',
        'text/html',
        'text/htm',
    }
    
    @classmethod
    def get_file_signature(cls, file_path: str, num_bytes: int = 8192) -> bytes:
        """读取文件的前N个字节"""
        try:
            with open(file_path, 'rb') as f:
                return f.read(num_bytes)
        except (IOError, OSError):
            return b''
    
    @classmethod
    def check_magic_bytes(cls, file_signature: bytes, mime_type: str) -> bool:
        """
        检查文件签名是否匹配指定的MIME类型
        
        Args:
            file_signature: 文件的前N个字节
            mime_type: 期望的MIME类型
            
        Returns:
            是否匹配
        """
        patterns = cls.MAGIC_BYTES.get(mime_type, [])
        
        for start_pattern, end_pattern in patterns:
            if start_pattern and not file_signature.startswith(start_pattern):
                continue
            if end_pattern and end_pattern not in file_signature:
                continue
            return True
        
        return False
    
    @classmethod
    def detect_mime_type(cls, file_signature: bytes) -> Optional[str]:
        """
        通过魔术字节检测文件的真实MIME类型
        
        Args:
            file_signature: 文件的前N个字节
            
        Returns:
            检测到的MIME类型，如果未知则返回None
        """
        for mime_type, patterns in cls.MAGIC_BYTES.items():
            for start_pattern, end_pattern in patterns:
                if start_pattern and not file_signature.startswith(start_pattern):
                    continue
                if end_pattern and end_pattern not in file_signature:
                    continue
                return mime_type
        return None
    
    @classmethod
    def validate_file_type(cls, file_path: str, expected_mime: Optional[str] = None,
                          allowed_types: Optional[Set[str]] = None) -> Tuple[bool, str]:
        """
        验证文件类型
        
        Args:
            file_path: 文件路径
            expected_mime: 期望的MIME类型
            allowed_types: 允许的文件类型集合
            
        Returns:
            (是否通过验证, 消息)
        """
        file_signature = cls.get_file_signature(file_path)
        
        if not file_signature:
            return False, "无法读取文件"
        
        # 检测真实文件类型
        detected_mime = cls.detect_mime_type(file_signature)
        
        # 检查是否为危险文件
        if detected_mime and detected_mime in cls.DANGEROUS_TYPES:
            return False, f"检测到危险文件类型: {detected_mime}"
        
        # 检查是否在允许列表中
        if allowed_types:
            # 检查扩展名
            ext = os.path.splitext(file_path)[1].lower()
            ext_mime = cls.EXTENSION_TO_MIME.get(ext)
            
            mime_allowed = (
                detected_mime in allowed_types or
                ext_mime in allowed_types
            )
            
            if not mime_allowed:
                return False, f"文件类型不在允许列表中"
        
        # 如果指定了期望类型，检查是否匹配
        if expected_mime and detected_mime:
            if detected_mime != expected_mime:
                return False, f"文件类型不匹配: 期望 {expected_mime}, 检测到 {detected_mime}"
        
        return True, "验证通过"
    
    @classmethod
    def get_extension_from_mime(cls, mime_type: str) -> Optional[str]:
        """从MIME类型获取文件扩展名"""
        for ext, mt in cls.EXTENSION_TO_MIME.items():
            if mt == mime_type:
                return ext
        return None


# =============================================================================
# 漏洞修复3: 输入长度限制
# =============================================================================

class InputLengthValidator:
    """输入长度验证器"""
    
    # 默认长度限制
    LIMITS = {
        'filename': 255,
        'folder_name': 255,
        'username': 32,
        'email': 254,
        'password': 128,
        'search_query': 200,
        'url': 2048,
        'file_path': 4096,
        'description': 10000,
        'text_field': 5000,
    }
    
    @classmethod
    def validate(cls, input_value: str, field_type: str, 
                 min_length: int = 1, custom_max: Optional[int] = None) -> Tuple[bool, str]:
        """
        验证输入长度
        
        Args:
            input_value: 输入值
            field_type: 字段类型 (filename, username等)
            min_length: 最小长度
            custom_max: 自定义最大长度
            
        Returns:
            (是否通过, 消息)
        """
        if input_value is None:
            return False, "输入不能为空"
        
        # 获取最大长度
        max_length = custom_max or cls.LIMITS.get(field_type, 255)
        
        # 检查长度
        input_len = len(input_value)
        
        if input_len < min_length:
            return False, f"输入太短 (最小 {min_length} 字符)"
        
        if input_len > max_length:
            return False, f"输入太长 (最大 {max_length} 字符)"
        
        return True, "长度验证通过"
    
    @classmethod
    def truncate(cls, input_value: str, field_type: str, 
                 custom_max: Optional[int] = None) -> str:
        """截断超长输入"""
        max_length = custom_max or cls.LIMITS.get(field_type, 255)
        if len(input_value) > max_length:
            return input_value[:max_length]
        return input_value


# =============================================================================
# 漏洞修复4: 完善特殊字符过滤
# =============================================================================

class SpecialCharFilter:
    """特殊字符过滤器"""
    
    # 控制字符 (0x00-0x1F 和 0x7F)
    CONTROL_CHARS = frozenset(chr(i) for i in range(0x20)) | {'\x7f'}
    
    # Unicode危险字符
    DANGEROUS_UNICODE = {
        '\u0000',  # 空字节
        '\ufeff',  # BOM
        '\u200b',  # 零宽空格
        '\u200c',  # 零宽非连接符
        '\u200d',  # 零宽连接符
        '\u2028',  # 行分隔符
        '\u2029',  # 段落分隔符
        '\u2060',  # 单词连接符
        '\uf8ff',  # Apple私有
    }
    
    # 脚本注入相关模式
    SCRIPT_PATTERNS = [
        r'<\s*script[^>]*>.*?<\s*/\s*script\s*>',  # <script>标签
        r'<\s*iframe[^>]*>.*?<\s*/\s*iframe\s*>',  # <iframe>标签
        r'javascript\s*:',  # javascript:协议
        r'data\s*:',  # data:协议
        r'vbscript\s*:',  # vbscript:协议
        r'on\w+\s*=',  # 事件处理器
        r'\.\./',  # 路径遍历
        r'\.\.\\',  # 路径遍历 (Windows)
        r'%00',  # 空字节编码
        r'\x00',  # 空字节
    ]
    
    # SQL注入相关模式 (基础检查)
    SQL_PATTERNS = [
        r'\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b',
        r'--.*$',
        r'/\*.*\*/',
        r';\s*$',
    ]
    
    # 命令注入相关模式
    COMMAND_PATTERNS = [
        r'[;&|`$]\s*\w+',
        r'\$\(',
        r'`[^`]*`',
    ]
    
    @classmethod
    def sanitize_control_chars(cls, text: str) -> str:
        """移除控制字符"""
        return ''.join(c for c in text if c not in cls.CONTROL_CHARS)
    
    @classmethod
    def sanitize_unicode(cls, text: str) -> str:
        """清理Unicode危险字符"""
        for char in cls.DANGEROUS_UNICODE:
            text = text.replace(char, '')
        return text
    
    @classmethod
    def has_script_content(cls, text: str) -> bool:
        """检查是否包含脚本注入内容"""
        lower_text = text.lower()
        for pattern in cls.SCRIPT_PATTERNS:
            if re.search(pattern, lower_text, re.IGNORECASE | re.DOTALL):
                return True
        return False
    
    @classmethod
    def has_sql_injection(cls, text: str) -> bool:
        """检查是否包含SQL注入特征"""
        upper_text = text.upper()
        for pattern in cls.SQL_PATTERNS:
            if re.search(pattern, upper_text):
                return True
        return False
    
    @classmethod
    def has_command_injection(cls, text: str) -> bool:
        """检查是否包含命令注入特征"""
        for pattern in cls.COMMAND_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    @classmethod
    def sanitize_for_filename(cls, text: str) -> str:
        """清理用于文件名的文本"""
        # 移除控制字符
        text = cls.sanitize_control_chars(text)
        
        # 移除路径分隔符
        text = text.replace('/', '').replace('\\', '')
        
        # 移除其他危险字符
        dangerous = '<>:"|?*\x00-\x1f\x7f'
        for char in dangerous:
            text = text.replace(char, '')
        
        # 清理Unicode
        text = cls.sanitize_unicode(text)
        
        return text.strip()
    
    @classmethod
    def sanitize_for_display(cls, text: str) -> str:
        """清理用于显示输出的文本 (XSS防护)"""
        # 转义HTML特殊字符
        html_escapes = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '/': '&#x2F;',
        }
        
        # 先移除控制字符
        text = cls.sanitize_control_chars(text)
        
        # 转义HTML
        for char, escape in html_escapes.items():
            text = text.replace(char, escape)
        
        return text


# =============================================================================
# 统一验证接口
# =============================================================================

class SecurityValidator:
    """统一安全验证接口"""
    
    @staticmethod
    def validate_filename(filename: str, check_length: bool = True,
                         check_chars: bool = True) -> Tuple[bool, str]:
        """验证文件名"""
        if not filename:
            return False, "文件名为空"
        
        # 长度检查
        if check_length:
            valid, msg = InputLengthValidator.validate(filename, 'filename')
            if not valid:
                return False, msg
        
        # 路径验证
        safe_name = PathValidator.validate_filename(filename)
        if not safe_name:
            return False, "文件名包含非法字符或模式"
        
        # 特殊字符检查
        if check_chars:
            if SpecialCharFilter.has_script_content(filename):
                return False, "文件名包含脚本内容"
        
        return True, safe_name
    
    @staticmethod
    def validate_filepath(filepath: str, base_dir: Optional[str] = None) -> Tuple[bool, str]:
        """验证文件路径"""
        if not filepath:
            return False, "路径为空"
        
        # 长度检查
        valid, msg = InputLengthValidator.validate(filepath, 'file_path')
        if not valid:
            return False, msg
        
        # 路径安全检查
        safe_path = PathValidator.validate_path(filepath, base_dir)
        if not safe_path:
            return False, "路径包含非法内容或试图遍历目录"
        
        return True, safe_path
    
    @staticmethod
    def validate_file_content(file_path: str, expected_mime: Optional[str] = None,
                              allowed_types: Optional[Set[str]] = None) -> Tuple[bool, str]:
        """验证文件内容"""
        if not os.path.exists(file_path):
            return False, "文件不存在"
        
        # 魔术字节检查
        valid, msg = MagicBytesValidator.validate_file_type(file_path, expected_mime, allowed_types)
        if not valid:
            return False, msg
        
        return True, "文件验证通过"
    
    @staticmethod
    def sanitize_text_input(text: str, max_length: int = 5000) -> Tuple[bool, str]:
        """清理文本输入"""
        if text is None:
            return True, ""
        
        # 长度检查
        if len(text) > max_length:
            text = text[:max_length]
        
        # 移除控制字符
        text = SpecialCharFilter.sanitize_control_chars(text)
        
        # 清理Unicode
        text = SpecialCharFilter.sanitize_unicode(text)
        
        return True, text
