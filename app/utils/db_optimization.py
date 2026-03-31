"""
数据库优化配置和工具
"""

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import joinedload, selectinload
from flask import g
import time
import logging

logger = logging.getLogger('db_performance')


def configure_db_engine(app, db):
    """配置数据库引擎优化参数"""
    
    # 获取引擎
    engine = db.engine
    
    # 配置连接池参数
    engine.pool.size = app.config.get('DB_POOL_SIZE', 10)
    engine.pool.max_overflow = app.config.get('DB_MAX_OVERFLOW', 20)
    engine.pool.timeout = app.config.get('DB_POOL_TIMEOUT', 30)
    engine.pool.recycle = app.config.get('DB_POOL_RECYCLE', 1800)  # 30分钟回收连接
    
    # SQLite 优化
    if 'sqlite' in str(engine.url):
        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            """设置 SQLite 优化参数"""
            cursor = dbapi_conn.cursor()
            # 启用 WAL 模式，提高并发性能
            cursor.execute("PRAGMA journal_mode=WAL")
            # 同步模式设为 NORMAL，平衡性能和安全性
            cursor.execute("PRAGMA synchronous=NORMAL")
            # 增加缓存大小
            cursor.execute("PRAGMA cache_size=-64000")  # 64MB
            # 临时表使用内存
            cursor.execute("PRAGMA temp_store=MEMORY")
            # 内存映射 I/O
            cursor.execute("PRAGMA mmap_size=30000000000")  # 30GB
            cursor.close()
    
    # 查询性能监控
    @event.listens_for(Engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """记录查询开始时间"""
        context._query_start_time = time.time()
        
        # 增加查询计数
        if hasattr(g, 'db_query_count'):
            g.db_query_count += 1
    
    @event.listens_for(Engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """记录查询执行时间"""
        elapsed = time.time() - context._query_start_time
        
        # 记录慢查询
        if elapsed > 0.5:  # 超过500ms的查询
            logger.warning(f'Slow query ({elapsed:.2f}s): {statement[:200]}')
        
        # 累加查询时间
        if hasattr(g, 'db_query_time'):
            g.db_query_time += elapsed


class QueryOptimizer:
    """查询优化工具类"""
    
    @staticmethod
    def optimize_file_list_query(query, include_folder=True):
        """优化文件列表查询，使用 joinedload 避免 N+1 查询"""
        from app.models.file import File, Folder
        from app.models.user import User
        
        if include_folder:
            query = query.options(
                joinedload(File.folder),
                joinedload(File.user)
            )
        return query
    
    @staticmethod
    def optimize_folder_tree_query(user_id):
        """优化文件夹树查询，使用批量加载"""
        from app.models.file import Folder
        
        return Folder.query.filter_by(
            user_id=user_id, 
            is_deleted=False
        ).options(
            selectinload(Folder.children)
        )
    
    @staticmethod
    def batch_update_storage_usage(user_ids):
        """批量更新用户存储使用量"""
        from app.models.file import File
        from app.models.user import User
        from app.extensions import db
        from sqlalchemy import func
        
        # 使用单个查询计算所有用户的存储使用量
        results = db.session.query(
            File.user_id,
            func.sum(File.size).label('total_size')
        ).filter(
            File.user_id.in_(user_ids),
            File.is_deleted == False
        ).group_by(File.user_id).all()
        
        # 批量更新
        for user_id, total_size in results:
            user = User.query.get(user_id)
            if user:
                user.storage_used = total_size or 0
        
        db.session.commit()


def create_database_indexes(db):
    """创建数据库索引以提高查询性能"""
    from sqlalchemy import Index
    from app.models.file import File, Folder
    from app.models.user import User
    from app.models.activity import Activity
    
    # File 表索引
    indexes = [
        # 用户文件查询索引
        Index('idx_file_user_deleted', 'files', 'user_id', 'is_deleted'),
        Index('idx_file_user_folder', 'files', 'user_id', 'folder_id', 'is_deleted'),
        Index('idx_file_folder', 'files', 'folder_id', 'is_deleted'),
        
        # 文件名搜索索引
        Index('idx_file_name', 'files', 'original_filename'),
        
        # 时间戳索引（用于排序）
        Index('idx_file_created', 'files', 'created_at'),
        Index('idx_file_updated', 'files', 'updated_at'),
        
        # 回收站过期索引
        Index('idx_file_expiry', 'files', 'expiry_date'),
        
        # Folder 表索引
        Index('idx_folder_user_parent', 'folders', 'user_id', 'parent_id', 'is_deleted'),
        Index('idx_folder_parent', 'folders', 'parent_id', 'is_deleted'),
        
        # Activity 表索引
        Index('idx_activity_user_time', 'activities', 'user_id', 'timestamp'),
        Index('idx_activity_user_action', 'activities', 'user_id', 'action'),
    ]
    
    # 创建索引（如果不存在）
    for index in indexes:
        try:
            index.create(db.engine)
        except Exception as e:
            logger.warning(f'Index creation skipped: {e}')


class BulkOperations:
    """批量操作工具类，提高大量数据处理性能"""
    
    BATCH_SIZE = 1000
    
    @staticmethod
    def bulk_delete_files(file_ids, user_id):
        """批量删除文件（使用 SQL 批量操作而非 ORM）"""
        from app.models.file import File
        from app.extensions import db
        
        # 分批处理
        for i in range(0, len(file_ids), BulkOperations.BATCH_SIZE):
            batch = file_ids[i:i + BulkOperations.BATCH_SIZE]
            
            # 使用 SQL 批量更新
            db.session.query(File).filter(
                File.id.in_(batch),
                File.user_id == user_id
            ).update({'is_deleted': True}, synchronize_session=False)
            
            db.session.commit()
    
    @staticmethod
    def bulk_move_files(file_ids, target_folder_id, user_id):
        """批量移动文件"""
        from app.models.file import File
        from app.extensions import db
        from datetime import datetime
        
        for i in range(0, len(file_ids), BulkOperations.BATCH_SIZE):
            batch = file_ids[i:i + BulkOperations.BATCH_SIZE]
            
            db.session.query(File).filter(
                File.id.in_(batch),
                File.user_id == user_id
            ).update({
                'folder_id': target_folder_id,
                'updated_at': datetime.utcnow()
            }, synchronize_session=False)
            
            db.session.commit()
