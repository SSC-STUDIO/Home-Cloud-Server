#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database Path Update Verification Tool

Verify if Linux paths in the database have been successfully updated to Windows paths.
"""

import os
import sqlite3
import logging
from datetime import datetime

# 配置日志
log_file = f"verify_db_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def validate_sql_identifier(identifier):
    """验证SQL标识符是否合法（防止SQL注入）"""
    import re
    if not identifier:
        return False
    # 只允许字母、数字、下划线，且不能以数字开头
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, identifier))

def find_path_column(db_path):
    """Find the column containing file paths"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取表结构
        cursor.execute("PRAGMA table_info(files)")
        columns = cursor.fetchall()
        
        logger.info('Checking columns of files table:')
        for col in columns:
                col_name = col[1]
                col_type = col[2]
                logger.info(f'  - {col_name} ({col_type})')
        
        # Try to find columns containing paths
        # Check first few rows to see which column contains path information
        cursor.execute("SELECT * FROM files LIMIT 2")
        rows = cursor.fetchall()
        
        if rows:
            logger.info('\nSample data:')
            for i, row in enumerate(rows):
                logger.info(f'  记录 {i+1}: {row}')
            
            # Check each column for values containing path patterns
            for col_idx, col in enumerate(columns):
                col_name = col[1]
                for row in rows:
                    if col_idx < len(row) and isinstance(row[col_idx], str):
                        # Check if it contains path characteristics
                        if ('/' in row[col_idx] or '\\' in row[col_idx]) and ('.' in row[col_idx] or row[col_idx].startswith('/')):
                            logger.info(f'\nFound potential path column: {col_name} (index {col_idx})')
                            logger.info(f'  Sample value: {row[col_idx]}')
                            return col_name
        
        logger.warning('Unable to automatically identify path-containing column')
        return None
        
    except Exception as e:
        logger.error(f'Error finding path column: {str(e)}')
        return None
    finally:
        if conn:
            conn.close()

def verify_path_update(db_path, old_path_prefix, new_path_prefix):
    """Verify if paths in the database have been updated"""
    conn = None
    try:
        # Check if database file exists
        if not os.path.exists(db_path):
            logger.error(f'Database file does not exist: {db_path}')
            return False
        
        # Find the column containing paths
        path_column = find_path_column(db_path)
        if not path_column:
            logger.error('Unable to find column containing path information')
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logger.info(f'\nStarting database path update verification: {db_path}')
        logger.info(f'Using column: {path_column}')
        
        # SECURITY FIX: Validate column name to prevent SQL injection
        if not validate_sql_identifier(path_column):
            logger.error(f'Invalid column name: {path_column}')
            return False
        
        # Check if there are any old paths left
        cursor.execute(f"SELECT COUNT(*) FROM files WHERE {path_column} LIKE ?", (f"{old_path_prefix}%",))
        old_path_count = cursor.fetchone()[0]
        
        # Check the number of new paths
        cursor.execute(f"SELECT COUNT(*) FROM files WHERE {path_column} LIKE ?", (f"{new_path_prefix}%",))
        new_path_count = cursor.fetchone()[0]
        
        # Count total rows
        cursor.execute("SELECT COUNT(*) FROM files")
        total_count = cursor.fetchone()[0]
        
        logger.info(f'Verification results:')
        logger.info(f'  Total records: {total_count}')
        logger.info(f'  Remaining old paths: {old_path_count}')
        logger.info(f'  New paths: {new_path_count}')
        
        # Check some new path records
        cursor.execute(f"SELECT id, {path_column} FROM files WHERE {path_column} LIKE ? LIMIT 5", (f"{new_path_prefix}%",))
        sample_records = cursor.fetchall()
        
        if sample_records:
            logger.info('\nUpdated sample records:')
            for record in sample_records:
                logger.info(f'  Record {record[0]}: {record[1]}')
        
        # Check if there are any old path records
        if old_path_count > 0:
            cursor.execute(f"SELECT id, {path_column} FROM files WHERE {path_column} LIKE ? LIMIT 3", (f"{old_path_prefix}%",))
            old_records = cursor.fetchall()
            if old_records:
                logger.info('\nUnupdated sample records:')
                for record in old_records:
                    logger.info(f'  Record {record[0]}: {record[1]}')
        
        # Determine verification result
        if old_path_count == 0 and new_path_count > 0:
            logger.info('\n✅ Path update verification successful! All Linux paths have been updated to Windows paths.')
            return True
        elif old_path_count == 0 and new_path_count == 0:
            logger.warning('\n⚠️  No path-containing records found, path format may not match expectations.')
            return False
        else:
            logger.warning(f'\n❌ Path update verification not fully successful, {old_path_count} records still contain old paths.')
            return False
            
    except Exception as e:
        logger.error(f'Error during verification: {str(e)}')
        return False
    finally:
        if conn:
            conn.close()

def main():
    """Main function"""
    print("=" * 80)
    print("Database Path Update Verification Tool")
    print("=" * 80)
    
    # 配置参数
    db_path = r"C:\cloud_storage\home-cloud\production.db"
    old_path_prefix = "/mnt/cloud_storage/uploads"
    new_path_prefix = r"C:\cloud_storage\uploads"
    
    logger.info(f'Verification configuration:')
    logger.info(f'  Database path: {db_path}')
    logger.info(f'  Old path prefix: {old_path_prefix}')
    logger.info(f'  New path prefix: {new_path_prefix}')

    # 执行验证
    success = verify_path_update(db_path, old_path_prefix, new_path_prefix)
    
    print("\n" + "=" * 80)
    print("Verification completed!")
    print(f"  Verification status: {'Success' if success else 'Failed'}")
    print(f"  Log file: {log_file}")
    print("=" * 80)
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())