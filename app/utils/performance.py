"""
性能优化扩展模块
包含缓存、数据库优化和性能监控
"""

from flask_caching import Cache
from flask import Flask, request, g
import time
import functools
import logging

# 配置缓存
cache = Cache()

def init_cache(app: Flask):
    """初始化缓存系统"""
    cache_config = {
        'CACHE_TYPE': app.config.get('CACHE_TYPE', 'simple'),
        'CACHE_DEFAULT_TIMEOUT': app.config.get('CACHE_DEFAULT_TIMEOUT', 300),
        'CACHE_KEY_PREFIX': 'home_cloud_',
    }
    
    # Redis 配置
    if cache_config['CACHE_TYPE'] == 'redis':
        cache_config.update({
            'CACHE_REDIS_URL': app.config.get('CACHE_REDIS_URL', 'redis://localhost:6379/0'),
            'CACHE_REDIS_DB': app.config.get('CACHE_REDIS_DB', 0),
        })
    
    app.config.from_mapping(cache_config)
    cache.init_app(app)


def cached_user_storage(user_id: int, timeout: int = 60):
    """缓存用户存储使用量的装饰器"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            cache_key = f'user_storage:{user_id}'
            result = cache.get(cache_key)
            if result is not None:
                return result
            result = f(*args, **kwargs)
            cache.set(cache_key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


def invalidate_user_storage(user_id: int):
    """使用户存储缓存失效"""
    cache.delete(f'user_storage:{user_id}')


def cached_query(cache_key: str, timeout: int = 300):
    """通用查询缓存装饰器"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            key = cache_key
            if callable(cache_key):
                key = cache_key(*args, **kwargs)
            result = cache.get(key)
            if result is not None:
                return result
            result = f(*args, **kwargs)
            cache.set(key, result, timeout=timeout)
            return result
        return wrapper
    return decorator


class PerformanceMonitor:
    """性能监控中间件"""
    
    def __init__(self, app: Flask = None):
        self.logger = logging.getLogger('performance')
        if app:
            self.init_app(app)
    
    def init_app(self, app: Flask):
        """初始化性能监控"""
        
        @app.before_request
        def before_request():
            g.start_time = time.time()
            g.db_query_count = 0
            g.db_query_time = 0
        
        @app.after_request
        def after_request(response):
            if hasattr(g, 'start_time'):
                elapsed = time.time() - g.start_time
                
                # 记录慢请求
                if elapsed > 1.0:  # 超过1秒的请求
                    self.logger.warning(
                        f'Slow request: {request.method} {request.path} '
                        f'took {elapsed:.2f}s'
                    )
                
                # 添加到响应头（仅在调试模式）
                if app.debug:
                    response.headers['X-Request-Time'] = f'{elapsed:.3f}s'
                    if hasattr(g, 'db_query_count'):
                        response.headers['X-DB-Queries'] = str(g.db_query_count)
            
            return response


def timed_cache(timeout: int = 300, key_prefix: str = None):
    """带执行时间统计的缓存装饰器"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_prefix:
                cache_key = f"{key_prefix}:{f.__name__}:{str(args)}:{str(kwargs)}"
            else:
                cache_key = f"{f.__name__}:{str(args)}:{str(kwargs)}"
            
            # 尝试从缓存获取
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # 执行函数并计时
            start = time.time()
            result = f(*args, **kwargs)
            elapsed = time.time() - start
            
            # 如果执行时间超过阈值，记录日志
            if elapsed > 0.5:
                logging.getLogger('performance').warning(
                    f'Slow function: {f.__name__} took {elapsed:.2f}s'
                )
            
            # 缓存结果
            cache.set(cache_key, result, timeout=timeout)
            return result
        return wrapper
    return decorator
