"""
日志模块，集中管理应用程序的日志配置
"""
import logging
import os
from logging.handlers import RotatingFileHandler

# 确保日志目录存在
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../archive/logs')
os.makedirs(log_dir, exist_ok=True)

# 应用日志文件路径
app_log_path = os.path.join(log_dir, 'app.log')
# 推荐系统日志文件路径
recommender_log_path = os.path.join(log_dir, 'recommender.log')
# 爬虫日志文件路径
scraper_log_path = os.path.join(log_dir, 'tmdb_scraper.log')

# 默认日志格式
DEFAULT_LOG_FORMAT = '%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s'

def get_logger(name, level=logging.INFO):
    """
    获取记录器
    
    Args:
        name (str): 记录器名称
        level (int, optional): 日志级别. 默认为 logging.INFO.
        
    Returns:
        logging.Logger: 日志记录器
    """
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 如果记录器已经有处理器，直接返回
    if logger.handlers:
        return logger
        
    # 设置日志级别
    logger.setLevel(level)
    
    # 日志文件路径
    log_file = os.path.join(log_dir, f'{name}.log')
    
    # 创建文件处理器
    file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
    file_handler.setLevel(level)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    # 设置格式
    formatter = logging.Formatter(DEFAULT_LOG_FORMAT)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 预先创建常用的日志记录器
app_logger = get_logger('app')
recommender_logger = get_logger('recommender')
scraper_logger = get_logger('tmdb_scraper')
movies_logger = get_logger('movies')

# 获取指定名称的日志记录器
def get_logger_from_existing(name):
    """获取指定名称的日志记录器

    Args:
        name (str): 日志记录器名称

    Returns:
        logging.Logger: 日志记录器
    """
    if name == 'app':
        return app_logger
    elif name == 'recommender':
        return recommender_logger
    elif name == 'tmdb_scraper':
        return scraper_logger
    else:
        return logging.getLogger(name)

if __name__ == "__main__":
    # 测试日志记录
    logger = get_logger("test")
    logger.debug("这是一条调试日志")
    logger.info("这是一条信息日志")
    logger.warning("这是一条警告日志")
    logger.error("这是一条错误日志")
    logger.critical("这是一条严重错误日志")
