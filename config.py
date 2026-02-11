"""
配置模块，包含应用程序的各种配置
"""
import os
import datetime
from typing import Any, Mapping

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except Exception:
    # 未安装 python-dotenv 或读取失败时，继续使用系统环境变量
    pass


def validate_required_settings(settings: Mapping[str, Any]) -> None:
    """仅用于生产环境：校验必须配置项。"""
    missing_vars = []

    if not settings.get('SECRET_KEY'):
        missing_vars.append('SECRET_KEY')

    if not settings.get('JWT_SECRET_KEY'):
        missing_vars.append('JWT_SECRET_KEY')

    db_config = settings.get('DB_CONFIG')
    if not isinstance(db_config, dict) or not db_config.get('password'):
        missing_vars.append('DB_PASSWORD')

    if not settings.get('ADMIN_VERIFICATION_CODE'):
        missing_vars.append('ADMIN_VERIFICATION_CODE')

    if missing_vars:
        missing_text = ', '.join(missing_vars)
        raise ValueError(f"必须设置以下环境变量：{missing_text}。请参考 .env.example 文件")

class Config:
    """基础配置类"""
    # 基础配置（是否强制校验由运行环境决定）
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # JWT配置
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)
    
    # 数据库配置
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD'),
        'database': os.environ.get('DB_NAME', 'movies_recommend'),
        'charset': 'utf8mb4'
    }
    
    # 连接池配置
    POOL_CONFIG = {
        'maxconnections': 10,
        'mincached': 2,
        'maxcached': 5,
        'maxshared': 3,
        'blocking': True,
        'maxusage': None,
        'setsession': [],
        'ping': 0
    }
    
    # 管理员验证码
    ADMIN_VERIFICATION_CODE = os.environ.get('ADMIN_VERIFICATION_CODE')
    
    # 默认密码（仅用于开发环境初始化）
    DEFAULT_PASSWORD = os.environ.get('DEFAULT_PASSWORD', '123456qwe')

    # 密码最小长度（登录/注册/改密统一策略）
    PASSWORD_MIN_LENGTH = int(os.environ.get('PASSWORD_MIN_LENGTH', 8))

class DevelopmentConfig(Config):
    """开发环境配置 - 使用默认值方便本地开发"""
    DEBUG = True
    
    # 开发环境允许使用默认值（但仍建议设置环境变量）
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-DO-NOT-USE-IN-PRODUCTION')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-jwt-secret-DO-NOT-USE-IN-PRODUCTION')
    
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD', 'root'),  # 开发环境默认密码
        'database': os.environ.get('DB_NAME', 'movies_recommend'),
        'charset': 'utf8mb4'
    }
    
    ADMIN_VERIFICATION_CODE = os.environ.get('ADMIN_VERIFICATION_CODE', 'admin123456')  # 开发环境默认验证码
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    """生产环境配置 - 必须设置所有环境变量"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    # 生产环境的必需配置在 create_app 阶段校验

# 配置字典，用于选择不同环境的配置
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
