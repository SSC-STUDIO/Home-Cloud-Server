"""
安全中间件 - 输入验证与路径安全
"""

from flask import request, abort, current_app
from functools import wraps
import re
from app.utils.security_validation import InputLengthValidator, SpecialCharFilter

class InputValidationMiddleware:
    """输入验证中间件"""
    
    # 需要验证的端点和字段
    VALIDATION_RULES = {
        '/files/upload': {
            'POST': {
                'folder_id': {'type': 'int', 'max_length': 20},
            }
        },
        '/files/search': {
            'GET': {
                'query': {'type': 'string', 'max_length': 200},
            }
        },
        '/folders/create': {
            'POST': {
                'folder_name': {'type': 'string', 'max_length': 255},
                'parent_id': {'type': 'int', 'max_length': 20},
            }
        },
    }
    
    @classmethod
    def validate_request(cls):
        """验证当前请求"""
        path = request.path
        method = request.method
        
        # 检查路径规则
        for pattern, methods in cls.VALIDATION_RULES.items():
            if path.startswith(pattern) and method in methods:
                rules = methods[method]
                
                # 获取请求数据
                if method == 'GET':
                    data = request.args
                else:
                    data = request.form
                
                # 验证每个字段
                for field, rule in rules.items():
                    value = data.get(field, '')
                    
                    if not value:
                        continue
                    
                    # 长度验证
                    if len(str(value)) > rule.get('max_length', 255):
                        abort(400, description=f"字段 {field} 超出长度限制")
                    
                    # 危险内容检查
                    if rule.get('type') == 'string' and SpecialCharFilter.has_script_content(str(value)):
                        abort(400, description=f"字段 {field} 包含非法内容")


def register_security_middleware(app):
    """注册安全中间件"""
    
    @app.before_request
    def validate_input():
        """在每个请求前验证输入"""
        try:
            InputValidationMiddleware.validate_request()
        except Exception as e:
            current_app.logger.warning(f"输入验证失败: {e}")
            abort(400, description="输入验证失败")
    
    @app.after_request
    def add_security_headers(response):
        """添加安全响应头"""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
