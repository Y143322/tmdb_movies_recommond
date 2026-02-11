"""
扩展模块，包含Flask扩展的初始化
"""
import logging
import threading
import pymysql
from flask import current_app, has_app_context
from flask_login import LoginManager
from flask_jwt_extended import JWTManager
from dbutils.pooled_db import PooledDB
from movies_recommend.models import User
import datetime
from flask_apscheduler import APScheduler

# 配置日志
logger = logging.getLogger(__name__)

# 初始化Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'info'
login_manager.session_protection = 'strong'

# 初始化JWT
jwt = JWTManager()

# 初始化APScheduler
scheduler = APScheduler()

# 数据库连接池
db_pool = None
_db_pool_lock = threading.Lock()
_table_columns_cache = {}
_runtime_db_config = None
_runtime_pool_config = None


def _extract_first_cell(row, key='Field'):
    """兼容 DictCursor/普通游标的首字段读取。"""
    if isinstance(row, dict):
        return row.get(key)
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return None


def _get_table_columns(cursor, table_name):
    """缓存表字段，避免频繁 SHOW COLUMNS。"""
    if table_name in _table_columns_cache:
        return _table_columns_cache[table_name]

    try:
        cursor.execute(f'SHOW COLUMNS FROM {table_name}')
        rows = cursor.fetchall()
        columns = {str(_extract_first_cell(row)).strip() for row in rows if _extract_first_cell(row)}
    except Exception as e:
        logger.warning(f"读取表 {table_name} 字段失败: {e}")
        columns = set()

    _table_columns_cache[table_name] = columns
    return columns


def set_runtime_db_config(db_config, pool_config):
    """缓存运行时数据库配置，供惰性连接池初始化使用。"""
    global _runtime_db_config, _runtime_pool_config
    _runtime_db_config = dict(db_config or {})
    _runtime_pool_config = dict(pool_config or {})


def _has_runtime_db_config():
    """判断是否已有可用的运行时数据库配置。"""
    return bool(_runtime_db_config and _runtime_pool_config)


def _ensure_runtime_db_config():
    """确保运行时数据库配置可用；必要时从当前应用上下文获取。"""
    if _has_runtime_db_config():
        return True

    if has_app_context():
        db_config = current_app.config.get('DB_CONFIG')
        pool_config = current_app.config.get('POOL_CONFIG')
        if db_config and pool_config:
            set_runtime_db_config(db_config, pool_config)
            return True

    return False


def _create_db_pool_from_runtime_config():
    """根据运行时配置创建连接池实例。"""
    return PooledDB(
        creator=pymysql,
        **_runtime_pool_config,
        **_runtime_db_config
    )

def init_db_pool(app):
    """初始化数据库连接池

    Args:
        app: Flask应用实例
    """
    global db_pool, _runtime_db_config, _runtime_pool_config
    try:
        db_config = app.config['DB_CONFIG']
        pool_config = app.config['POOL_CONFIG']

        set_runtime_db_config(db_config, pool_config)

        db_pool = _create_db_pool_from_runtime_config()
        app.logger.info("数据库连接池创建成功！")
    except Exception as e:
        app.logger.error(f"创建数据库连接池失败: {e}")
        db_pool = None

def get_db_connection():
    """获取数据库连接

    Returns:
        pymysql.Connection: 数据库连接对象

    Raises:
        Exception: 如果连接池未初始化或连接失败
    """
    global db_pool
    if db_pool is None:
        with _db_pool_lock:
            if db_pool is None:
                if not _ensure_runtime_db_config():
                    raise Exception("数据库连接池未初始化，请检查数据库配置")
                db_pool = _create_db_pool_from_runtime_config()
                logger.info("数据库连接池惰性初始化完成")

    try:
        conn = db_pool.connection()
        return conn
    except Exception as e:
        raise Exception(f"数据库连接错误: {str(e)}")

# 用户加载函数
@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        admin_columns = _get_table_columns(cursor, 'admininfo')
        user_columns = _get_table_columns(cursor, 'userinfo')

        # 先检查是否是管理员
        admin_select_fields = ['id', 'username', 'email']
        if 'reset_password' in admin_columns:
            admin_select_fields.append('reset_password')

        cursor.execute(
            f'SELECT {", ".join(admin_select_fields)} FROM admininfo WHERE id = %s',
            (user_id,)
        )
        admin_data = cursor.fetchone()

        if admin_data:
            reset_password = bool(admin_data.get('reset_password', 0)) if 'reset_password' in admin_columns else False

            return User(
                id=admin_data['id'],
                username=admin_data['username'],
                email=admin_data.get('email'),
                is_admin=True,
                reset_password=reset_password
            )

        # 如果不是管理员，检查普通用户
        user_select_fields = ['id', 'username', 'email']
        if 'reset_password' in user_columns:
            user_select_fields.append('reset_password')
        if 'status' in user_columns:
            user_select_fields.append('status')
        if 'mute_expires_at' in user_columns:
            user_select_fields.append('mute_expires_at')

        cursor.execute(
            f'SELECT {", ".join(user_select_fields)} FROM userinfo WHERE id = %s',
            (user_id,)
        )
        user_data = cursor.fetchone()

        if user_data:
            reset_password = bool(user_data.get('reset_password', 0)) if 'reset_password' in user_columns else False

            # 获取用户状态和禁言到期时间
            status = user_data.get('status') if 'status' in user_columns else 'active'
            status = status or 'active'
            mute_expires_at = user_data.get('mute_expires_at') if 'mute_expires_at' in user_columns else None
            
            try:
                # 加载禁言到期时间
                if 'mute_expires_at' in user_columns and status == 'banned' and mute_expires_at:
                    # 如果禁言已过期，自动解除
                    if mute_expires_at < datetime.datetime.now():
                        update_sql = 'UPDATE userinfo SET mute_expires_at = NULL WHERE id = %s'
                        if 'status' in user_columns:
                            update_sql = 'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s'
                        cursor.execute(update_sql, (user_id,))
                        conn.commit()
                        status = 'active'
                        mute_expires_at = None
            except Exception as e:
                logger.error(f"获取用户状态出错: {e}")

            return User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data.get('email'),
                is_admin=False,
                reset_password=reset_password,
                mute_expires_at=mute_expires_at,
                status=status
            )

        return None
    except Exception as e:
        logger.error(f"加载用户时出错: {str(e)}")
        return None
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
