#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TMDB电影数据爬虫
使用TMDB API获取电影数据并存入数据库
"""

import os
import sys
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import requests
import time
import pymysql
import threading
import json
from datetime import datetime
from requests.exceptions import RequestException

# 获取日志记录器
from movies_recommend.logger import get_logger

# 获取日志记录器并禁用日志传播，避免重复日志
logger = get_logger('tmdb_scraper')
logger.propagate = False

# TMDB API配置
API_KEY = os.environ.get("TMDB_API_KEY", "")
API_TOKEN = os.environ.get("TMDB_API_TOKEN", "")
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

from movies_recommend.extensions import get_db_connection

# 爬虫状态保存文件路径
SCRAPER_STATE_FILE = "archive/scraper_state.json"

# 确保存储目录存在
os.makedirs(os.path.dirname(SCRAPER_STATE_FILE), exist_ok=True)

# 全局变量，用于跟踪爬虫进度
scraper_progress = {
    "current": 0,
    "total": 100,
    "status": "idle",  # idle, running, completed, error
    "message": "",
    "last_page": 1,    # 上次爬取的页数
    "total_pages": 1,  # 总页数
    "last_movie_id": 0, # 上次爬取的电影ID
    "processed_movies": 0, # 已处理的电影数量
    "target_movies": 50000, # 目标电影数量
    "start_time": None, # 爬虫开始时间
    "end_time": None,   # 爬虫结束时间
    "endpoint": "movie/top_rated" # 爬取的API端点
}

# 全局变量，用于存储爬虫线程
scraper_thread = None
stop_scraper_flag = False # 新增：用于停止爬虫的标志

def stop_scraper_execution():
    """设置全局停止爬虫标志为True"""
    global stop_scraper_flag
    stop_scraper_flag = True
    logger.info("接收到停止爬虫信号，将尝试在下一个检查点停止。")
    return True

# 检查数据库中是否存在爬虫状态表，如果不存在则创建
def check_and_create_scraper_state_table():
    """检查爬虫状态表是否存在，但不修改表结构"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT DATABASE()")
        db_name_row = cursor.fetchone()
        db_name = db_name_row[0] if db_name_row and db_name_row[0] else 'movies_recommend'
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_name = %s
            """,
            (db_name, 'scraper_state')
        )
        
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            # 如果表不存在，创建完整表结构
            logger.info("爬虫状态表不存在，创建完整表结构")
            cursor.execute("""
                CREATE TABLE scraper_state (
                    id INT NOT NULL AUTO_INCREMENT,
                    status VARCHAR(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'idle',
                    current INT NOT NULL DEFAULT 0,
                    message TEXT COLLATE utf8mb4_unicode_ci NULL,
                    last_page INT DEFAULT 1,
                    total_pages INT DEFAULT 1,
                    last_movie_id INT DEFAULT 0,
                    processed_movies INT NOT NULL DEFAULT 0,
                    target_movies INT DEFAULT 50000,
                    start_time DATETIME DEFAULT NULL,
                    end_time DATETIME DEFAULT NULL,
                    endpoint VARCHAR(50) COLLATE utf8mb4_unicode_ci DEFAULT 'movie/top_rated',
                    created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            conn.commit()
            logger.info("爬虫状态表完整结构创建成功")
        else:
            # 表已存在，检查是否有记录
            logger.info("爬虫状态表已存在，检查是否有记录")
            cursor.execute("SELECT COUNT(*) FROM scraper_state")
            records_count = cursor.fetchone()[0]
            
            if records_count == 0:
                # 没有记录，添加一条初始记录
                logger.info("爬虫状态表为空，添加初始记录")
                try:
                    cursor.execute("""
                        INSERT INTO scraper_state 
                        (status, current, message, processed_movies, last_page, total_pages, 
                         last_movie_id, target_movies, endpoint)
                        VALUES ('idle', 0, '爬虫初始化', 0, 1, 1, 0, 50000, 'movie/top_rated')
                    """)
                    conn.commit()
                    logger.info("初始记录添加成功")
                except Exception as e:
                    logger.error(f"添加初始记录失败: {str(e)}")
                    conn.rollback()
            else:
                logger.info(f"爬虫状态表中已有 {records_count} 条记录")
        
        # 查询表结构，检查是否需要添加缺失列
        logger.debug("查询爬虫状态表结构")
        cursor.execute("SHOW COLUMNS FROM scraper_state")
        existing_columns = [col[0] for col in cursor.fetchall()]
        logger.debug(f"爬虫状态表现有列: {', '.join(existing_columns)}")
        
        # 需要的所有列
        required_columns = ['id', 'status', 'current', 'message', 'last_page', 'total_pages', 
                          'last_movie_id', 'processed_movies', 'target_movies', 'start_time', 
                          'end_time', 'endpoint', 'created_at', 'updated_at']
        
        # 检查是否缺少列
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        # 如果缺少列，添加这些列
        if missing_columns:
            logger.info(f"爬虫状态表缺少以下列: {', '.join(missing_columns)}")
            
            for column in missing_columns:
                try:
                    # 根据列名添加适当的列定义
                    if column == 'current':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN current INT NOT NULL DEFAULT 0")
                    elif column == 'status':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN status VARCHAR(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'idle'")
                    elif column == 'message':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN message TEXT COLLATE utf8mb4_unicode_ci NULL")
                    elif column == 'last_page':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN last_page INT DEFAULT 1")
                    elif column == 'total_pages':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN total_pages INT DEFAULT 1")
                    elif column == 'last_movie_id':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN last_movie_id INT DEFAULT 0")
                    elif column == 'processed_movies':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN processed_movies INT NOT NULL DEFAULT 0")
                    elif column == 'target_movies':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN target_movies INT DEFAULT 50000")
                    elif column == 'start_time':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN start_time DATETIME DEFAULT NULL")
                    elif column == 'end_time':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN end_time DATETIME DEFAULT NULL")
                    elif column == 'endpoint':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN endpoint VARCHAR(50) COLLATE utf8mb4_unicode_ci DEFAULT 'movie/top_rated'")
                    elif column == 'created_at':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN created_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP")
                    elif column == 'updated_at':
                        cursor.execute("ALTER TABLE scraper_state ADD COLUMN updated_at TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
                    
                    logger.info(f"成功添加列: {column}")
                except Exception as e:
                    logger.error(f"添加列 {column} 时出错: {str(e)}")
            
            conn.commit()
            logger.info("爬虫状态表结构更新完成")
        
        cursor.close()
        return True
    except Exception as e:
        logger.error(f"检查爬虫状态表时出错: {str(e)}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        if conn:
            conn.close()

# 保存爬虫状态到数据库
def save_scraper_state_to_db():
    """保存爬虫状态到数据库，适应现有表结构"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 首先获取表的实际列信息
        cursor.execute("SHOW COLUMNS FROM scraper_state")
        existing_columns = [col[0] for col in cursor.fetchall()]
        logger.debug(f"爬虫状态表现有列: {', '.join(existing_columns)}")
        
        # 检查是否有记录
        cursor.execute("SELECT id FROM scraper_state ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        
        # 根据现有表结构准备数据，只包含表中实际存在的列
        save_data = {}
        for field in ["status", "current", "message", "last_page", "total_pages", 
                      "last_movie_id", "processed_movies", "target_movies", "endpoint"]:
            if field in existing_columns and field in scraper_progress:
                save_data[field] = scraper_progress[field]
        
        # 处理时间字段，同样只包含表中实际存在的列
        for time_field in ["start_time", "end_time"]:
            if time_field in existing_columns and time_field in scraper_progress:
                time_value = scraper_progress[time_field]
                # 如果是字符串，尝试转换为datetime
                if isinstance(time_value, str):
                    try:
                        time_value = datetime.strptime(time_value, '%Y-%m-%d %H:%M:%S')
                    except (ValueError, TypeError):
                        time_value = None
                save_data[time_field] = time_value
        
        # 检查是否有可用数据
        if not save_data:
            logger.warning("没有可保存的数据或表结构不兼容")
            return False
        
        try:
            if result:
                # 更新现有记录
                record_id = result[0]
                
                # 构建SQL语句，只使用存在的字段
                update_fields = []
                update_values = []
                
                for field, value in save_data.items():
                    update_fields.append(f"{field} = %s")
                    update_values.append(value)
                
                if not update_fields:
                    logger.warning("没有可更新的字段")
                    return False
                
                # 添加WHERE条件
                update_values.append(record_id)
                
                # 执行更新
                update_sql = f"UPDATE scraper_state SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(update_sql, update_values)
                
                logger.info(f"更新爬虫状态记录 ID: {record_id}, 状态: {scraper_progress.get('status', 'unknown')}, 进度: {scraper_progress.get('current', 0)}%")
            else:
                # 插入新记录
                insert_fields = list(save_data.keys())
                placeholders = ["%s"] * len(insert_fields)
                insert_values = [save_data[field] for field in insert_fields]
                
                if not insert_fields:
                    logger.warning("没有可插入的字段")
                    return False
                
                insert_sql = f"INSERT INTO scraper_state ({', '.join(insert_fields)}) VALUES ({', '.join(placeholders)})"
                cursor.execute(insert_sql, insert_values)
                
                logger.info("创建新的爬虫状态记录")
            
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"保存爬虫状态到数据库失败: {str(e)}")
            
            # 尝试使用最小字段集保存
            try:
                # 确保最小字段集中的字段在表中存在
                minimal_fields = [field for field in ["status", "processed_movies"] if field in existing_columns]
                
                # 如果"current"列存在，添加到最小字段集
                if "current" in existing_columns:
                    minimal_fields.append("current")
                
                # 如果"last_page"列存在，添加到最小字段集
                if "last_page" in existing_columns:
                    minimal_fields.append("last_page")
                
                if not minimal_fields:
                    logger.error("没有可用的最小字段集")
                    return False
                
                minimal_values = [scraper_progress.get(field, 0) for field in minimal_fields]
                
                if result:
                    # 更新语句
                    update_sets = [f"{field} = %s" for field in minimal_fields]
                    minimal_values.append(result[0])  # ID for WHERE clause
                    cursor.execute(f"UPDATE scraper_state SET {', '.join(update_sets)} WHERE id = %s", minimal_values)
                else:
                    # 插入语句
                    cursor.execute(
                        f"INSERT INTO scraper_state ({', '.join(minimal_fields)}) VALUES ({', '.join(['%s'] * len(minimal_fields))})",
                        minimal_values
                    )
                
                conn.commit()
                logger.info("使用最小字段集保存爬虫状态成功")
                return True
            except Exception as e2:
                conn.rollback()
                logger.error(f"使用最小字段集保存爬虫状态也失败: {str(e2)}")
                return False
    except Exception as e:
        logger.error(f"连接数据库或查询记录失败: {str(e)}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        if conn:
            try:
                cursor.close()
                conn.close()
            except:
                pass

# 从数据库加载爬虫状态
def load_scraper_state_from_db():
    """从数据库加载爬虫状态"""
    conn = None
    try:
        # 先确保表存在
        check_and_create_scraper_state_table()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取表的实际列信息
        cursor.execute("SHOW COLUMNS FROM scraper_state")
        existing_columns = [col[0] for col in cursor.fetchall()]
        logger.debug(f"爬虫状态表现有列: {', '.join(existing_columns)}")
        
        # 需要查询的所有可能列
        possible_columns = [
            "status", "last_page", "total_pages", "last_movie_id", "processed_movies", 
            "target_movies", "start_time", "end_time", "endpoint"
        ]
        
        # 只选择表中实际存在的列
        select_columns = [col for col in possible_columns if col in existing_columns]
        
        if not select_columns:
            logger.warning("爬虫状态表没有足够的列，无法加载状态")
            return False
        
        # 构建动态SQL语句
        select_sql = f"SELECT {', '.join(select_columns)} FROM scraper_state ORDER BY id DESC LIMIT 1"
        cursor.execute(select_sql)
        
        result = cursor.fetchone()
        if result:
            # 将查询结果映射到对应的列
            for i, col in enumerate(select_columns):
                if col == "status":
                    scraper_progress["status"] = result[i]
                elif col == "last_page":
                    scraper_progress["last_page"] = result[i]
                elif col == "total_pages":
                    scraper_progress["total_pages"] = result[i]
                elif col == "last_movie_id":
                    scraper_progress["last_movie_id"] = result[i]
                elif col == "processed_movies":
                    scraper_progress["processed_movies"] = result[i]
                elif col == "target_movies":
                    scraper_progress["target_movies"] = result[i]
                elif col == "start_time":
                    scraper_progress["start_time"] = result[i]
                elif col == "end_time":
                    scraper_progress["end_time"] = result[i]
                elif col == "endpoint":
                    scraper_progress["endpoint"] = result[i]
            
            # 根据处理进度计算当前百分比
            if scraper_progress["target_movies"] > 0:
                # 计算进度百分比
                progress_percent = min(
                    int((scraper_progress["processed_movies"] / scraper_progress["target_movies"]) * 100), 
                    99
                )
                # 如果状态是running但处理电影数为0，设置为1%避免显示为0
                if scraper_progress["status"] == "running" and scraper_progress["processed_movies"] == 0:
                    progress_percent = 1
                
                scraper_progress["current"] = progress_percent
                
            # 设置默认消息
            if scraper_progress["status"] == "running":
                scraper_progress["message"] = f"已处理 {scraper_progress['processed_movies']} 部电影，当前页码 {scraper_progress['last_page']}"
            elif scraper_progress["status"] == "completed":
                scraper_progress["message"] = f"爬虫任务已完成，共处理 {scraper_progress['processed_movies']} 部电影"
            elif scraper_progress["status"] == "error":
                scraper_progress["message"] = "爬虫任务出错，请查看日志"
            else:
                scraper_progress["message"] = "爬虫已初始化"
            
            logger.info(f"从数据库加载爬虫状态: 上次爬取到第 {scraper_progress['last_page']} 页，已处理 {scraper_progress['processed_movies']} 部电影")
            return True
        else:
            logger.info("数据库中没有爬虫状态记录")
            return False
    except Exception as e:
        logger.error(f"从数据库加载爬虫状态时出错: {str(e)}")
        # 发生错误时尝试从文件加载
        logger.info("尝试从备份文件加载爬虫状态...")
        return load_scraper_state_from_file()
    finally:
        if conn:
            try:
                cursor.close()
                conn.close()
            except:
                pass

# 保存爬虫状态到文件（作为备份）
def save_scraper_state_to_file():
    """保存爬虫状态到文件"""
    try:
        with open(SCRAPER_STATE_FILE, 'w', encoding='utf-8') as f:
            # 将datetime对象转换为字符串
            state_copy = scraper_progress.copy()
            
            # 确保时间对象正确处理
            for time_field in ["start_time", "end_time"]:
                if time_field in state_copy and state_copy[time_field] is not None:
                    if isinstance(state_copy[time_field], datetime):
                        state_copy[time_field] = state_copy[time_field].strftime('%Y-%m-%d %H:%M:%S')
                    elif isinstance(state_copy[time_field], str):
                        # 已经是字符串，不需要转换
                        pass
                    else:
                        # 不是datetime也不是字符串，设为None
                        state_copy[time_field] = None
            
            json.dump(state_copy, f, ensure_ascii=False, indent=2)
        logger.info(f"爬虫状态已保存到文件: {SCRAPER_STATE_FILE}")
    except Exception as e:
        logger.error(f"保存爬虫状态到文件时出错: {str(e)}")
        # 错误不影响主流程，继续执行

# 从文件加载爬虫状态（作为备份）
def load_scraper_state_from_file():
    """从文件加载爬虫状态"""
    try:
        if os.path.exists(SCRAPER_STATE_FILE):
            with open(SCRAPER_STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
                
                # 将字符串转换回datetime对象，处理可能的格式错误
                for time_field in ["start_time", "end_time"]:
                    if time_field in state and state[time_field]:
                        try:
                            if isinstance(state[time_field], str):
                                state[time_field] = datetime.strptime(state[time_field], '%Y-%m-%d %H:%M:%S')
                        except (ValueError, TypeError) as e:
                            logger.warning(f"转换时间字段 {time_field} 失败: {str(e)}，设置为None")
                            state[time_field] = None
                
                # 更新全局状态
                scraper_progress.update(state)
                
                logger.info(f"从文件加载爬虫状态: 上次爬取到第 {state.get('last_page', 1)} 页，已处理 {state.get('processed_movies', 0)} 部电影")
                return True
        else:
            logger.info(f"爬虫状态文件不存在: {SCRAPER_STATE_FILE}")
            return False
    except Exception as e:
        logger.error(f"从文件加载爬虫状态时出错: {str(e)}")
        return False

# 检查电影是否已存在于数据库
def is_movie_exists_in_db(movie_id):
    """检查电影是否已存在于数据库"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM movies WHERE id = %s", (movie_id,))
        result = cursor.fetchone()
        
        exists = result is not None
        cursor.close()
        return exists
    except Exception as e:
        logger.error(f"检查电影ID: {movie_id} 是否存在时出错: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

# 检查电影信息是否完整
def is_movie_info_complete(movie_data):
    """检查电影信息是否完整

    Args:
        movie_data (dict): 电影数据

    Returns:
        bool: 电影信息是否完整
    """
    # 检查必要字段
    required_fields = ['id', 'title', 'original_title', 'release_date', 'vote_average']
    for field in required_fields:
        if field not in movie_data or movie_data[field] is None:
            logger.warning(f"电影ID: {movie_data.get('id', '未知')} 缺少必要字段: {field}")
            return False
            
    # 检查概述是否为空或太短
    if 'overview' not in movie_data or not movie_data.get('overview') or len(movie_data.get('overview', '')) < 10:
        logger.warning(f"电影ID: {movie_data.get('id', '未知')} 概述缺失或过短: {movie_data.get('overview', '无')}")
        return False
        
    # 检查海报路径是否存在
    if 'poster_path' not in movie_data or not movie_data.get('poster_path'):
        logger.warning(f"电影ID: {movie_data.get('id', '未知')} 海报路径缺失")
        return False
        
    # 检查电影类型是否存在
    if 'genres' not in movie_data or not movie_data.get('genres'):
        logger.warning(f"电影ID: {movie_data.get('id', '未知')} 电影类型缺失")
        return False
    
    # 检查电影评分是否合理
    if movie_data.get('vote_average', 0) <= 0 or movie_data.get('vote_average', 0) > 10:
        logger.warning(f"电影ID: {movie_data.get('id', '未知')} 评分不合理: {movie_data.get('vote_average', 0)}")
        return False
    
    # 检查制片国家或语言信息
    if ('production_countries' not in movie_data or not movie_data.get('production_countries')) and \
       ('production_companies' not in movie_data or not movie_data.get('production_companies')):
        logger.warning(f"电影ID: {movie_data.get('id', '未知')} 制片国家和制片公司均缺失")
        return False
    
    # 检查电影年份是否合理
    if 'release_date' in movie_data and movie_data['release_date']:
        try:
            release_date = movie_data['release_date']
            if hasattr(release_date, 'year'):
                # datetime对象
                year = release_date.year
            else:
                # 字符串
                year = int(str(release_date).split('-')[0])
            current_year = datetime.now().year
            if year < 1900 or year > current_year + 2:  # 允许最多未来两年的电影
                logger.warning(f"电影ID: {movie_data.get('id', '未知')} 上映年份不合理: {year}")
                return False
        except:
            # 日期格式错误
            logger.warning(f"电影ID: {movie_data.get('id', '未知')} 日期格式错误: {movie_data['release_date']}")
            return False
    
    logger.info(f"电影 ID: {movie_data.get('id', '未知')}, 标题: {movie_data.get('title', '未知')} 的信息完整")
    return True

# 获取进度
def get_progress():
    """获取当前爬虫进度"""
    # 复制一份爬虫进度，避免原始数据被修改
    progress = scraper_progress.copy()
    
    # 记录原始数据信息，便于调试
    logger.debug(f"原始爬虫进度数据: {progress}")
    
    # 将datetime对象转换为字符串，防止JSON序列化错误
    for key, value in progress.items():
        if isinstance(value, datetime):
            progress[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            logger.debug(f"转换datetime字段 {key}: {value} -> {progress[key]}")
    
    # 确保所有必需字段都存在
    required_fields = ["current", "status", "message", "processed_movies", "target_movies", 
                      "last_page", "total_pages", "last_movie_id"]
    
    for field in required_fields:
        if field not in progress:
            logger.warning(f"进度数据缺少必要字段: {field}，设置默认值")
            # 根据字段类型设置默认值
            if field in ["current", "processed_movies", "target_movies", "last_page", "total_pages", "last_movie_id"]:
                progress[field] = 0
            elif field == "status":
                progress[field] = "idle"
            else:
                progress[field] = ""
    
    # 确保数字字段为整数类型，避免前端解析问题
    int_fields = ["current", "processed_movies", "target_movies", "last_page", "total_pages", "last_movie_id"]
    for field in int_fields:
        if field in progress and progress[field] is not None:
            try:
                progress[field] = int(progress[field])
            except (ValueError, TypeError):
                logger.warning(f"字段 {field} 值 {progress[field]} 无法转换为整数，设为0")
                progress[field] = 0
    
    # 记录最终返回的数据，便于调试
    logger.info(f"返回爬虫进度: 状态={progress['status']}, 进度={progress['current']}%, 已处理={progress['processed_movies']}/{progress['target_movies']} 部电影")
    
    return progress


def reset_progress():
    """重置爬虫进度"""
    global scraper_progress
    scraper_progress = {
        "current": 0,
        "total": 100,
        "status": "idle",
        "message": "",
        "last_page": 1,
        "total_pages": 1,
        "last_movie_id": 0,
        "processed_movies": 0,
        "target_movies": 50000,
        "start_time": None,
        "end_time": None,
        "endpoint": "movie/top_rated"
    }
    logger.info("爬虫进度已重置")


def update_progress(current=None, status=None, message=None, last_page=None, last_movie_id=None, processed_movies=None):
    """更新爬虫进度"""
    global scraper_progress
    
    # 记录更新前的状态
    old_status = scraper_progress.get("status")
    old_current = scraper_progress.get("current")
    old_processed = scraper_progress.get("processed_movies")
    
    # 更新各个字段
    if current is not None:
        # 确保current是一个整数，并且在0-100之间
        scraper_progress["current"] = max(0, min(100, int(current)))
    if status is not None:
        scraper_progress["status"] = status
    if message is not None:
        scraper_progress["message"] = message
    if last_page is not None:
        scraper_progress["last_page"] = last_page
    if last_movie_id is not None:
        scraper_progress["last_movie_id"] = last_movie_id
    if processed_movies is not None:
        scraper_progress["processed_movies"] = processed_movies
        
    # 如果状态变为running且原来不是running，记录开始时间
    if status == "running" and old_status != "running":
        scraper_progress["start_time"] = datetime.now()
        logger.info(f"爬虫状态从 {old_status} 变更为 running，记录开始时间: {scraper_progress['start_time']}")
        
    # 如果状态变为completed或error，记录结束时间
    if status in ["completed", "error"] and old_status not in ["completed", "error"]:
        scraper_progress["end_time"] = datetime.now()
        logger.info(f"爬虫状态从 {old_status} 变更为 {status}，记录结束时间: {scraper_progress['end_time']}")
        
    # 记录状态变化日志
    if (status is not None and status != old_status) or \
       (current is not None and current != old_current) or \
       (processed_movies is not None and processed_movies != old_processed) or \
       message is not None:
        logger.info(
            f"爬虫进度更新: {scraper_progress['current']}%, 状态: {scraper_progress['status']}, " +
            f"已处理: {scraper_progress['processed_movies']}/{scraper_progress['target_movies']} 部电影, " +
            f"消息: {scraper_progress['message']}"
        )
        
    # 尝试保存状态到数据库，但不中止爬虫进程
    try:
        # 只保存状态到数据库，不再保存到文件
        db_save_result = save_scraper_state_to_db()
        if not db_save_result:
            logger.warning("保存爬虫状态到数据库失败，但爬虫会继续运行")
    except Exception as e:
        logger.error(f"更新爬虫进度时出错: {str(e)}，但爬虫会继续运行")
    
    # 不再每次都保存到文件，避免文件操作错误
    # save_scraper_state_to_file()


def get_db_connection():
    """获取数据库连接"""
    try:
        conn = pymysql.connect(**DB_CONFIG)
        logger.info("数据库连接成功")
        return conn
    except pymysql.MySQLError as e:
        logger.error(f"数据库连接失败: {str(e)}")
        update_progress(status="error", message=f"数据库连接失败: {str(e)}")
        raise


def make_api_request(endpoint, params=None, max_retries=3, timeout=30):
    """
    向TMDB API发送请求

    Args:
        endpoint (str): API端点，不包含基础URL
        params (dict, optional): 请求参数
        max_retries (int): 最大重试次数
        timeout (int): 请求超时时间（秒）

    Returns:
        dict: API响应JSON数据
    """
    url = f"{BASE_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json;charset=utf-8",
        "accept": "application/json"
    }

    if params is None:
        params = {}

    # 添加语言参数，获取中文数据
    if 'language' not in params:
        params['language'] = 'zh-CN'

    # 添加API密钥
    params['api_key'] = API_KEY

    retries = 0
    while retries < max_retries:
        try:
            logger.info(f"发送API请求: {url}, 参数: {params}, 重试次数: {retries}")
            response = requests.get(
                url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()  # 如果响应状态码不是200，抛出异常
            return response.json()
        except RequestException as e:
            logger.error(f"API请求失败: {url}, 错误: {str(e)}")
            # 如果是请求限制错误，等待并重试
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"响应状态码: {e.response.status_code}")
                logger.error(f"响应内容: {e.response.text}")
                if e.response.status_code == 429:
                    retry_after = int(e.response.headers.get('Retry-After', 1))
                    logger.warning(f"达到请求限制，等待 {retry_after} 秒后重试")
                    time.sleep(retry_after)
                    continue  # 直接进入下一次循环重试

            # 其他错误，增加重试次数
            retries += 1
            wait_time = 2 ** retries  # 指数退避策略
            logger.warning(f"请求失败，{wait_time}秒后进行第{retries}次重试")
            time.sleep(wait_time)

            # 如果已经达到最大重试次数，抛出异常
            if retries >= max_retries:
                logger.error(f"达到最大重试次数({max_retries})，请求失败")
                raise
        except Exception as e:
            logger.error(f"发生未预期的错误: {str(e)}")
            retries += 1
            if retries >= max_retries:
                logger.error(f"达到最大重试次数({max_retries})，请求失败")
                raise


def save_genres(genres):
    """保存电影类型到内存中，不再保存到数据库"""
    # 直接返回类型列表，作为内存中的引用
    all_genres = [(genre['id'], genre['name']) for genre in genres]
    logger.info(f"处理了 {len(all_genres)} 个电影类型")
    return all_genres


def save_movie(conn, movie_data):
    """保存电影基本信息到数据库"""
    cursor = conn.cursor()
    try:
        # 检查电影是否已存在
        cursor.execute("SELECT id FROM movies WHERE id = %s",
                       (movie_data['id'],))
        movie_exists = cursor.fetchone() is not None

        # 如果电影存在，先获取电影的现有数据
        existing_data = {}
        if movie_exists:
            # 获取现有电影数据
            cursor.execute("""
                SELECT id, title, original_title, overview, poster_path, backdrop_path,
                release_date, popularity, vote_average, vote_count, original_language, genres
                FROM movies WHERE id = %s
            """, (movie_data['id'],))
            movie_row = cursor.fetchone()
            if movie_row:
                # 将现有数据存储到字典中
                columns = [
                    'id', 'title', 'original_title', 'overview', 'poster_path', 'backdrop_path',
                    'release_date', 'popularity', 'vote_average', 'vote_count', 'original_language', 'genres'
                ]
                existing_data = dict(zip(columns, movie_row))
                logger.info(f"获取到电影 ID: {movie_data['id']} 的现有数据")

        # 处理日期，如果为空则设为NULL
        release_date = movie_data.get('release_date')
        if not release_date or release_date == '':
            release_date = None

        # 处理电影类型数据，将其转换为字符串
        genres_str = ''
        if 'genres' in movie_data and movie_data['genres']:
            # 提取类型名称并用逗号连接
            genres_str = ', '.join([genre['name']
                                   for genre in movie_data['genres']])

        # 准备要更新的电影数据
        if movie_exists:
            # 使用UPDATE而不是REPLACE，更新电影基本信息
            cursor.execute("""
                UPDATE movies SET
                    title = %s,
                    original_title = %s,
                    overview = %s,
                    poster_path = %s,
                    backdrop_path = %s,
                    release_date = %s,
                    popularity = %s,
                    vote_average = %s,
                    vote_count = %s,
                    original_language = %s,
                    genres = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (
                movie_data['title'],
                movie_data['original_title'],
                movie_data.get('overview', ''),
                movie_data.get('poster_path', ''),
                movie_data.get('backdrop_path', ''),
                release_date,
                movie_data.get('popularity', 0),
                movie_data.get('vote_average', 0),
                movie_data.get('vote_count', 0),
                movie_data.get('original_language', ''),
                genres_str,
                movie_data['id']
            ))
            logger.info(
                f"更新电影 '{movie_data['title']}' (ID: {movie_data['id']}) 成功，保留用户评分数据")
        else:
            # 如果电影不存在，则插入新记录
            cursor.execute("""
                INSERT INTO movies (
                    id, title, original_title, overview, poster_path, backdrop_path,
                    release_date, popularity, vote_average, vote_count, original_language, genres
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                movie_data['id'],
                movie_data['title'],
                movie_data['original_title'],
                movie_data.get('overview', ''),
                movie_data.get('poster_path', ''),
                movie_data.get('backdrop_path', ''),
                release_date,
                movie_data.get('popularity', 0),
                movie_data.get('vote_average', 0),
                movie_data.get('vote_count', 0),
                movie_data.get('original_language', ''),
                genres_str
            ))
            logger.info(
                f"插入新电影 '{movie_data['title']}' (ID: {movie_data['id']}) 成功")

        # 3. 处理制作公司
        if 'production_companies' in movie_data and movie_data['production_companies']:
            for company in movie_data['production_companies']:
                cursor.execute(
                    "REPLACE INTO production_companies (id, name, logo_path, origin_country) VALUES (%s, %s, %s, %s)",
                    (
                        company['id'],
                        company['name'],
                        company.get('logo_path', ''),
                        company.get('origin_country', '')
                    )
                )

                # 删除现有关联，然后重新添加
                cursor.execute("DELETE FROM movie_production_companies WHERE movie_id = %s AND company_id = %s",
                               (movie_data['id'], company['id']))
                cursor.execute(
                    "INSERT INTO movie_production_companies (movie_id, company_id) VALUES (%s, %s)",
                    (movie_data['id'], company['id'])
                )

        # 4. 处理制作国家 - 先清除现有关联，再添加新的
        cursor.execute(
            "DELETE FROM movie_production_countries WHERE movie_id = %s", (movie_data['id'],))

        # 限制每部电影的最大制作国家数量
        MAX_COUNTRIES = 2
        countries_added = 0

        if 'production_countries' in movie_data and movie_data['production_countries']:
            for country in movie_data['production_countries']:
                # 检查是否达到最大数量
                if countries_added >= MAX_COUNTRIES:
                    break

                try:
                    cursor.execute(
                        "REPLACE INTO production_countries (iso_3166_1, name) VALUES (%s, %s)",
                        (country['iso_3166_1'], country['name'])
                    )

                    cursor.execute(
                        "INSERT INTO movie_production_countries (movie_id, country_iso) VALUES (%s, %s)",
                        (movie_data['id'], country['iso_3166_1'])
                    )
                    countries_added += 1
                except Exception as e:
                    logger.error(
                        f"保存电影 ID: {movie_data['id']} 的制作国家 {country.get('name', 'unknown')} 时出错: {str(e)}")
                    # 继续处理其他国家

        # 4.1 从发行信息中提取额外的国家信息
        if countries_added < MAX_COUNTRIES and 'release_dates' in movie_data and 'results' in movie_data['release_dates']:
            for country_info in movie_data['release_dates']['results']:
                # 检查是否达到最大数量
                if countries_added >= MAX_COUNTRIES:
                    break

                try:
                    if 'iso_3166_1' in country_info and country_info['iso_3166_1']:
                        country_code = country_info['iso_3166_1']
                        country_name = country_code  # 使用ISO代码作为名称

                        # 检查该国家是否已经添加
                        cursor.execute(
                            "SELECT 1 FROM movie_production_countries WHERE movie_id = %s AND country_iso = %s",
                            (movie_data['id'], country_code)
                        )
                        if cursor.fetchone():
                            continue

                        cursor.execute(
                            "REPLACE INTO production_countries (iso_3166_1, name) VALUES (%s, %s)",
                            (country_code, country_name)
                        )

                        cursor.execute(
                            "INSERT INTO movie_production_countries (movie_id, country_iso) VALUES (%s, %s)",
                            (movie_data['id'], country_code)
                        )
                        countries_added += 1
                except Exception as e:
                    logger.error(
                        f"从发行信息中保存电影 ID: {movie_data['id']} 的制作国家时出错: {str(e)}")

        # 5. 处理语言 - 只保留原始语言
        # 首先清除所有现有的语言关联，确保只有一种原始语言
        try:
            cursor.execute(
                "DELETE FROM movie_spoken_languages WHERE movie_id = %s",
                (movie_data['id'],)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"清除电影 ID: {movie_data['id']} 的语言关联时出错: {str(e)}")

        # 确保原始语言是唯一的语言
        if 'original_language' in movie_data and movie_data['original_language']:
            original_lang = movie_data['original_language']
            try:
                # 添加原始语言到语言表
                cursor.execute(
                    "REPLACE INTO spoken_languages (iso_639_1, name) VALUES (%s, %s)",
                    (original_lang, original_lang)
                )

                # 添加电影-语言关联
                cursor.execute(
                    "INSERT INTO movie_spoken_languages (movie_id, language_iso) VALUES (%s, %s)",
                    (movie_data['id'], original_lang)
                )
            except Exception as e:
                logger.error(f"保存电影 ID: {movie_data['id']} 的原始语言时出错: {str(e)}")
        else:
            logger.warning(f"电影 ID: {movie_data['id']} 没有原始语言信息")

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        logger.error(
            f"保存电影 '{movie_data['title']}' (ID: {movie_data['id']}) 时出错: {str(e)}")
        return False
    finally:
        cursor.close()


def save_movie_credits(conn, movie_id, credits):
    """保存电影演职员信息"""
    if not credits:
        logger.info(f"电影 ID: {movie_id} 没有演职员数据")
        return True

    cursor = conn.cursor()
    try:
        # 检查电影是否已有导演记录
        existing_directors = []
        try:
            cursor.execute("""
                SELECT mc.person_id, p.name, mc.job
                FROM movie_crew mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s AND (mc.job = 'Director' OR mc.job LIKE 'Director %%')
            """, (movie_id,))
            existing_directors = cursor.fetchall()
            if existing_directors:
                logger.info(
                    f"电影 ID: {movie_id} 已有 {len(existing_directors)} 个导演记录")
        except Exception as e:
            logger.error(f"查询电影 ID: {movie_id} 的现有导演记录时出错: {str(e)}")

        # 检查是否有导演信息，并限制最多两名导演
        has_director = len(existing_directors) > 0
        directors = []

        # 如果已有导演记录，则不需要再添加新的导演
        if not has_director and 'crew' in credits and credits['crew']:
            # 获取所有导演，并按受欢迎程度排序
            all_directors = [crew for crew in credits['crew']
                if crew.get('job') == 'Director']
            if all_directors:
                # 按受欢迎程度排序，取前两名
                all_directors.sort(key=lambda x: x.get(
                    'popularity', 0), reverse=True)
                directors = all_directors[:2]  # 最多取两名导演
                has_director = True

        if not has_director:
            logger.warning(f"电影 ID: {movie_id} 的演职员数据中没有导演信息")
            # 如果没有导演信息，尝试从导演部门找人
            if 'crew' in credits and credits['crew']:
                directing_crew = [crew for crew in credits['crew']
                    if crew.get('department') == 'Directing']
                if directing_crew:
                    # 按受欢迎程度排序
                    directing_crew.sort(key=lambda x: x.get(
                        'popularity', 0), reverse=True)
                    logger.info(
                        f"从导演部门找到电影 ID: {movie_id} 的可能导演: {directing_crew[0]['name']}")
                    # 将第一个导演部门的人设为导演
                    director = directing_crew[0].copy()
                    director['job'] = 'Director'
                    directors.append(director)
                    has_director = True
                else:
                    # 如果没有导演部门的人，尝试从制作人员中找出可能的导演
                    producers = [crew for crew in credits['crew'] if crew.get(
                        'job') in ['Producer', 'Executive Producer']]
                    if producers:
                        # 按受欢迎程度排序
                        producers.sort(key=lambda x: x.get(
                            'popularity', 0), reverse=True)
                        logger.info(
                            f"从制作人员中找到电影 ID: {movie_id} 的可能导演: {producers[0]['name']}")
                        # 创建一个副本，修改为导演
                        director = producers[0].copy()
                        director['job'] = 'Director'
                        director['department'] = 'Directing'
                        directors.append(director)
                        has_director = True

        # 1. 处理演员
        if 'cast' in credits and credits['cast']:
            for cast_member in credits['cast']:
                # 保存演员基础信息
                cursor.execute("""
                    REPLACE INTO persons (id, name, gender, popularity)
                    VALUES (%s, %s, %s, %s)
                """, (
                    cast_member['id'],
                    cast_member['name'],
                    cast_member.get('gender', 0),
                    cast_member.get('popularity', 0)
                ))

                # 保存电影-演员关联
                cursor.execute("""
                    REPLACE INTO movie_cast (movie_id, person_id, role_name, cast_order)
                    VALUES (%s, %s, %s, %s)
                """, (
                    movie_id,
                    cast_member['id'],
                    cast_member.get('character', ''),
                    cast_member.get('order', 0)
                ))

        # 2. 处理剧组成员
        if 'crew' in credits and credits['crew']:
            # 只有在没有现有导演记录时才添加新的导演
            if not existing_directors and directors:
                # 减少日志输出，只在调试时记录
                # logger.info(f"电影 ID: {movie_id} 有 {len(directors)} 个导演: {', '.join([d['name'] for d in directors])}")

                # 处理导演信息
                for idx, director in enumerate(directors):
                    # 保存导演基础信息
                    cursor.execute("""
                        REPLACE INTO persons (id, name, gender, popularity)
                        VALUES (%s, %s, %s, %s)
                    """, (
                        director['id'],
                        director['name'],
                        director.get('gender', 0),
                        director.get('popularity', 0)
                    ))

                    # 保存电影-导演关联
                    try:
                        # 如果有多个导演，为了避免主键冲突，使用不同的job值
                        job_name = 'Director' if idx == 0 else f'Director {idx+1}'
                        cursor.execute("""
                            INSERT INTO movie_crew (movie_id, person_id, job, department)
                            VALUES (%s, %s, %s, %s)
                        """, (
                            movie_id,
                            director['id'],
                            job_name,
                            'Directing'
                        ))
                        logger.info(f"为电影 ID: {movie_id} 添加新导演 {director['name']} (职位: {job_name})")
                    except Exception as e:
                        logger.error(f"保存电影 ID: {movie_id} 的导演 {director['name']} 时出错: {str(e)}")

            # 处理其他剧组成员
            for crew_member in credits['crew']:
                # 跳过所有导演职位，避免覆盖现有导演记录
                if crew_member.get('job') == 'Director' or crew_member.get('job', '').startswith('Director ') or crew_member in directors:
                    continue

                # 保存剧组成员基础信息
                cursor.execute("""
                    REPLACE INTO persons (id, name, gender, popularity)
                    VALUES (%s, %s, %s, %s)
                """, (
                    crew_member['id'],
                    crew_member['name'],
                    crew_member.get('gender', 0),
                    crew_member.get('popularity', 0)
                ))

                # 保存电影-剧组成员关联
                cursor.execute("""
                    REPLACE INTO movie_crew (movie_id, person_id, job, department)
                    VALUES (%s, %s, %s, %s)
                """, (
                    movie_id,
                    crew_member['id'],
                    crew_member.get('job', ''),
                    crew_member.get('department', '')
                ))

        conn.commit()
        # 减少日志输出，只在调试时记录
        # logger.info(f"保存电影 ID: {movie_id} 的演职员信息成功")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"保存电影 ID: {movie_id} 的演职员信息时出错: {str(e)}")
        return False
    finally:
        cursor.close()

def save_movie_keywords(conn, movie_id, keywords_data):
    """保存电影关键词信息"""
    if not keywords_data or 'keywords' not in keywords_data or not keywords_data['keywords']:
        logger.info(f"电影 ID: {movie_id} 没有关键词数据")
        return True

    cursor = conn.cursor()
    try:
        for keyword in keywords_data['keywords']:
            # 保存关键词
            cursor.execute(
                "REPLACE INTO keywords (id, name) VALUES (%s, %s)",
                (keyword['id'], keyword['name'])
            )

            # 保存电影-关键词关联
            cursor.execute(
                "REPLACE INTO movie_keywords (movie_id, keyword_id) VALUES (%s, %s)",
                (movie_id, keyword['id'])
            )

        conn.commit()
        # 减少日志输出，只在调试时记录
        # logger.info(f"保存电影 ID: {movie_id} 的关键词信息成功，共 {len(keywords_data['keywords'])} 个关键词")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"保存电影 ID: {movie_id} 的关键词信息时出错: {str(e)}")
        return False
    finally:
        cursor.close()

def fetch_and_save_movie_details(movie_id, all_genres=None, max_retries=3):
    """获取并保存单个电影的详细信息"""
    retries = 0
    while retries < max_retries:
        try:
            # 1. 获取电影详情
            logger.info(f"获取电影 ID: {movie_id} 的详细信息 (尝试 {retries+1}/{max_retries})")
            # 增加请求参数，确保获取全面的电影信息
            movie_details = make_api_request(f"movie/{movie_id}", {
                "append_to_response": "credits,keywords,production_companies,production_countries,spoken_languages,release_dates,translations",
                "include_image_language": "zh,null",
                "include_adult": "false",
                "language": "zh-CN"
            }, max_retries=2, timeout=30)
            
            # 首先检查API响应是否有效
            if not movie_details:
                logger.error(f"电影 ID: {movie_id} 的API响应为空或无效")
                retries += 1
                continue
                
            # 检查必要字段
            required_fields = ['id', 'title']
            missing_fields = [field for field in required_fields if field not in movie_details]
            if missing_fields:
                logger.error(f"电影 ID: {movie_id} 的API响应缺少必要字段: {', '.join(missing_fields)}")
                retries += 1
                continue
            
            # 检查中文数据是否完整，特别是概述(overview)
            zh_overview_empty = not movie_details.get('overview') or movie_details.get('overview') == ''
            
            # 如果中文API没有返回完整信息，获取英文版本
            english_details = None
            if zh_overview_empty or not movie_details.get('production_countries') or not movie_details.get('spoken_languages'):
                logger.info(f"中文API未返回完整信息，尝试英文API获取电影 ID: {movie_id} 的信息")
                english_details = make_api_request(f"movie/{movie_id}", {
                    "append_to_response": "credits,keywords,production_companies,production_countries,spoken_languages,release_dates,translations",
                    "include_image_language": "en,null",
                    "include_adult": "false",
                    "language": "en-US"
                }, max_retries=2, timeout=30)
                
                # 处理概述(overview)特殊情况
                if zh_overview_empty and english_details and english_details.get('overview'):
                    logger.info(f"电影 ID: {movie_id} 使用英文概述替代空的中文概述")
                    movie_details['overview'] = english_details.get('overview')
                
                # 合并其他信息
                if not movie_details.get('production_countries') and english_details.get('production_countries'):
                    movie_details['production_countries'] = english_details['production_countries']
                    logger.info(f"从英文API获取到电影 ID: {movie_id} 的制作国家信息")

                if not movie_details.get('spoken_languages') and english_details.get('spoken_languages'):
                    movie_details['spoken_languages'] = english_details['spoken_languages']
                    logger.info(f"从英文API获取到电影 ID: {movie_id} 的语言信息")

                # 合并发行日期和翻译信息
                if not movie_details.get('release_dates') and english_details.get('release_dates'):
                    movie_details['release_dates'] = english_details['release_dates']

                if not movie_details.get('translations') and english_details.get('translations'):
                    movie_details['translations'] = english_details['translations']
            
            # 如果仍然没有概述，尝试从translations中查找完整信息
            if (not movie_details.get('overview') or movie_details.get('overview') == '') and 'translations' in movie_details and 'translations' in movie_details['translations']:
                translations = movie_details['translations']['translations']
                
                # 首先查找中文翻译
                for translation in translations:
                    if translation.get('iso_639_1') == 'zh' and translation.get('data', {}).get('overview'):
                        movie_details['overview'] = translation['data']['overview']
                        logger.info(f"从中文翻译中获取到电影 ID: {movie_id} 的概述")
                        break
                
                # 如果没有找到中文翻译，尝试英文
                if not movie_details.get('overview') or movie_details.get('overview') == '':
                    for translation in translations:
                        if translation.get('iso_639_1') == 'en' and translation.get('data', {}).get('overview'):
                            movie_details['overview'] = translation['data']['overview']
                            logger.info(f"从英文翻译中获取到电影 ID: {movie_id} 的概述")
                            break
            
            # 记录最终结果
            if not movie_details.get('overview') or movie_details.get('overview') == '':
                logger.warning(f"电影 ID: {movie_id} 最终没有获取到概述信息")
            else:
                # 截取概述的前50个字符用于日志
                overview_preview = movie_details.get('overview', '')[:50] + ('...' if len(movie_details.get('overview', '')) > 50 else '')
                logger.info(f"电影 ID: {movie_id} 成功获取概述: {overview_preview}")

            # 检查电影类型数据
            if 'genres' not in movie_details or not movie_details['genres']:
                logger.warning(f"电影 ID: {movie_id} 没有类型数据")

                # 尝试单独获取电影类型数据
                try:
                    genre_data = make_api_request(f"movie/{movie_id}", {"language": "zh-CN"}, max_retries=2, timeout=15)
                    if 'genres' in genre_data and genre_data['genres']:
                        logger.info(f"单独获取到电影 ID: {movie_id} 的类型数据")
                        movie_details['genres'] = genre_data['genres']
                    else:
                        # 如果仍然没有类型数据，尝试从关键词获取
                        keywords_data = make_api_request(f"movie/{movie_id}/keywords", max_retries=2, timeout=15)
                        if 'keywords' in keywords_data and keywords_data['keywords']:
                            logger.info(f"从关键词中获取到电影 ID: {movie_id} 的类型数据")
                            # 将关键词作为类型数据
                            # 使用关键词的ID作为类型的ID，确保不会与现有类型冲突
                            # 关键词的ID通常很大，我们使用取模操作确保在合理范围内
                            movie_details['genres'] = [{'id': (kw['id'] % 900) + 100, 'name': kw['name']} for kw in keywords_data['keywords'][:5]]
                except Exception as e:
                    logger.error(f"获取电影 ID: {movie_id} 的类型或关键词数据时出错: {str(e)}")

                # 如果仍然没有类型数据，使用随机类型
                if ('genres' not in movie_details or not movie_details['genres']) and all_genres:
                    import random
                    # 随机选择2-4个类型
                    num_genres = random.randint(2, 4)
                    # 确保有足够的类型可供选择
                    if len(all_genres) > 0:
                        selected_genres = random.sample(all_genres, min(num_genres, len(all_genres)))
                        movie_details['genres'] = [{'id': genre[0], 'name': genre[1]} for genre in selected_genres]
                        logger.info(f"为电影 ID: {movie_id} 随机分配了 {len(selected_genres)} 个类型")
                    else:
                        # 如果没有类型可选，创建一些默认类型
                        default_genres = [
                            {'id': 28, 'name': '动作'},
                            {'id': 12, 'name': '冒险'},
                            {'id': 16, 'name': '动画'},
                            {'id': 35, 'name': '喜剧'},
                            {'id': 80, 'name': '犯罪'},
                            {'id': 18, 'name': '剧情'},
                            {'id': 10751, 'name': '家庭'},
                            {'id': 14, 'name': '奇幻'},
                            {'id': 36, 'name': '历史'},
                            {'id': 27, 'name': '恐怖'},
                            {'id': 10402, 'name': '音乐'},
                            {'id': 9648, 'name': '悬疑'},
                            {'id': 10749, 'name': '爱情'},
                            {'id': 878, 'name': '科幻'},
                            {'id': 10770, 'name': '电视电影'},
                            {'id': 53, 'name': '惊悚'},
                            {'id': 10752, 'name': '战争'},
                            {'id': 37, 'name': '西部'}
                        ]
                        selected_genres = random.sample(default_genres, min(num_genres, len(default_genres)))
                        movie_details['genres'] = selected_genres
                        logger.info(f"为电影 ID: {movie_id} 随机分配了 {len(selected_genres)} 个默认类型")
            
            # 检查电影信息是否完整
            if not is_movie_info_complete(movie_details):
                logger.warning(f"电影 ID: {movie_id} 信息不完整，跳过保存")
                # 详细记录电影信息不完整的原因
                missing_info = []
                required_fields = ['id', 'title', 'original_title', 'release_date', 'vote_average']
                for field in required_fields:
                    if field not in movie_details or movie_details[field] is None:
                        missing_info.append(f"缺少 {field}")
                
                if 'overview' not in movie_details or not movie_details.get('overview') or len(movie_details.get('overview', '')) < 10:
                    missing_info.append("概述缺失或过短")
                
                if 'poster_path' not in movie_details or not movie_details.get('poster_path'):
                    missing_info.append("海报路径缺失")
                
                if 'genres' not in movie_details or not movie_details.get('genres'):
                    missing_info.append("电影类型缺失")
                
                if movie_details.get('vote_average', 0) <= 0 or movie_details.get('vote_average', 0) > 10:
                    missing_info.append(f"评分不合理: {movie_details.get('vote_average', 0)}")
                
                logger.error(f"电影 ID: {movie_id} 信息不完整的具体原因: {', '.join(missing_info)}")
                
                # 尝试下一次重试
                retries += 1
                if retries >= max_retries:
                    logger.error(f"达到最大重试次数({max_retries})，电影 ID: {movie_id} 信息仍不完整")
                    return False
                
                wait_time = 2 ** retries
                logger.warning(f"信息不完整，{wait_time}秒后进行第{retries}次重试")
                time.sleep(wait_time)
                continue

            # 2. 保存到数据库
            conn = None
            try:
                conn = get_db_connection()
                # 保存电影基本信息
                movie_saved = save_movie(conn, movie_details)
                if not movie_saved:
                    logger.warning(f"电影 ID: {movie_id} 基本信息保存失败，跳过相关数据")
                    return False

                # 保存演职员信息
                credits_saved = True
                if 'credits' in movie_details:
                    try:
                        # 检查是否有导演信息
                        has_director = False
                        if 'crew' in movie_details['credits']:
                            directors = [crew for crew in movie_details['credits']['crew'] if crew.get('job') == 'Director']
                            has_director = len(directors) > 0

                        if not has_director:
                            logger.warning(f"电影 ID: {movie_id} 没有导演信息，尝试单独获取")
                            # 尝试单独获取电影演职员信息
                            try:
                                # 尝试不同的语言参数
                                for lang in ['zh-CN', 'en-US', None]:
                                    params = {"language": lang} if lang else {}
                                    credits_data = make_api_request(f"movie/{movie_id}/credits", params, max_retries=2, timeout=15)
                                    if credits_data and 'crew' in credits_data:
                                        # 查找导演
                                        directors = [crew for crew in credits_data['crew'] if crew.get('job') == 'Director']
                                        if directors:
                                            logger.info(f"成功获取电影 ID: {movie_id} 的导演信息: {', '.join([d['name'] for d in directors])}")
                                            # 将新获取的导演信息添加到原始数据中
                                            if 'crew' not in movie_details['credits']:
                                                movie_details['credits']['crew'] = []
                                            movie_details['credits']['crew'].extend(directors)
                                            break  # 找到导演后跳出循环

                                # 如果仍然没有导演信息，尝试从导演部门找人
                                if not has_director and 'crew' in movie_details['credits']:
                                    directing_crew = [crew for crew in movie_details['credits']['crew'] if crew.get('department') == 'Directing']
                                    if directing_crew:
                                        logger.info(f"从导演部门找到电影 ID: {movie_id} 的可能导演: {directing_crew[0]['name']}")
                                        # 创建一个副本，将第一个导演部门的人设为导演
                                        director = directing_crew[0].copy()
                                        director['job'] = 'Director'
                                        director['department'] = 'Directing'  # 确保设置部门
                                        movie_details['credits']['crew'].append(director)
                                        has_director = True
                                        logger.info(f"已将导演部门人员 {director['name']} 添加为电影 ID: {movie_id} 的导演")
                                    else:
                                        logger.warning(f"电影 ID: {movie_id} 没有导演部门的人员")

                                        # 尝试从制作人员中找出可能的导演
                                        producers = [crew for crew in movie_details['credits']['crew'] if crew.get('job') in ['Producer', 'Executive Producer']]
                                        if producers:
                                            logger.info(f"从制作人员中找到电影 ID: {movie_id} 的可能导演: {producers[0]['name']}")
                                            # 创建一个副本，修改为导演
                                            director_copy = producers[0].copy()
                                            director_copy['job'] = 'Director'
                                            director_copy['department'] = 'Directing'
                                            movie_details['credits']['crew'].append(director_copy)
                                            has_director = True
                                            logger.info(f"已将制作人员 {director_copy['name']} 添加为电影 ID: {movie_id} 的导演")
                            except Exception as e:
                                logger.error(f"单独获取电影 ID: {movie_id} 的演职员信息时出错: {str(e)}")

                        # 保存演职员信息
                        credits_saved = save_movie_credits(conn, movie_id, movie_details['credits'])
                        if not credits_saved:
                            logger.error(f"电影 ID: {movie_id} 的演职员信息保存失败")
                    except Exception as e:
                        logger.error(f"保存电影 ID: {movie_id} 的演职员信息时出错: {str(e)}")
                        credits_saved = False

                # 保存关键词信息
                keywords_saved = True
                if 'keywords' in movie_details:
                    try:
                        keywords_saved = save_movie_keywords(conn, movie_id, movie_details['keywords'])
                        if not keywords_saved:
                            logger.error(f"电影 ID: {movie_id} 的关键词信息保存失败")
                    except Exception as e:
                        logger.error(f"保存电影 ID: {movie_id} 的关键词信息时出错: {str(e)}")
                        keywords_saved = False

                # 只有当所有关键信息都保存成功时，才认为电影保存成功
                success = movie_saved and (credits_saved or 'credits' not in movie_details) and (keywords_saved or 'keywords' not in movie_details)
                if success:
                    logger.info(f"电影 ID: {movie_id} 的信息保存完成")
                else:
                    logger.error(f"电影 ID: {movie_id} 的信息部分保存失败: 基本信息={movie_saved}, 演职员信息={credits_saved}, 关键词信息={keywords_saved}")
                return success
            except Exception as e:
                logger.error(f"保存电影 ID: {movie_id} 时发生未预期错误: {str(e)}")
                # 如果是数据库连接问题，可能需要重试
                if "数据库连接" in str(e):
                    retries += 1
                    wait_time = 2 ** retries
                    logger.warning(f"数据库连接问题，{wait_time}秒后进行第{retries}次重试")
                    time.sleep(wait_time)
                    continue
                return False
            finally:
                if conn:
                    conn.close()

        except Exception as e:
            logger.error(f"获取或保存电影 ID: {movie_id} 的详细信息时出错: {str(e)}")
            retries += 1
            if retries >= max_retries:
                logger.error(f"达到最大重试次数({max_retries})，放弃处理电影 ID: {movie_id}")
                return False

            wait_time = 2 ** retries
            logger.warning(f"处理失败，{wait_time}秒后进行第{retries}次重试")
            time.sleep(wait_time)

    # 如果执行到这里，说明所有重试都失败了
    return False

def fetch_movie_ids_by_page(page=1, include_adult=False, endpoint="movie/top_rated"):
    """通过分页获取电影ID列表

    Args:
        page (int): 页码
        include_adult (bool): 是否包含成人内容
        endpoint (str): API端点，默认为高分电影(top_rated)，可选popular(热门)
    """
    try:
        # 获取电影列表
        movies_data = make_api_request(endpoint, {"page": page, "include_adult": include_adult})

        if 'results' not in movies_data:
            logger.error(f"获取电影第 {page} 页时未找到结果")
            return []

        movie_ids = [movie['id'] for movie in movies_data['results']]
        logger.info(f"获取电影第 {page} 页成功，共 {len(movie_ids)} 个电影")
        return movie_ids
    except Exception as e:
        logger.error(f"获取电影第 {page} 页时出错: {str(e)}")
        return []

def fetch_and_save_top_rated_movies(pages=10, include_adult=False, endpoint="movie/top_rated", target_movies=50000, resume=True, total_movies=None):
    """获取并保存高分电影

    Args:
        pages (int): 要获取的页数，如果超过TMDB API的最大页数，会自动调整
        include_adult (bool): 是否包含成人内容
        endpoint (str): API端点，默认为高分电影(top_rated)，可选popular(热门)
        target_movies (int): 要获取的电影总数，默认50000部
        resume (bool): 是否从上次中断的地方继续爬取，默认为True
        total_movies (int): 向后兼容参数，如果提供则覆盖target_movies

    Returns:
        bool: 电影获取是否成功
    """
    global stop_scraper_flag # 声明使用全局停止标志
    stop_scraper_flag = False # 每次启动新的爬虫任务时，重置停止标志

    try:
        # 处理向后兼容的total_movies参数
        if total_movies is not None:
            target_movies = total_movies
            logger.info(f"使用total_movies参数值: {total_movies}作为目标电影数量")
            
        # 检查并创建爬虫状态表
        check_and_create_scraper_state_table()
        
        # 如果resume为True，尝试从数据库加载爬虫状态
        if resume:
            db_state_loaded = load_scraper_state_from_db()
            if not db_state_loaded:
                # 不再尝试从文件加载状态
                # 如果数据库中没有状态，重置爬虫状态
                reset_progress()
                # 并设置目标电影数量和API端点
                scraper_progress["target_movies"] = target_movies
                scraper_progress["endpoint"] = endpoint
                # 明确更新状态为running并保存
                update_progress(status="running", message="爬虫已启动，开始获取电影数据")
            else:
                # 明确更新状态为running并保存，确保状态正确
                update_progress(status="running", message="从上次断点继续爬取电影数据")
                logger.info(f"成功加载爬虫状态，将从上次中断处继续：页码 {scraper_progress['last_page']}，已处理 {scraper_progress['processed_movies']} 部电影")
        else:
            # 如果不使用断点续传，重置爬虫状态
            reset_progress()
            # 设置目标电影数量和API端点
            scraper_progress["target_movies"] = target_movies
            scraper_progress["endpoint"] = endpoint
            # 明确更新状态为running并保存
            update_progress(status="running", message="爬虫已启动，开始获取电影数据")

        # 设置开始时间
        if scraper_progress["start_time"] is None:
            scraper_progress["start_time"] = datetime.now()
            save_scraper_state_to_db()  # 确保开始时间被保存

        conn = get_db_connection()
        # 获取API的最大页数
        first_page_data = make_api_request(
            endpoint, {"page": 1, "include_adult": str(include_adult).lower()})
        max_api_pages = first_page_data.get('total_pages', 500)
        
        # 计算要爬取的页数，考虑到API的限制和目标电影数量
        pages_to_crawl = min(max_api_pages, pages)
        
        # 如果已经有进度，从上次的页面继续
        start_page = scraper_progress["last_page"]
        if start_page == 0:
            start_page = 1  # 如果是第一次运行，从第1页开始
        
        # 页数范围：从start_page到start_page+pages_to_crawl
        # 但不超过max_api_pages
        end_page = min(max_api_pages, start_page + pages_to_crawl - 1)
        
        # 更新总页数估计值
        if target_movies > 0:
            # 根据目标电影数量估算总页数 (TMDB每页通常返回20部电影)
            scraper_progress["total_pages"] = min(max_api_pages, (target_movies // 20) + 2)  # 每页约20部电影，多加点页数确保足够
        else:
            # 如果没有明确指定目标数量，使用pages参数
            scraper_progress["total_pages"] = min(max_api_pages, (target_movies // 20) + 2)
            
        # 明确更新一次状态
        update_progress(
            current=0,
            status="running",
            message=f"开始获取电影数据，计划从第{start_page}页到第{end_page}页，目标{target_movies}部电影",
            last_page=start_page
        )
        
        # 记录已处理的电影数量
        processed_movies = scraper_progress["processed_movies"]
        
        # 获取所有电影类型
        all_genres = get_all_genres()

        # 记录已保存的电影ID，避免重复，初始为空集合
        saved_movie_ids = set()
        
        try:
            # 从start_page到end_page获取每一页的电影
            for page in range(start_page, end_page + 1):
                if stop_scraper_flag: # <--- 新增检查
                    logger.info("接收到停止信号，爬虫将停止...")
                    update_progress(status="idle", message="爬虫已手动停止")
                    if conn: conn.close()
                    return False

                try:
                    # 获取当前页的所有电影ID
                    page_movie_ids = fetch_movie_ids_by_page(
                        page, include_adult, endpoint)
                    
                    # 如果返回的ID列表为空，跳过这一页
                    if not page_movie_ids:
                        logger.warning(f"页面 {page} 没有返回任何电影ID，跳过")
                        continue
                    
                    logger.info(f"获取到第 {page} 页的 {len(page_movie_ids)} 个电影ID")
                    
                    # 更新进度信息，计算百分比
                    progress_percentage = min(100, int((page - start_page) / (end_page - start_page + 1) * 100))
                    update_progress(current=progress_percentage, message=f"已获取第 {page}/{scraper_progress['total_pages']} 页电影", last_page=page)
                    
                    # 处理每个电影ID
                    for movie_id in page_movie_ids:
                        if stop_scraper_flag: # <--- 在内层循环也检查
                            logger.info("接收到停止信号，爬虫将停止...")
                            update_progress(status="idle", message="爬虫已手动停止")
                            if conn: conn.close()
                            return False
                        
                        # 检查是否已经处理过这个电影
                        if movie_id in saved_movie_ids:
                            logger.info(f"电影 ID {movie_id} 已经处理过，跳过")
                            continue
                            
                        # 检查电影是否已存在于数据库中且信息完整
                        if is_movie_exists_in_db(movie_id):
                            logger.info(f"电影 ID {movie_id} 已存在于数据库中，跳过")
                            saved_movie_ids.add(movie_id)
                            processed_movies += 1  # 计入已处理电影数
                            continue
                            
                        # 获取并保存电影详情
                        fetch_and_save_movie_details(movie_id, all_genres)
                        
                        # 添加到已保存集合中
                        saved_movie_ids.add(movie_id)
                        
                        # 更新已处理电影数量
                        processed_movies += 1
                        
                        # 实时更新处理进度信息
                        update_progress(
                            processed_movies=processed_movies,
                            last_movie_id=movie_id,
                            message=f"已处理 {processed_movies}/{target_movies} 部电影，当前页面 {page}/{scraper_progress['total_pages']}"
                        )
                        
                        # 检查是否已达到目标电影数量
                        if target_movies > 0 and processed_movies >= target_movies:
                            logger.info(f"已达到目标电影数量 {target_movies} 部，停止爬取")
                            update_progress(
                                current=100,
                                status="completed",
                                message=f"已完成爬取，共处理 {processed_movies} 部电影"
                            )
                            if conn: conn.close()
                            return True
                except Exception as e:
                    logger.error(f"处理页面 {page} 时发生错误: {str(e)}")
                    # 更新进度状态，但继续处理下一页
                    update_progress(
                        message=f"处理页面 {page} 时发生错误: {str(e)}",
                        last_page=page
                    )
                    continue  # 继续处理下一页
                
                # 每页处理完毕后，更新进度
                update_progress(
                    current=progress_percentage,
                    last_page=page,
                    processed_movies=processed_movies,
                    message=f"已完成第 {page}/{scraper_progress['total_pages']} 页，共处理 {processed_movies} 部电影"
                )
                
            # 所有页面处理完毕
            update_progress(
                current=100,
                status="completed",
                message=f"已完成所有页面的爬取，共处理 {processed_movies} 部电影"
            )
            logger.info(f"电影数据爬取完成，共处理 {processed_movies} 部电影")
            if conn: conn.close()
            return True
        except Exception as e:
            logger.error(f"爬取电影数据过程中发生错误: {str(e)}")
            update_progress(
                status="error",
                message=f"爬取电影数据过程中发生错误: {str(e)}"
            )
            if conn: conn.close()
            return False
    except Exception as e:
        logger.error(f"启动爬虫过程中发生错误: {str(e)}")
        update_progress(
            status="error",
            message=f"启动爬虫过程中发生错误: {str(e)}"
        )
        return False

# 为了保持向后兼容，保留原函数名
def fetch_and_save_popular_movies(pages=10, include_adult=False):
    """获取并保存热门电影（为了向后兼容）"""
    return fetch_and_save_top_rated_movies(pages, include_adult, "movie/popular")

def fetch_movies_by_search(query, pages=2):
    """通过搜索关键词获取电影"""
    global stop_scraper_flag # 声明使用全局停止标志
    # stop_scraper_flag = False # 不在这里重置，由 run_scraper_async 或主调用函数重置

    try:
        # 更新爬虫进度
        update_progress(status="running", message=f"开始搜索电影: {query}")

        all_movie_ids = []
        for page in range(1, pages + 1):
            if stop_scraper_flag:
                logger.info(f"搜索 '{query}' 任务接收到停止信号，将停止。")
                update_progress(status="idle", message=f"搜索任务 '{query}' 已手动停止")
                return []
            try:
                # 搜索电影
                search_results = make_api_request("search/movie", {
                    "query": query,
                    "page": page,
                    "include_adult": False
                })

                if 'results' not in search_results:
                    logger.error(f"搜索电影 '{query}' 第 {page} 页时未找到结果")
                    continue

                # 提取电影ID
                movie_ids = [movie['id'] for movie in search_results['results']]
                all_movie_ids.extend(movie_ids)

                # 更新进度
                progress_percentage = (page / pages) * 20  # 获取电影ID占总进度的20%
                update_progress(current=progress_percentage, message=f"已搜索第 {page}/{pages} 页: {query}")

                logger.info(f"搜索 '{query}' 第 {page} 页成功，找到 {len(movie_ids)} 个电影")

                # 添加延迟，避免过快请求
                time.sleep(0.8)
            except Exception as e:
                logger.error(f"搜索电影 '{query}' 第 {page} 页时出错: {str(e)}")

        # 获取默认电影类型
        all_genres = [
            (28, '动作'),
            (12, '冒险'),
            (16, '动画'),
            (35, '喜剧'),
            (80, '犯罪'),
            (18, '剧情'),
            (10751, '家庭'),
            (14, '奇幻'),
            (36, '历史'),
            (27, '恐怖'),
            (10402, '音乐'),
            (9648, '悬疑'),
            (10749, '爱情'),
            (878, '科幻'),
            (53, '惊悚'),
            (10752, '战争'),
            (37, '西部')
        ]

        # 获取并保存每个电影的详细信息
        total_movies = len(all_movie_ids)
        success_count = 0
        for index, movie_id in enumerate(all_movie_ids):
            if stop_scraper_flag:
                logger.info(f"处理 '{query}' 相关电影详情时接收到停止信号，将停止。")
                update_progress(status="idle", message=f"搜索任务 '{query}' 的详情处理已手动停止")
                return all_movie_ids[:index] # 返回已处理部分
            success = fetch_and_save_movie_details(movie_id, all_genres)
            if success:
                success_count += 1

            # 更新进度 (20%的进度已用于搜索，剩余80%用于获取详情)
            progress_percentage = 20 + ((index + 1) / total_movies) * 80
            update_progress(
                current=progress_percentage,
                message=f"处理电影 {index+1}/{total_movies}: ID {movie_id}"
            )

            # 添加延迟，避免过快请求
            time.sleep(1)

        update_progress(current=100, status="completed", message=f"搜索完成！成功获取 {total_movies} 部 '{query}' 相关电影")
        return all_movie_ids
    except Exception as e:
        logger.error(f"搜索电影 '{query}' 时出错: {str(e)}")
        update_progress(status="error", message=f"搜索失败: {str(e)}")
        return []

def fetch_movies_by_person(person_id, is_director=False):
    """获取与特定演员或导演相关的电影
    
    Args:
        person_id (int): 人物ID
        is_director (bool, optional): 是否是导演. 默认为 False.
        
    Returns:
        list: 电影ID列表
    """
    global stop_scraper_flag # 声明使用全局停止标志
    # stop_scraper_flag = False # 不在这里重置

    try:
        # 获取人物详情
        person_details = make_api_request(f"person/{person_id}")
        person_name = person_details.get('name', f"ID: {person_id}")

        # 更新爬虫进度
        role_type = "导演" if is_director else "演员"
        update_progress(status="running", message=f"开始获取{role_type} {person_name} 的相关电影")

        # 获取人物参与的电影
        movie_credits = make_api_request(f"person/{person_id}/movie_credits")

        all_movie_ids = []

        if is_director:
            # 如果是导演，只获取导演作品
            if 'crew' in movie_credits:
                # 筛选出导演作品
                director_jobs = ['Director']
                crew_movies = [movie for movie in movie_credits['crew'] if movie.get('job') in director_jobs]
                crew_ids = [movie['id'] for movie in crew_movies]
                all_movie_ids.extend(crew_ids)
                logger.info(f"找到{role_type} {person_name} 的导演作品 {len(crew_ids)} 部")
        else:
            # 如果是演员，获取演员作品
            if 'cast' in movie_credits:
                cast_ids = [movie['id'] for movie in movie_credits['cast']]
                all_movie_ids.extend(cast_ids)
                logger.info(f"找到{role_type} {person_name} 的演员作品 {len(cast_ids)} 部")

        # 去重
        all_movie_ids = list(set(all_movie_ids))

        # 获取默认电影类型
        all_genres = [
            (28, '动作'),
            (12, '冒险'),
            (16, '动画'),
            (35, '喜剧'),
            (80, '犯罪'),
            (18, '剧情'),
            (10751, '家庭'),
            (14, '奇幻'),
            (36, '历史'),
            (27, '恐怖'),
            (10402, '音乐'),
            (9648, '悬疑'),
            (10749, '爱情'),
            (878, '科幻'),
            (53, '惊悚'),
            (10752, '战争'),
            (37, '西部')
        ]

        # 获取并保存每个电影的详细信息
        total_movies = len(all_movie_ids)
        success_count = 0
        for index, movie_id in enumerate(all_movie_ids):
            if stop_scraper_flag:
                logger.info(f"处理{role_type} {person_name} 相关电影详情时接收到停止信号，将停止。")
                update_progress(status="idle", message=f"{role_type} {person_name} 相关电影任务已手动停止")
                return all_movie_ids[:index] # 返回已处理部分
            success = fetch_and_save_movie_details(movie_id, all_genres)
            if success:
                success_count += 1

            # 更新进度
            progress_percentage = ((index + 1) / total_movies) * 100
            update_progress(
                current=progress_percentage,
                message=f"处理{role_type} {person_name} 的电影 {index+1}/{total_movies}: ID {movie_id}"
            )

            # 添加延迟，避免过快请求
            time.sleep(1)

        update_progress(current=100, status="completed", message=f"获取完成！成功获取{role_type} {person_name} 的 {success_count} 部电影")
        return all_movie_ids
    except Exception as e:
        logger.error(f"获取{role_type if 'role_type' in locals() else '人物'} ID: {person_id} 的电影时出错: {str(e)}")
        update_progress(status="error", message=f"获取失败: {str(e)}")
        return []

def run_scraper_async(function=fetch_and_save_top_rated_movies, *args, **kwargs):
    """异步运行爬虫

    Args:
        function: 要运行的爬虫函数，默认为获取高分电影
        *args, **kwargs: 传递给爬虫函数的参数
    """
    global scraper_thread, stop_scraper_flag # 添加 stop_scraper_flag

    # 检查是否有爬虫已在运行
    if scraper_thread and scraper_thread.is_alive():
        logger.warning("爬虫已在运行中，无法启动新的爬虫任务")
        return False
    
    # 首先检查并修复数据库结构
    logger.info("启动爬虫前检查数据库结构")
    check_result = check_and_create_scraper_state_table()
    if not check_result:
        logger.error("数据库结构检查失败，无法启动爬虫")
        return False
    logger.info("数据库结构检查完成")
    
    # 检查爬虫状态
    state_loaded = False
    
    # 如果未指定是否断点续传，默认为True
    if 'resume' not in kwargs:
        kwargs['resume'] = True
    
    # 如果kwargs中有resume参数并且为True，尝试加载状态
    if kwargs.get('resume'):
        # 尝试从数据库加载状态
        state_loaded = load_scraper_state_from_db()
        
        # 不再尝试从文件加载
        # if not state_loaded:
        #     state_loaded = load_scraper_state_from_file()
        
        if state_loaded:
            logger.info(f"成功加载爬虫状态，将从上次中断处继续：页码 {scraper_progress['last_page']}，已处理 {scraper_progress['processed_movies']} 部电影")
            
            # 检查之前的状态，如果是error或idle，则重置为running
            if scraper_progress["status"] in ["error", "idle"]:
                update_progress(status="running", message="从上次中断处继续爬取")
    
    def task():
        try:
            # 在线程中重置停止标志
            global stop_scraper_flag
            stop_scraper_flag = False
            
            function(*args, **kwargs)
        except Exception as e:
            logger.error(f"爬虫运行时出错: {str(e)}")
            update_progress(status="error", message=f"爬虫出错: {str(e)}")

    # 创建并启动线程
    scraper_thread = threading.Thread(target=task)
    scraper_thread.daemon = True  # 设置为守护线程
    scraper_thread.start()
    
    if state_loaded:
        logger.info(f"异步爬虫任务已启动: {function.__name__}，从上次中断处继续")
    else:
        logger.info(f"异步爬虫任务已启动: {function.__name__}，从头开始爬取")
    
    return True

def get_all_genres():
    """获取所有电影类型
    
    Returns:
        list: 包含电影类型ID和名称的列表，格式为[(id, name), ...]
    """
    try:
        genres = make_api_request("genre/movie/list")
        if 'genres' in genres:
            all_genres = [(genre['id'], genre['name']) for genre in genres['genres']]
            logger.info(f"获取到 {len(all_genres)} 个电影类型")
            return all_genres
        else:
            logger.warning("获取电影类型列表时，返回数据格式不正确")
            return []
    except Exception as e:
        logger.error(f"获取电影类型列表失败: {str(e)}")
        return []

def test_scraper_status_update():
    """测试爬虫状态更新功能
    
    这个函数可以用来测试爬虫状态更新和数据库连接是否正常
    """
    try:
        # 1. 检查并创建状态表
        logger.info("测试爬虫状态更新: 1. 检查并创建状态表")
        check_and_create_scraper_state_table()
        
        # 2. 重置爬虫状态
        logger.info("测试爬虫状态更新: 2. 重置爬虫状态")
        reset_progress()
        
        # 3. 更新爬虫状态为运行中
        logger.info("测试爬虫状态更新: 3. 更新爬虫状态为运行中")
        update_progress(status="running", message="测试爬虫状态更新", current=10)
        
        # 4. 获取更新后的状态
        logger.info("测试爬虫状态更新: 4. 获取更新后的状态")
        progress = get_progress()
        
        # 检查状态是否正确
        if progress["status"] == "running" and progress["current"] == 10:
            logger.info("测试爬虫状态更新: 状态更新成功!")
            
            # 5. 再次更新状态为已完成
            logger.info("测试爬虫状态更新: 5. 再次更新状态为已完成")
            update_progress(status="completed", message="测试完成", current=100)
            
            # 6. 从数据库加载状态
            logger.info("测试爬虫状态更新: 6. 从数据库加载状态")
            load_scraper_state_from_db()
            
            return True
        else:
            logger.error(f"测试爬虫状态更新: 状态更新失败! status={progress['status']}, current={progress['current']}")
            return False
    except Exception as e:
        logger.error(f"测试爬虫状态更新失败: {str(e)}")
        return False

def stop_scraper():
    """设置停止标志以请求停止爬虫线程"""
    global stop_scraper_flag, scraper_thread
    logger.info("请求停止爬虫...")
    stop_scraper_flag = True
    
    # 更新状态以提供即时反馈
    current_status = scraper_progress.get("status")
    if current_status == "running":
        # 避免在爬虫线程自身更新状态之前覆盖
        # 可以考虑只在特定条件下更新，或依赖爬虫自身更新
        # update_progress(status="idle", message="已发送停止请求，等待爬虫响应...")
        logger.info("停止标志已设置。爬虫将在下一个检查点停止。")
    
    return {"status": "stopping_initiated", "message": "已发送停止爬虫请求，爬虫将在下一个检查点停止。"}

def search_person(name, max_retries=3):
    """搜索人物（演员或导演）
    
    Args:
        name (str): 人物名称
        max_retries (int, optional): 最大重试次数. 默认为 3.
        
    Returns:
        int or None: 人物ID，如果未找到则返回None
    """
    if not name:
        logger.warning("搜索人物时，名称为空")
        return None
        
    logger.info(f"搜索人物: {name}")
    endpoint = "search/person"
    params = {
        "query": name,
        "include_adult": "false",
        "language": "zh-CN",
        "page": 1
    }
    
    try:
        response = make_api_request(endpoint, params, max_retries)
        if not response or 'results' not in response:
            logger.warning(f"搜索人物 {name} 时未获取到有效响应")
            return None
            
        results = response.get('results', [])
        if not results:
            logger.warning(f"未找到人物: {name}")
            return None
            
        # 返回第一个匹配结果的ID
        first_match = results[0]
        person_id = first_match.get('id')
        
        if person_id:
            logger.info(f"找到人物 {name}: ID={person_id}, 知名作品: {first_match.get('known_for_department', '')}")
            return person_id
        else:
            logger.warning(f"人物 {name} 的ID为空")
            return None
    except Exception as e:
        logger.error(f"搜索人物 {name} 时出错: {e}")
        return None

def fetch_movies_by_discover(params, pages=1, include_adult=False):
    """使用发现API按条件搜索电影
    
    Args:
        params (dict): 搜索参数
        pages (int, optional): 要获取的页数. 默认为 1.
        include_adult (bool, optional): 是否包含成人内容. 默认为 False.
        
    Returns:
        bool: 是否成功获取并保存电影
    """
    endpoint = "discover/movie"
    total_movies_processed = 0
    
    # 更新爬虫进度信息
    global scraper_progress
    scraper_progress["endpoint"] = endpoint
    scraper_progress["start_time"] = datetime.now()  # 使用datetime对象而不是字符串
    
    # 设置默认参数
    default_params = {
        "include_adult": str(include_adult).lower(),
        "include_video": "false",
        "language": "zh-CN",
        "sort_by": "popularity.desc",
        "page": 1
    }
    
    # 合并默认参数和用户提供的参数
    api_params = {**default_params, **params}
    
    try:
        # 先获取第一页，确定总页数
        logger.info(f"开始获取发现API电影列表，参数: {api_params}")
        response = make_api_request(endpoint, api_params)
        
        if not response:
            logger.error("获取发现API电影列表失败")
            update_progress(status="error", message="获取发现API电影列表失败")
            return False
            
        total_pages = response.get('total_pages', 1)
        total_results = response.get('total_results', 0)
        logger.info(f"发现API电影搜索总结果: {total_results} 部电影，共 {total_pages} 页")
        
        # 确保页数不超过总页数
        if pages > total_pages:
            pages = total_pages
            
        if pages > 20:  # API限制，最多只能获取20页
            pages = 20
            
        # 更新进度信息
        scraper_progress["total_pages"] = pages
        update_progress(
            current=0, 
            message=f"发现API搜索到 {total_results} 部电影，计划爬取 {pages} 页",
            last_page=1
        )
        
        # 处理所有页
        conn = get_db_connection()
        
        # 准备用于存储电影ID的集合
        all_movie_ids = set()
        processed_count = 0
        skipped_existing_count = 0
        failed_processing_count = 0
        
        # 处理每一页
        for page in range(1, pages + 1):
            # 检查是否需要停止爬虫
            global stop_scraper_flag
            if stop_scraper_flag:
                logger.info("收到停止爬虫信号，中断电影发现API处理")
                update_progress(status="completed", message="爬虫已手动停止")
                stop_scraper_flag = False  # 重置标志
                return True
                
            # 更新请求参数中的页码
            api_params['page'] = page
            
            # 更新进度
            update_progress(
                current=int(page * 100 / pages),
                message=f"正在处理第 {page}/{pages} 页",
                last_page=page
            )
            
            if page > 1:  # 第一页已经获取过
                response = make_api_request(endpoint, api_params)
                if not response or 'results' not in response:
                    logger.warning(f"获取第 {page} 页数据失败，跳过")
                    continue
                    
            # 获取当前页的电影列表
            movies = response.get('results', [])
            if not movies:
                logger.warning(f"第 {page} 页没有电影数据")
                continue
                
            # 记录当前页的电影ID
            page_movie_ids = set()
            
            # 处理每部电影
            for movie in movies:
                movie_id = movie.get('id')
                if not movie_id:
                    continue
                    
                # 如果电影ID已经处理过，跳过
                if movie_id in all_movie_ids:
                    continue
                    
                all_movie_ids.add(movie_id)
                page_movie_ids.add(movie_id)
                
                # 检查电影是否已存在于数据库中
                if is_movie_exists_in_db(movie_id):
                    logger.debug(f"电影 ID {movie_id} 已存在于数据库中")
                    skipped_existing_count += 1
                    continue
                    
                # 获取并保存电影详情
                if fetch_and_save_movie_details(movie_id, max_retries=3):
                    processed_count += 1
                    update_progress(
                        processed_movies=scraper_progress["processed_movies"] + 1,
                        message=f"第 {page}/{pages} 页 | 已处理 {processed_count} 部电影"
                    )
                else:
                    failed_processing_count += 1
                    logger.warning(f"电影 ID {movie_id} 获取或保存失败")
                    
            logger.info(f"第 {page} 页处理完成，新增 {len(page_movie_ids)} 部电影ID")
            
        # 更新最终进度
        total_movies_processed = processed_count
        logger.info(f"发现API电影处理完成，共处理 {total_movies_processed} 部电影")
        logger.info(f"电影处理统计: 新发现ID {len(all_movie_ids)} 部, 成功保存 {processed_count} 部, 已存在跳过 {skipped_existing_count} 部, 处理失败 {failed_processing_count} 部")
        
        # 更新爬虫状态
        scraper_progress["end_time"] = datetime.now()
        update_progress(
            current=100,
            status="completed",
            message=f"发现API电影处理完成，共处理 {total_movies_processed} 部电影, 已存在跳过 {skipped_existing_count} 部"
        )
        
        return True
    except Exception as e:
        logger.error(f"处理发现API电影时出错: {e}")
        update_progress(status="error", message=f"处理发现API电影时出错: {e}")
        return False
    finally:
        try:
            if 'conn' in locals() and conn:
                conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    # 测试代码
    logger.info("开始爬取TMDB电影数据")
    
    # 执行测试
    logger.info("首先测试爬虫状态更新功能")
    test_result = test_scraper_status_update()
    if test_result:
        logger.info("测试成功，开始正式爬取")
        # 修改为爬取50000部高分电影，增加页数以获取足够的电影
        fetch_and_save_top_rated_movies(
            pages=500,  # 增加页数，每页约20部电影
            target_movies=50000,  # 目标获取50000部完整电影
            resume=True,  # 启用断点续传
            include_adult=False  # 不包含成人内容
        )
    else:
        logger.error("测试失败，请检查数据库连接和日志")
    
    logger.info("TMDB电影数据爬取完成")
