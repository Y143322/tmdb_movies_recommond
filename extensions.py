"""
扩展模块，包含Flask扩展的初始化
"""
import os
import sys
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
import pymysql
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

def init_db_pool(app):
    """初始化数据库连接池

    Args:
        app: Flask应用实例
    """
    global db_pool
    try:
        db_config = app.config['DB_CONFIG']
        pool_config = app.config['POOL_CONFIG']

        db_pool = PooledDB(
            creator=pymysql,
            **pool_config,
            **db_config
        )
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
    if db_pool is None:
        raise Exception("数据库连接池未初始化，请检查数据库配置")

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

        # 先检查是否是管理员
        cursor.execute('SELECT * FROM admininfo WHERE id = %s', (user_id,))
        admin_data = cursor.fetchone()

        if admin_data:
            # 检查是否有 reset_password 字段
            reset_password = False
            try:
                cursor.execute('SHOW COLUMNS FROM admininfo LIKE "reset_password"')
                if cursor.fetchone():
                    cursor.execute('SELECT reset_password FROM admininfo WHERE id = %s', (user_id,))
                    reset_data = cursor.fetchone()
                    if reset_data:
                        reset_password = bool(reset_data.get('reset_password', 0))
            except Exception as e:
                logger.error(f"获取 reset_password 状态出错: {e}")

            return User(
                id=admin_data['id'],
                username=admin_data['username'],
                email=admin_data.get('email'),
                is_admin=True,
                reset_password=reset_password
            )

        # 如果不是管理员，检查普通用户
        cursor.execute('SELECT * FROM userinfo WHERE id = %s', (user_id,))
        user_data = cursor.fetchone()

        if user_data:
            # 检查是否有 reset_password 字段
            reset_password = False
            try:
                cursor.execute('SHOW COLUMNS FROM userinfo LIKE "reset_password"')
                if cursor.fetchone():
                    cursor.execute('SELECT reset_password FROM userinfo WHERE id = %s', (user_id,))
                    reset_data = cursor.fetchone()
                    if reset_data:
                        reset_password = bool(reset_data.get('reset_password', 0))
            except Exception as e:
                logger.error(f"获取 reset_password 状态出错: {e}")
                
            # 获取用户状态和禁言到期时间
            status = 'active'
            mute_expires_at = None
            
            try:
                # 检查状态和禁言到期时间字段
                cursor.execute('SHOW COLUMNS FROM userinfo LIKE "status"')
                has_status_field = cursor.fetchone() is not None
                
                cursor.execute('SHOW COLUMNS FROM userinfo LIKE "mute_expires_at"')
                has_expire_field = cursor.fetchone() is not None
                
                # 加载状态字段
                if has_status_field:
                    cursor.execute('SELECT status FROM userinfo WHERE id = %s', (user_id,))
                    status_data = cursor.fetchone()
                    if status_data and status_data.get('status'):
                        status = status_data.get('status')
                
                # 加载禁言到期时间
                if has_expire_field and status == 'banned':
                    cursor.execute('SELECT mute_expires_at FROM userinfo WHERE id = %s', (user_id,))
                    expire_data = cursor.fetchone()
                    if expire_data:
                        mute_expires_at = expire_data.get('mute_expires_at')
                        
                        # 如果禁言已过期，自动解除
                        if mute_expires_at and mute_expires_at < datetime.datetime.now():
                            cursor.execute(
                                'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s',
                                (user_id,)
                            )
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
