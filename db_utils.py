"""
数据库工具模块，集中管理数据库相关的工具函数
"""
import random
import time
import pymysql
from movies_recommend.logger import get_logger

# 获取日志记录器
logger = get_logger('app')
_id_range_cache = {}
_id_range_cache_ttl_seconds = 60


def _extract_first_value(row, key):
    """兼容 DictCursor 和普通游标的取值。"""
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return None


def fetch_random_rows_by_id_range(cursor, table, select_columns, limit, where_clause='', params=None, id_column='id'):
    """基于随机 ID 起点获取随机行，避免 ORDER BY RAND() 的全表排序开销。"""
    if limit <= 0:
        return []

    base_params = list(params or [])
    normalized_where = (where_clause or '').strip()
    if normalized_where and normalized_where.lower().startswith('where '):
        normalized_where = normalized_where[6:].strip()

    cache_key = f'{table}:{id_column}'
    now_ts = time.time()
    cache_item = _id_range_cache.get(cache_key)

    if cache_item and now_ts - cache_item.get('ts', 0) <= _id_range_cache_ttl_seconds:
        range_row = cache_item.get('row')
    else:
        cursor.execute(f'SELECT MIN({id_column}) AS min_id, MAX({id_column}) AS max_id FROM {table}')
        range_row = cursor.fetchone()
        _id_range_cache[cache_key] = {'ts': now_ts, 'row': range_row}

    min_id = _extract_first_value(range_row, 'min_id')
    max_id = None
    if isinstance(range_row, dict):
        max_id = range_row.get('max_id')
    elif isinstance(range_row, (list, tuple)) and len(range_row) >= 2:
        max_id = range_row[1]

    if min_id is None or max_id is None:
        return []

    pivot = random.randint(int(min_id), int(max_id))

    def _where_with_id(condition):
        if normalized_where:
            return f'WHERE {normalized_where} AND {condition}'
        return f'WHERE {condition}'

    query_ge = f'''
        SELECT {select_columns}
        FROM {table}
        {_where_with_id(f'{id_column} >= %s')}
        ORDER BY {id_column}
        LIMIT %s
    '''
    cursor.execute(query_ge, base_params + [pivot, limit])
    rows = list(cursor.fetchall())

    remaining = limit - len(rows)
    if remaining > 0:
        query_lt = f'''
            SELECT {select_columns}
            FROM {table}
            {_where_with_id(f'{id_column} < %s')}
            ORDER BY {id_column}
            LIMIT %s
        '''
        cursor.execute(query_lt, base_params + [pivot, remaining])
        rows.extend(cursor.fetchall())

    if len(rows) > 1:
        random.shuffle(rows)

    return rows

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
    cursor = None
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
