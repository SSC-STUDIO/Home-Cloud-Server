"""
优化后的文件服务模块
包含缓存、批量操作和性能优化
"""

from functools import wraps
from flask import current_app
from app.extensions import db
from app.models.file import File, Folder
from app.models.user import User
from app.utils.performance import cache, invalidate_user_storage
from sqlalchemy import func
import os


class OptimizedFileService:
    """优化后的文件服务类"""
    
    CACHE_TIMEOUT = 60  # 缓存60秒
    
    @staticmethod
    def get_user_storage_used(user_id: int, use_cache: bool = True) -> int:
        """获取用户存储使用量（带缓存）"""
        cache_key = f'user_storage:{user_id}'
        
        if use_cache:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        
        # 使用 SQL 聚合函数计算
        total_size = db.session.query(
            func.sum(File.size)
        ).filter(
            File.user_id == user_id,
            File.is_deleted == False
        ).scalar() or 0
        
        if use_cache:
            cache.set(cache_key, total_size, timeout=OptimizedFileService.CACHE_TIMEOUT)
        
        return total_size
    
    @staticmethod
    def get_folder_contents(folder_id: int, user_id: int, page: int = 1, per_page: int = 50):
        """获取文件夹内容（分页、优化查询）"""
        offset = (page - 1) * per_page
        
        # 使用单个查询获取文件和文件夹
        files = File.query.filter_by(
            folder_id=folder_id,
            user_id=user_id,
            is_deleted=False
        ).order_by(
            File.updated_at.desc()
        ).offset(offset).limit(per_page).all()
        
        folders = Folder.query.filter_by(
            parent_id=folder_id,
            user_id=user_id,
            is_deleted=False
        ).order_by(
            Folder.name.asc()
        ).all()
        
        # 获取总数用于分页
        total_files = File.query.filter_by(
            folder_id=folder_id,
            user_id=user_id,
            is_deleted=False
        ).count()
        
        return {
            'files': files,
            'folders': folders,
            'total_files': total_files,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_files + per_page - 1) // per_page
        }
    
    @staticmethod
    def search_files_optimized(user_id: int, query: str, limit: int = 100):
        """优化的文件搜索"""
        from sqlalchemy import or_
        
        # 使用 ILIKE 进行不区分大小写的搜索
        search_pattern = f"%{query}%"
        
        files = File.query.filter(
            File.user_id == user_id,
            File.is_deleted == False,
            File.original_filename.ilike(search_pattern)
        ).limit(limit).all()
        
        folders = Folder.query.filter(
            Folder.user_id == user_id,
            Folder.is_deleted == False,
            Folder.name.ilike(search_pattern)
        ).limit(limit).all()
        
        return files, folders
    
    @staticmethod
    def batch_delete_items(item_ids: list, item_type: str, user_id: int) -> dict:
        """批量删除项目（文件或文件夹）"""
        success_count = 0
        error_count = 0
        
        BATCH_SIZE = 100
        
        for i in range(0, len(item_ids), BATCH_SIZE):
            batch = item_ids[i:i + BATCH_SIZE]
            
            try:
                if item_type == 'file':
                    # 批量更新文件为已删除
                    db.session.query(File).filter(
                        File.id.in_(batch),
                        File.user_id == user_id
                    ).update({'is_deleted': True}, synchronize_session=False)
                
                elif item_type == 'folder':
                    # 批量更新文件夹为已删除
                    db.session.query(Folder).filter(
                        Folder.id.in_(batch),
                        Folder.user_id == user_id
                    ).update({'is_deleted': True}, synchronize_session=False)
                    
                    # 同时删除文件夹内的文件
                    db.session.query(File).filter(
                        File.folder_id.in_(batch),
                        File.user_id == user_id
                    ).update({'is_deleted': True}, synchronize_session=False)
                
                db.session.commit()
                success_count += len(batch)
                
            except Exception as e:
                db.session.rollback()
                error_count += len(batch)
                current_app.logger.error(f'Batch delete error: {e}')
        
        # 使缓存失效
        invalidate_user_storage(user_id)
        
        return {
            'success_count': success_count,
            'error_count': error_count
        }
    
    @staticmethod
    def get_storage_stats(user_id: int) -> dict:
        """获取存储统计信息（优化的聚合查询）"""
        cache_key = f'storage_stats:{user_id}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # 文件类型统计
        file_types = db.session.query(
            File.file_type,
            func.count(File.id).label('count'),
            func.sum(File.size).label('total_size')
        ).filter(
            File.user_id == user_id,
            File.is_deleted == False
        ).group_by(File.file_type).all()
        
        # 文件数量统计
        total_files = db.session.query(func.count(File.id)).filter(
            File.user_id == user_id,
            File.is_deleted == False
        ).scalar() or 0
        
        total_folders = db.session.query(func.count(Folder.id)).filter(
            Folder.user_id == user_id,
            Folder.is_deleted == False
        ).scalar() or 0
        
        stats = {
            'total_files': total_files,
            'total_folders': total_folders,
            'storage_used': OptimizedFileService.get_user_storage_used(user_id),
            'file_types': [
                {
                    'type': ft[0] or 'other',
                    'count': ft[1],
                    'size': ft[2] or 0
                }
                for ft in file_types
            ]
        }
        
        cache.set(cache_key, stats, timeout=300)  # 缓存5分钟
        return stats
    
    @staticmethod
    def invalidate_storage_cache(user_id: int):
        """使用户的存储相关缓存失效"""
        cache.delete(f'user_storage:{user_id}')
        cache.delete(f'storage_stats:{user_id}')


