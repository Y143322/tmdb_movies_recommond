"""
配置模块，包含应用程序的各种配置
"""
import os
import datetime

class Config:
    """基础配置类"""
    # ⚠️ 生产环境必须设置环境变量！
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("必须设置 SECRET_KEY 环境变量！请参考 .env.example 文件")
    
    PERMANENT_SESSION_LIFETIME = datetime.timedelta(days=7)
    
    # JWT配置
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')
    if not JWT_SECRET_KEY:
        raise ValueError("必须设置 JWT_SECRET_KEY 环境变量！请参考 .env.example 文件")
    
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = datetime.timedelta(days=30)
    
    # 数据库配置
    DB_CONFIG = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASSWORD'),  # 必须通过环境变量设置
        'database': os.environ.get('DB_NAME', 'movies_recommend'),
        'charset': 'utf8mb4'
    }
    
    # 验证数据库密码必须设置
    if not DB_CONFIG['password']:
        raise ValueError("必须设置 DB_PASSWORD 环境变量！请参考 .env.example 文件")
    
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
    
    # 管理员验证码 - 必须通过环境变量设置
    ADMIN_VERIFICATION_CODE = os.environ.get('ADMIN_VERIFICATION_CODE')
    if not ADMIN_VERIFICATION_CODE:
        raise ValueError("必须设置 ADMIN_VERIFICATION_CODE 环境变量！请参考 .env.example 文件")
    
    # 默认密码（仅用于开发环境初始化）
    DEFAULT_PASSWORD = os.environ.get('DEFAULT_PASSWORD', '123456qwe')

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

class ProductionConfig(Config):
    """生产环境配置 - 必须设置所有环境变量"""
    DEBUG = False
    # 生产环境的所有必需配置已在 Config 基类中验证

# 配置字典，用于选择不同环境的配置
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
