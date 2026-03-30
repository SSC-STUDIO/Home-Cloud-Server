"""
性能优化后的文件路由
与原 files.py 功能相同，但使用优化后的服务
"""

from flask import Blueprint, current_app, jsonify, request
from flask import session
from app.utils.file_service import (
    OptimizedFileService, 
    FileUploadOptimizer,
    FolderTreeOptimizer
)
from app.utils.performance import invalidate_user_storage
from app.routes.auth import login_required

files_optimized = Blueprint('files_optimized', __name__)


@files_optimized.route('/api/files/optimized/list')
@login_required
def api_list_files():
    """优化的文件列表 API（支持分页）"""
    user_id = session.get('user_id')
    folder_id = request.args.get('folder_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    # 限制每页最大数量
    per_page = min(per_page, 100)
    
    result = OptimizedFileService.get_folder_contents(
        folder_id=folder_id,
        user_id=user_id,
        page=page,
        per_page=per_page
    )
    
    return jsonify({
        'success': True,
        'files': [f.to_dict() for f in result['files']],
        'folders': [f.to_dict() for f in result['folders']],
        'pagination': {
            'page': result['page'],
            'per_page': result['per_page'],
            'total_files': result['total_files'],
            'total_pages': result['total_pages']
        }
    })


@files_optimized.route('/api/files/optimized/stats')
@login_required
def api_storage_stats():
    """获取存储统计（使用缓存）"""
    user_id = session.get('user_id')
    stats = OptimizedFileService.get_storage_stats(user_id)
    return jsonify({
        'success': True,
        'stats': stats
    })


@files_optimized.route('/api/files/optimized/search')
@login_required
def api_search_files():
    """优化的文件搜索"""
    user_id = session.get('user_id')
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 100, type=int)
    
    if not query or len(query) < 2:
        return jsonify({
            'success': False,
            'error': 'Search query must be at least 2 characters'
        }), 400
    
    files, folders = OptimizedFileService.search_files_optimized(
        user_id=user_id,
        query=query,
        limit=min(limit, 200)
    )
    
    return jsonify({
        'success': True,
        'query': query,
        'files': [f.to_dict() for f in files],
        'folders': [f.to_dict() for f in folders],
        'total': len(files) + len(folders)
    })


@files_optimized.route('/api/files/optimized/batch-delete', methods=['POST'])
@login_required
def api_batch_delete():
    """批量删除（优化版本）"""
    user_id = session.get('user_id')
    data = request.get_json()
    
    file_ids = data.get('file_ids', [])
    folder_ids = data.get('folder_ids', [])
    
    result = {'files': {'success': 0, 'error': 0}, 'folders': {'success': 0, 'error': 0}}
    
    if file_ids:
        file_result = OptimizedFileService.batch_delete_items(
            item_ids=file_ids,
            item_type='file',
            user_id=user_id
        )
        result['files'] = file_result
    
    if folder_ids:
        folder_result = OptimizedFileService.batch_delete_items(
            item_ids=folder_ids,
            item_type='folder',
            user_id=user_id
        )
        result['folders'] = folder_result
    
    return jsonify({
        'success': True,
        'result': result
    })


@files_optimized.route('/api/files/optimized/folder-tree')
@login_required
def api_folder_tree():
    """获取文件夹树（使用递归 CTE 优化）"""
    user_id = session.get('user_id')
    parent_id = request.args.get('parent_id', type=int)
    
    tree = FolderTreeOptimizer.get_folder_tree(
        user_id=user_id,
        parent_id=parent_id
    )
    
    return jsonify({
        'success': True,
        'tree': tree
    })


@files_optimized.route('/api/files/optimized/folder-size/<int:folder_id>')
@login_required
def api_folder_size(folder_id):
    """获取文件夹大小（包含子文件夹）"""
    size = FolderTreeOptimizer.get_folder_size(folder_id)
    return jsonify({
        'success': True,
        'folder_id': folder_id,
        'size': size,
        'size_human': _format_size(size)
    })


def _format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
