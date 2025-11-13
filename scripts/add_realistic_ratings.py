#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
为没有评分的电影添加真实的评分、评论和观看历史

此脚本用于识别数据库中没有任何评分的电影，并使用随机选择的普通用户
为这些电影添加评分(3-9分)、评论和观看历史记录，丰富系统数据。
"""

import sys
import os
import random
from datetime import datetime
import pymysql
import logging
from logging.handlers import RotatingFileHandler

# 设置导入路径
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, '..'))
sys.path.insert(0, root_dir)

# 导入项目配置
from config import Config

# 配置日志记录
log_dir = os.path.join(root_dir, 'archive', 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'add_realistic_ratings.log')

logger = logging.getLogger('add_realistic_ratings')
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
        conn = pymysql.connect(
            host=Config.DB_CONFIG['host'],
            user=Config.DB_CONFIG['user'],
            password=Config.DB_CONFIG['password'],
            database=Config.DB_CONFIG['database'],
            charset=Config.DB_CONFIG['charset'],
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"连接数据库失败: {e}")
        return None

def get_unrated_movies(conn):
    """获取没有任何评分的电影"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT m.id, m.title, m.original_title, m.overview, m.vote_average, m.release_date 
            FROM movies m 
            LEFT JOIN user_ratings ur ON m.id = ur.movie_id 
            WHERE ur.movie_id IS NULL
            AND m.title IS NOT NULL 
            AND m.title != ''
            ORDER BY m.id
            """
        )
        movies = cursor.fetchall()
        logger.info(f"找到 {len(movies)} 部没有评分的电影")
        return movies
    except Exception as e:
        logger.error(f"查询无评分电影失败: {e}")
        return []
    finally:
        cursor.close()

def get_regular_users(conn):
    """获取普通用户(非管理员)"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, username 
            FROM userinfo 
            WHERE id NOT IN (SELECT id FROM admininfo) 
            AND status = 'active'
            """
        )
        users = cursor.fetchall()
        logger.info(f"找到 {len(users)} 个普通用户")
        return users
    except Exception as e:
        logger.error(f"查询普通用户失败: {e}")
        return []
    finally:
        cursor.close()

def get_existing_ratings(conn, movie_id):
    """获取电影已有的评分，避免重复添加"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT user_id FROM user_ratings 
            WHERE movie_id = %s
            """,
            (movie_id,)
        )
        return [row['user_id'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"查询已有评分失败: {e}")
        return []
    finally:
        cursor.close()

def generate_comment(movie, rating):
    """基于电影信息和评分生成评论内容"""
    movie_title = movie['title'] or movie['original_title']
    
    positive_comments = [
        f"《{movie_title}》是一部很棒的电影，故事情节吸引人，演员表演也很出色。",
        f"我非常喜欢这部电影的视觉效果和音乐，值得一看。",
        f"《{movie_title}》的剧情发展很流畅，人物塑造也很成功。",
        f"这部电影的导演功力很深厚，拍摄手法独特。",
        f"虽然不算完美，但整体来说这是一部很好看的电影。",
        f"我被《{movie_title}》中的演员表演深深打动了。",
        f"这部电影的故事很有创意，让人回味无穷。",
        f"画面精美，剧情紧凑，是一部不错的作品。",
        f"这部电影让我印象深刻，推荐给大家观看。"
    ]
    
    neutral_comments = [
        f"《{movie_title}》是一部还不错的电影，但有些情节有点拖沓。",
        f"这部电影的前半部分很精彩，但后半部分节奏有点慢。",
        f"《{movie_title}》有几个精彩的场景，但整体表现一般。",
        f"剧情还行，但演员的表演有些地方不够自然。",
        f"我对这部电影感觉比较中立，有亮点也有不足。",
        f"《{movie_title}》的创意很好，但执行上有些欠缺。",
        f"这部电影的情节有点老套，但还算流畅。",
        f"中规中矩的一部电影，没有特别出彩的地方。",
        f"看完感觉一般般，不算太差但也不算特别好。"
    ]
    
    critical_comments = [
        f"《{movie_title}》不太符合我的预期，情节发展比较平淡。",
        f"这部电影的节奏太慢了，很难让人一直保持兴趣。",
        f"《{movie_title}》的剧情有些混乱，人物动机不够清晰。",
        f"演员的表演不够自然，对白也有点尴尬。",
        f"我觉得这部电影被过誉了，实际上并没有那么出彩。",
        f"《{movie_title}》的结尾让我感到失望，没有好好收尾。",
        f"这部电影的特效看起来很廉价，不太符合现在的标准。",
        f"剧情拖沓，看了一半就想弃了。",
        f"整体来说比较失望，没有达到期望值。"
    ]
    
    # 根据评分选择合适的评论类型
    if rating >= 7:
        comments = positive_comments
    elif rating >= 5:
        comments = neutral_comments
    else:
        comments = critical_comments
        
    # 加入电影简介相关内容（如果有）
    if movie['overview'] and len(movie['overview']) > 20:
        # 从电影简介中提取一小段
        snippet = movie['overview'][:50]
        custom_comment = f"关于\"{snippet}...\"这个部分，我认为导演的处理很{('出色' if rating >= 7 else '一般' if rating >= 5 else '不够理想')}"
        comments.append(custom_comment)
        
    return random.choice(comments)

def add_watch_history(conn, user_id, movie_id):
    """为用户添加观看历史记录"""
    cursor = conn.cursor()
    try:
        # 检查是否已有观看历史记录
        cursor.execute(
            "SELECT id FROM user_watch_history WHERE user_id = %s AND movie_id = %s",
            (user_id, movie_id)
        )
        if cursor.fetchone():
            return True  # 已有记录，跳过
            
        # 生成随机的观看时间（最近30天内的随机时间）
        import random
        from datetime import datetime, timedelta
        
        days_ago = random.randint(1, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        
        watched_time = datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        
        # 插入观看历史记录
        cursor.execute(
            "INSERT INTO user_watch_history (user_id, movie_id, watched_at) VALUES (%s, %s, %s)",
            (user_id, movie_id, watched_time)
        )
        
        return True
    except Exception as e:
        logger.error(f"添加观看历史失败: {e}")
        return False
    finally:
        cursor.close()

def add_realistic_ratings(conn, movies, users, ratings_per_movie=5):
    """为每部电影添加指定数量的真实评分和观看历史"""
    cursor = conn.cursor()
    
    total_added_ratings = 0
    total_added_history = 0
    
    try:
        for movie in movies:
            movie_id = movie['id']
            
            # 获取已有评分的用户，避免重复添加
            existing_user_ids = get_existing_ratings(conn, movie_id)
            
            # 过滤掉已有评分的用户
            available_users = [user for user in users if user['id'] not in existing_user_ids]
            
            if not available_users:
                logger.warning(f"电影 {movie_id}({movie['title']}) 没有可用的用户来添加评分")
                continue
                
            # 为每部电影添加指定数量的评分，或者根据可用用户数量添加
            actual_ratings = min(ratings_per_movie, len(available_users))
            selected_users = random.sample(available_users, actual_ratings)
            
            for user in selected_users:
                # 生成3-9之间的随机评分
                rating = random.randint(3, 9)
                
                # 生成评论内容
                comment = generate_comment(movie, rating)
                
                # 生成随机的评分时间（最近60天内）
                from datetime import datetime, timedelta
                days_ago = random.randint(1, 60)
                hours_ago = random.randint(0, 23)
                minutes_ago = random.randint(0, 59)
                rating_time = datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
                
                # 插入评分记录
                cursor.execute(
                    """
                    INSERT INTO user_ratings (user_id, movie_id, rating, comment, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user['id'], movie_id, rating, comment, rating_time)
                )
                
                # 添加观看历史记录（80%的概率添加观看历史）
                if random.random() < 0.8:
                    # 观看时间应该在评分时间之前
                    watch_days_before = random.randint(0, 7)  # 评分前0-7天观看
                    watch_time = rating_time - timedelta(days=watch_days_before, 
                                                       hours=random.randint(0, 23), 
                                                       minutes=random.randint(0, 59))
                    
                    # 检查是否已有观看历史
                    cursor.execute(
                        "SELECT id FROM user_watch_history WHERE user_id = %s AND movie_id = %s",
                        (user['id'], movie_id)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO user_watch_history (user_id, movie_id, watched_at) VALUES (%s, %s, %s)",
                            (user['id'], movie_id, watch_time)
                        )
                        total_added_history += 1
                
                logger.debug(f"用户 {user['username']}({user['id']}) 为电影 {movie['title']}({movie_id}) 添加了评分: {rating}")
                total_added_ratings += 1
                
            # 更新电影的总评分和评分计数
            cursor.execute(
                """
                SELECT AVG(rating) as avg_rating, COUNT(*) as count
                FROM user_ratings
                WHERE movie_id = %s
                """,
                (movie_id,)
            )
            result = cursor.fetchone()
            
            if result and result['avg_rating'] is not None:
                # 确保评分为最多一位小数
                avg_rating = round(float(result['avg_rating']), 1)
                cursor.execute(
                    """
                    UPDATE movies
                    SET vote_average = %s, vote_count = %s
                    WHERE id = %s
                    """,
                    (avg_rating, result['count'], movie_id)
                )
                
                logger.info(f"更新电影 {movie['title']}({movie_id}) 的评分为 {avg_rating:.1f}，评分总数为 {result['count']}")
            
            conn.commit()
            
        logger.info(f"成功添加了 {total_added_ratings} 条评分记录和 {total_added_history} 条观看历史记录")
        return total_added_ratings, total_added_history
    
    except Exception as e:
        conn.rollback()
        logger.error(f"添加评分失败: {e}")
        return 0, 0
    finally:
        cursor.close()

