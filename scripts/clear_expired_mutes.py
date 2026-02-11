#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
清理过期的用户禁言状态

此脚本用于自动检查并清理已过期的用户禁言状态。
可以通过计划任务定期运行，如每小时执行一次。
"""

import sys
import os
import datetime
import pymysql
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 统一脚本引导
try:
    from _bootstrap import setup_project_path
except ModuleNotFoundError:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from _bootstrap import setup_project_path

package_root, project_root = setup_project_path()

# 导入项目配置
from movies_recommend.config import Config

# 配置日志记录
log_dir = os.path.join(str(package_root), 'archive', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'clear_mutes.log')

logger = logging.getLogger('clear_mutes')
logger.setLevel(logging.INFO)

# 文件处理器
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(file_handler)

# 控制台处理器
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))
logger.addHandler(console_handler)

def get_db_connection():
    """获取数据库连接"""
    try:
        db_config = Config.DB_CONFIG
        conn = pymysql.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['database'],
            charset=db_config.get('charset', 'utf8mb4'),
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"连接数据库失败: {e}")
        return None

def clear_expired_mutes():
    """清理过期的用户禁言"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = conn.cursor()
    now = datetime.datetime.now()
    
    try:
        # 查询所有已过期的禁言
        cursor.execute(
            """
            SELECT id, username, mute_expires_at
            FROM userinfo
            WHERE status = 'banned' 
              AND mute_expires_at IS NOT NULL 
              AND mute_expires_at < %s
            """,
            (now,)
        )
        expired_mutes = cursor.fetchall()
        
        if not expired_mutes:
            logger.info("没有找到过期的禁言")
            return True
        
        # 清理过期禁言
        user_ids = [user['id'] for user in expired_mutes]
        placeholders = ', '.join(['%s'] * len(user_ids))
        
        cursor.execute(
            f"""
            UPDATE userinfo
            SET status = 'active', mute_expires_at = NULL
            WHERE id IN ({placeholders})
            """,
            user_ids
        )
        
        conn.commit()
        logger.info(f"已清理 {len(user_ids)} 个过期禁言")
        
        return True
    
    except Exception as e:
        logger.error(f"清理过期禁言失败: {e}")
        conn.rollback()
        return False
    
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    logger.info("开始清理过期的用户禁言...")
    success = clear_expired_mutes()
    if success:
        logger.info("清理过期禁言完成")
    else:
        logger.error("清理过期禁言时发生错误") 