class FileUploadOptimizer:
    """文件上传优化工具类"""
    
    CHUNK_SIZE = 8192  # 8KB 块大小
    
    @staticmethod
    def save_file_stream(file_obj, save_path: str) -> bool:
        """流式保存文件，避免内存溢出"""
        try:
            with open(save_path, 'wb') as f:
                while True:
                    chunk = file_obj.read(FileUploadOptimizer.CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
            return True
        except Exception as e:
            current_app.logger.error(f'File save error: {e}')
            return False
    
    @staticmethod
    def validate_upload_space(user_id: int, file_size: int) -> bool:
        """验证用户是否有足够的上传空间（使用缓存）"""
        user = User.query.get(user_id)
        if not user:
            return False
        
        storage_used = OptimizedFileService.get_user_storage_used(user_id)
        return (storage_used + file_size) <= user.storage_quota


class FolderTreeOptimizer:
    """文件夹树操作优化"""
    
    @staticmethod
    def get_folder_tree(user_id: int, parent_id: int = None) -> list:
        """获取文件夹树结构（使用递归 CTE 优化）"""
        from sqlalchemy import text
        
        # 使用递归 CTE 查询文件夹树
        query = text("""
            WITH RECURSIVE folder_tree AS (
                -- 根文件夹
                SELECT id, name, parent_id, 0 as depth
                FROM folders
                WHERE user_id = :user_id 
                  AND parent_id IS :parent_id
                  AND is_deleted = 0
                
                UNION ALL
                
                -- 子文件夹
                SELECT f.id, f.name, f.parent_id, ft.depth + 1
                FROM folders f
                INNER JOIN folder_tree ft ON f.parent_id = ft.id
                WHERE f.user_id = :user_id
                  AND f.is_deleted = 0
            )
            SELECT * FROM folder_tree ORDER BY depth, name
        """)
        
        result = db.session.execute(query, {
            'user_id': user_id,
            'parent_id': parent_id
        })
        
        return [
            {
                'id': row[0],
                'name': row[1],
                'parent_id': row[2],
                'depth': row[3]
            }
            for row in result
        ]
    
    @staticmethod
    def get_folder_size(folder_id: int) -> int:
        """获取文件夹总大小（包含子文件夹）"""
        from sqlalchemy import text
        
        query = text("""
            WITH RECURSIVE folder_tree AS (
                SELECT id FROM folders WHERE id = :folder_id
                UNION ALL
                SELECT f.id FROM folders f
                INNER JOIN folder_tree ft ON f.parent_id = ft.id
                WHERE f.is_deleted = 0
            )
            SELECT COALESCE(SUM(f.size), 0) 
            FROM files f
            WHERE f.folder_id IN (SELECT id FROM folder_tree)
              AND f.is_deleted = 0
        """)
        
        result = db.session.execute(query, {'folder_id': folder_id}).scalar()
        return result or 0