def main(ratings_per_movie=5):
    """主函数"""
    conn = get_db_connection()
    if not conn:
        logger.error("无法连接数据库，退出程序")
        return False
        
    try:
        # 获取没有评分的电影
        movies = get_unrated_movies(conn)
        if not movies:
            logger.info("没有找到无评分的电影，无需处理")
            return True
            
        # 获取普通用户
        users = get_regular_users(conn)
        if not users:
            logger.error("没有找到普通用户，无法添加评分")
            return False
            
        # 添加真实评分和观看历史
        added_ratings, added_history = add_realistic_ratings(conn, movies, users, ratings_per_movie)
        
        if added_ratings > 0:
            logger.info(f"脚本执行成功，共添加了 {added_ratings} 条评分记录和 {added_history} 条观看历史记录")
            return True
        else:
            logger.warning("没有添加任何评分记录")
            return False
            
    except Exception as e:
        logger.error(f"脚本执行过程中发生错误: {e}")
        return False
    finally:
        conn.close()
        
if __name__ == "__main__":
    # 从命令行参数获取每部电影的评分数量，默认为5
    import argparse
    
    parser = argparse.ArgumentParser(description='为没有评分的电影添加真实的评分、评论和观看历史')
    parser.add_argument('--ratings', type=int, default=5, help='为每部电影添加的评分数量（默认为5）')
    
    args = parser.parse_args()
    
    if main(args.ratings):
        sys.exit(0)  # 成功执行
    else:
        sys.exit(1)  # 执行失败
