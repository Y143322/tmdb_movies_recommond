"""
数据库工具模块，集中管理数据库相关的工具函数
"""
import pymysql
from movies_recommend.logger import get_logger

# 获取日志记录器
logger = get_logger('app')

def test_db_connection(db_config):
    """测试数据库连接
    
    Args:
        db_config (dict): 数据库配置字典
        
    Returns:
        bool: 连接是否成功
    """
    try:
        conn = pymysql.connect(**db_config)
        conn.close()
        logger.info("数据库连接成功！")
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        logger.error("请检查以下可能的问题:")
        logger.error("1. MySQL服务是否已启动")
        logger.error("2. 用户名和密码是否正确")
        logger.error("3. 数据库'movies_recommend'是否存在")
        logger.error("4. 用户是否有权限访问该数据库")
        return False

def execute_sql_script(script_path, db_config=None, conn=None):
    """执行SQL脚本文件
    
    Args:
        script_path (str): SQL脚本文件路径
        db_config (dict, optional): 数据库配置字典. 默认为 None.
        conn (pymysql.Connection, optional): 数据库连接对象. 默认为 None.
        
    Returns:
        bool: 执行是否成功
    """
    close_conn = False
    try:
        # 如果没有提供连接，则创建新连接
        if conn is None and db_config is not None:
            conn = pymysql.connect(**db_config)
            close_conn = True
        
        if conn is None:
            raise ValueError("必须提供数据库连接或配置")
            
        cursor = conn.cursor()
        
        # 读取SQL脚本文件
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
            
        # 执行SQL脚本
        for statement in sql_script.split(';'):
            if statement.strip():
                cursor.execute(statement)
                
        conn.commit()
        logger.info(f"SQL脚本执行成功: {script_path}")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"SQL脚本执行失败: {e}")
        return False
    finally:
        if cursor:
            cursor.close()
        if close_conn and conn:
            conn.close()
