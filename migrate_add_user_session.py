"""
数据库迁移脚本: 创建 UserSession 表
用于会话安全和并发登录检测

使用方法:
    python migrate_add_user_session.py
"""

import os
import sys

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def migrate():
    """执行数据库迁移"""
    from app import create_app
    from app.extensions import db
    from app.models.user_session import UserSession
    
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("数据库迁移: 添加 UserSession 表")
        print("=" * 60)
        
        # 检查表是否存在
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        if 'user_sessions' in existing_tables:
            print("✓ user_sessions 表已存在，跳过创建")
        else:
            # 创建 UserSession 表
            print("→ 创建 user_sessions 表...")
            UserSession.__table__.create(db.engine)
            print("✓ user_sessions 表创建成功")
        
        # 显示表结构
        print("\n表结构:")
        columns = inspector.get_columns('user_sessions') if 'user_sessions' in existing_tables else []
        if not columns:
            # 重新获取
            columns = db.inspect(db.engine).get_columns('user_sessions')
        
        for col in columns:
            print(f"  - {col['name']}: {col['type']}")
        
        # 创建索引
        print("\n→ 创建索引...")
        indexes = inspector.get_indexes('user_sessions') if 'user_sessions' in existing_tables else []
        existing_index_names = [idx['name'] for idx in indexes]
        
        with db.engine.connect() as conn:
            # 用户ID索引
            if 'ix_user_sessions_user_id' not in existing_index_names:
                conn.execute(db.text("CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id)"))
                print("  ✓ 创建索引: ix_user_sessions_user_id")
            
            # session_token唯一索引
            if 'ix_user_sessions_session_token' not in existing_index_names:
                conn.execute(db.text("CREATE UNIQUE INDEX ix_user_sessions_session_token ON user_sessions (session_token)"))
                print("  ✓ 创建索引: ix_user_sessions_session_token (UNIQUE)")
            
            # session_hash索引
            if 'ix_user_sessions_session_hash' not in existing_index_names:
                conn.execute(db.text("CREATE UNIQUE INDEX ix_user_sessions_session_hash ON user_sessions (session_hash)"))
                print("  ✓ 创建索引: ix_user_sessions_session_hash (UNIQUE)")
            
            conn.commit()
        
        print("\n" + "=" * 60)
        print("迁移完成!")
        print("=" * 60)
        
        return True

if __name__ == '__main__':
    try:
        success = migrate()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
