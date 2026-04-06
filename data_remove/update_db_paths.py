#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Database File Path Mapping Update Tool

This script is used to update file path mappings in SQLite database, replacing Linux paths with Windows paths.
"""

import os
import sqlite3
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'update_db_paths_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
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

def update_file_paths(db_path, old_path_prefix, new_path_prefix, dry_run=False):
    """Update file path mappings in the database
    
    Args:
        db_path: Database file path
        old_path_prefix: Old path prefix to be replaced
        new_path_prefix: New path prefix
        dry_run: Whether to run in simulation mode
    
    Returns:
        tuple: (Number of successfully updated records, Number of failed records)
    """
    conn = None
    try:
        # Check if database file exists
        if not os.path.exists(db_path):
            logger.error(f'Database file does not exist: {db_path}')
            return 0, 0
        
        # Connect to database
        logger.info(f'Connecting to database: {db_path}')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query for file records containing the old path prefix
        cursor.execute("SELECT id, file_path FROM file WHERE file_path LIKE ?", (f'{old_path_prefix}%',))
        files = cursor.fetchall()
        
        logger.info(f'Found {len(files)} file records that need path updates')
        
        success_count = 0
        failed_count = 0
        
        for file_id, old_file_path in files:
            try:
                # Build new file path
                # Remove old prefix, add new prefix
                relative_path = old_file_path[len(old_path_prefix):]
                # Ensure correct path separator
                relative_path = relative_path.replace('/', '\\')
                new_file_path = f'{new_path_prefix}{relative_path}'
                
                if dry_run:
                    logger.info(f'[DRY RUN] Will update: ID={file_id}, {old_file_path} -> {new_file_path}')
                    success_count += 1
                else:
                    # Update database record
                    cursor.execute("UPDATE file SET file_path = ? WHERE id = ?", (new_file_path, file_id))
                    success_count += 1
                    logger.info(f'Updated: ID={file_id}, {old_file_path} -> {new_file_path}')
                
                # Show progress every 100 records
                if success_count % 100 == 0:
                    logger.info(f'Processed {success_count} records')
                    
            except Exception as e:
                logger.error(f'Failed to update file path (ID={file_id}, {old_file_path}): {str(e)}')
                failed_count += 1
        
        # Commit changes
        if not dry_run and success_count > 0:
            conn.commit()
            logger.info(f'Committed {success_count} changes to database')
        
        # Show sample paths
        if success_count > 0:
            cursor.execute("SELECT file_path FROM file LIMIT 5")
            sample_paths = cursor.fetchall()
            logger.info('Updated file path examples:')
            for path in sample_paths:
                logger.info(f'  {path[0]}')
        
        return success_count, failed_count
    
    except Exception as e:
        logger.error(f'Error during database path update: {str(e)}')
        if conn and not dry_run:
            conn.rollback()
        return 0, 0
    finally:
        if conn:
            conn.close()
            logger.info('Database connection closed')

def verify_update(db_path):
    """Verify update results"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Count files
        cursor.execute("SELECT COUNT(*) FROM file")
        file_count = cursor.fetchone()[0]
        logger.info(f'Total files in database: {file_count}')
        
        # Check if there are any Linux-style paths left (starting with /)
        cursor.execute("SELECT COUNT(*) FROM file WHERE file_path LIKE '/%'")
        linux_style_paths = cursor.fetchone()[0]
        logger.info(f'Records still containing Linux-style paths: {linux_style_paths}')
        
        # If there are Linux-style paths, show some examples
        if linux_style_paths > 0:
            cursor.execute("SELECT file_path FROM file WHERE file_path LIKE '/%' LIMIT 5")
            remaining_linux_paths = cursor.fetchall()
            logger.warning('Remaining Linux-style path examples:')
            for path in remaining_linux_paths:
                logger.warning(f'  {path[0]}')
        
        return True
    except Exception as e:
        logger.error(f'Failed to verify update results: {str(e)}')
        return False
    finally:
        if conn:
            conn.close()

