"""
敏感信息脱敏工具模块
用于安全地记录日志，防止敏感信息泄露
"""

import re
import json
from typing import Any, Dict, List, Union


class SensitiveDataMasker:
    """敏感数据脱敏器"""
    
    # 敏感字段名模式（不区分大小写）
    SENSITIVE_FIELDS = [
        'password', 'passwd', 'pwd', 'secret', 'token', 'access_token',
        'refresh_token', 'api_key', 'apikey', 'api_secret', 'apisecret',
        'auth_token', 'authtoken', 'jwt', 'bearer', 'credential',
        'private_key', 'privatekey', 'secret_key', 'secretkey',
        'session', 'session_id', 'sessionid', 'csrf_token', 'csrftoken',
        'reset_token', 'resettoken', 'verification_code', 'verificationcode',
        'otp', '2fa_code', '2facode', 'pin', 'cvv', 'ssn'
    ]
    
    # 需要脱敏的值模式
    SENSITIVE_PATTERNS = [
        # JWT Token: eyJ...xxxxx
        (r'eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*', '[JWT_TOKEN]'),
        # Bearer Token: Bearer xxxxx
        (r'Bearer\s+[A-Za-z0-9_\-\.]+', 'Bearer [MASKED]'),
        # Basic Auth: Basic xxxxx
        (r'Basic\s+[A-Za-z0-9=]+', 'Basic [MASKED]'),
        # API Key patterns
        (r'[a-zA-Z0-9_-]{32,}', '[API_KEY]'),
        # Session ID patterns
        (r'[a-f0-9]{32,64}', '[SESSION_ID]'),
    ]
    
    MASK = '[MASKED]'
    PARTIAL_MASK = '***'
    
    @classmethod
    def mask_string(cls, text: str) -> str:
        """对字符串进行脱敏处理"""
        if not text or not isinstance(text, str):
            return text
        
        result = text
        
        # 应用敏感值模式
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        
        return result
    
    @classmethod
    def mask_dict(cls, data: Dict[str, Any], depth: int = 0, max_depth: int = 5) -> Dict[str, Any]:
        """
        对字典进行脱敏处理
        
        Args:
            data: 要脱敏的字典
            depth: 当前深度（递归使用）
            max_depth: 最大递归深度
        """
        if depth > max_depth:
            return {'[DEPTH_EXCEEDED]': True}
        
        if not isinstance(data, dict):
            return data
        
        result = {}
        for key, value in data.items():
            # 检查键名是否为敏感字段
            key_lower = key.lower()
            is_sensitive_key = any(
                sensitive in key_lower 
                for sensitive in cls.SENSITIVE_FIELDS
            )
            
            if is_sensitive_key:
                # 敏感字段的值直接脱敏
                if isinstance(value, str):
                    if len(value) <= 8:
                        result[key] = cls.MASK
                    else:
                        # 保留前2位和后2位，中间脱敏
                        result[key] = value[:2] + cls.PARTIAL_MASK + value[-2:]
                else:
                    result[key] = cls.MASK
            elif isinstance(value, dict):
                result[key] = cls.mask_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = cls.mask_list(value, depth + 1, max_depth)
            elif isinstance(value, str):
                result[key] = cls.mask_string(value)
            else:
                result[key] = value
        
        return result
    
    @classmethod
    def mask_list(cls, data: List[Any], depth: int = 0, max_depth: int = 5) -> List[Any]:
        """对列表进行脱敏处理"""
        if depth > max_depth:
            return ['[DEPTH_EXCEEDED]']
        
        if not isinstance(data, list):
            return data
        
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(cls.mask_dict(item, depth + 1, max_depth))
            elif isinstance(item, list):
                result.append(cls.mask_list(item, depth + 1, max_depth))
            elif isinstance(item, str):
                result.append(cls.mask_string(item))
            else:
                result.append(item)
        
        return result
    
    @classmethod
    def mask_json(cls, json_str: str) -> str:
        """对JSON字符串进行脱敏"""
        try:
            data = json.loads(json_str)
            masked_data = cls.mask_dict(data)
            return json.dumps(masked_data)
        except json.JSONDecodeError:
            return cls.mask_string(json_str)
    
    @classmethod
    def safe_log_message(cls, message: str, *args, **kwargs) -> str:
        """
        创建安全的日志消息
        
        用法:
            logger.info(SensitiveDataMasker.safe_log_message(
                "User %s logged in with token %s", username, token
            ))
        """
        # 格式化消息
        try:
            formatted = message % args
        except (TypeError, ValueError):
            formatted = message
        
        # 对kwargs进行处理
        for key, value in kwargs.items():
            if isinstance(value, str):
                kwargs[key] = cls.mask_string(value)
        
        # 脱敏处理
        return cls.mask_string(formatted)
    
    @classmethod
    def mask_headers(cls, headers: Dict[str, str]) -> Dict[str, str]:
        """
        对HTTP头进行脱敏
        """
        sensitive_headers = [
            'authorization', 'cookie', 'x-csrf-token', 'x-xsrf-token',
            'x-api-key', 'x-auth-token', 'proxy-authorization'
        ]
        
        result = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if any(sh in key_lower for sh in sensitive_headers):
                if isinstance(value, str) and len(value) > 10:
                    result[key] = value[:5] + cls.PARTIAL_MASK + value[-5:]
                else:
                    result[key] = cls.MASK
            else:
                result[key] = cls.mask_string(value) if isinstance(value, str) else value
        
        return result
    
    @classmethod
    def mask_query_string(cls, query_string: str) -> str:
        """对查询字符串进行脱敏"""
        if not query_string:
            return query_string
        
        try:
            from urllib.parse import parse_qs, urlencode
            params = parse_qs(query_string)
            masked_params = {}
            
            for key, values in params.items():
                key_lower = key.lower()
                is_sensitive = any(
                    sensitive in key_lower 
                    for sensitive in cls.SENSITIVE_FIELDS
                )
                
                if is_sensitive:
                    masked_params[key] = [cls.MASK]
                else:
                    masked_params[key] = [cls.mask_string(v) for v in values]
            
            return urlencode(masked_params, doseq=True)
        except Exception:
            return cls.mask_string(query_string)


# 便捷函数
def mask_sensitive_data(data: Any) -> Any:
    """对任意类型的数据进行脱敏"""
    if isinstance(data, dict):
        return SensitiveDataMasker.mask_dict(data)
    elif isinstance(data, list):
        return SensitiveDataMasker.mask_list(data)
    elif isinstance(data, str):
        return SensitiveDataMasker.mask_string(data)
    return data


def safe_log(logger, level: str, message: str, *args, **kwargs):
    """安全地记录日志"""
    safe_message = SensitiveDataMasker.safe_log_message(message, *args)
    
    # 处理extra参数
    if 'extra' in kwargs:
        kwargs['extra'] = mask_sensitive_data(kwargs['extra'])
    
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(safe_message, **kwargs)