def check_database_structure(db_path):
    """Check database structure"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        logger.info(f'Database tables:')
        for table in tables:
            table_name = table[0]
            logger.info(f'  - {table_name}')
            
            # SECURITY FIX: Validate table name before using in PRAGMA
            if not validate_sql_identifier(table_name):
                logger.warning(f'    Skipping invalid table name: {table_name}')
                continue
            
            # Get table structure
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            logger.info(f'    Columns:')
            for col in columns:
                logger.info(f'      {col[1]} ({col[2]})')
            
            # Get some sample data
            try:
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                rows = cursor.fetchall()
                if rows:
                    logger.info(f'    Sample data:')
                    for row in rows:
                        logger.info(f'      {row}')
            except Exception as e:
                logger.warning(f"    Failed to read data from table {table_name}: {str(e)}")
        
        return tables
    except Exception as e:
        logger.error(f'Failed to check database structure: {str(e)}')
        return []
    finally:
        if conn:
            conn.close()

def update_file_paths_in_table(db_path, table_name, column_name, old_path_prefix, new_path_prefix, dry_run):
    """Update file paths in the specified table"""
    # SECURITY FIX: Validate identifiers to prevent SQL injection
    if not validate_sql_identifier(table_name):
        logger.error(f'Invalid table name: {table_name}')
        return 0, 1
    if not validate_sql_identifier(column_name):
        logger.error(f'Invalid column name: {column_name}')
        return 0, 1
    
    conn = None
    success = 0
    failed = 0
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query records containing old paths
        cursor.execute(f"SELECT id, {column_name} FROM {table_name} WHERE {column_name} LIKE ?", (f"{old_path_prefix}%",))
        records = cursor.fetchall()
        
        logger.info(f'Found {len(records)} records to update in table {table_name}.{column_name}')
        
        for record in records:
            record_id, old_path = record
            try:
                # Replace path prefix
                new_path = old_path.replace(old_path_prefix, new_path_prefix)
                
                logger.info(f'  Record {record_id}: {old_path} -> {new_path}')
                
                if not dry_run:
                    # Execute update
                    cursor.execute(f"UPDATE {table_name} SET {column_name} = ? WHERE id = ?", (new_path, record_id))
                success += 1
            except Exception as e:
                logger.error(f'  Failed to update record {record_id}: {str(e)}')
                failed += 1
        
        if not dry_run:
            conn.commit()
            logger.info(f'Committed {success} updates')
            
    except Exception as e:
        logger.error(f'Error updating table {table_name}: {str(e)}')
        failed += len(records)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return success, failed

def update_all_file_paths(db_path, old_path_prefix, new_path_prefix, dry_run):
    """Update fields that may contain file paths in all tables"""
    total_success = 0
    total_failed = 0
    
    # From logs we see table name is files, and based on sample data, the 4th column contains paths
    # Let's try using the correct field name
    tables_to_update = [
        ("files", "path")  # First try the path field
    ]
    
    # Check and update each table
    for table_name, column_name in tables_to_update:
        try:
            logger.info(f'\nStarting update for {column_name} field in table {table_name}...')
            success, failed = update_file_paths_in_table(
                db_path, table_name, column_name, old_path_prefix, new_path_prefix, dry_run
            )
            total_success += success
            total_failed += failed
        except Exception as e:
            logger.warning(f'Error attempting to update {column_name} field in table {table_name}: {str(e)}')
    
    # If first attempt fails, try other possible field names
    # From sample data, the 4th field contains paths
    if total_success == 0 and total_failed == 0:
        logger.info('\nAttempting dynamic field name matching...')
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get table structure
            cursor.execute("PRAGMA table_info(files)")
            columns = cursor.fetchall()
            
            # Iterate through all fields to find ones containing paths
            for col in columns:
                col_name = col[1]
                try:
                    # Try to query records containing paths
                    cursor.execute(f"SELECT id, {col_name} FROM files WHERE {col_name} LIKE ? LIMIT 1", 
                                  (f"{old_path_prefix}%",))
                    if cursor.fetchone():
                        logger.info(f'Found path-containing field: {col_name}')
                        success, failed = update_file_paths_in_table(
                            db_path, "files", col_name, old_path_prefix, new_path_prefix, dry_run
                        )
                        total_success += success
                        total_failed += failed
                        break
                except Exception as e:
                    logger.warning(f'Error checking field {col_name}: {str(e)}')
        except Exception as e:
            logger.error(f'Dynamic field matching failed: {str(e)}')
        finally:
            if conn:
                conn.close()
    
    return total_success, total_failed

def main():
    """Main function"""
    print("=" * 80)
    print("Database File Path Mapping Update Tool")
    print("=" * 80)
    
    # 配置参数
    db_path = r"C:\cloud_storage\home-cloud\production.db"
    old_path_prefix = "/mnt/cloud_storage/uploads"
    new_path_prefix = r"C:\cloud_storage\uploads"
    dry_run = False  # 设置为True以进行模拟运行
    
    logger.info(f'Update configuration:')
    logger.info(f'  Database path: {db_path}')
    logger.info(f'  Old path prefix: {old_path_prefix}')
    logger.info(f'  New path prefix: {new_path_prefix}')
    logger.info(f'  Simulation run: {dry_run}')
    
    # Check database structure
    logger.info('Checking database structure...')
    tables = check_database_structure(db_path)
    
    # Execute path update
    logger.info('\nStarting file path update...')
    success, failed = update_all_file_paths(db_path, old_path_prefix, new_path_prefix, dry_run)
    
    print("\n" + "=" * 80)
    print("Path update completed!")
    print(f"  Success: {success}")
    print(f"  Failed: {failed}")
    print(f"  Simulation run: {'Yes' if dry_run else 'No'}")
    print(f"  Log file: update_db_paths_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    print("=" * 80)
    
    return 0

if __name__ == '__main__':
    exit(main())