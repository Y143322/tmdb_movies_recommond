#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户偏好管理模块

用于分析用户评分历史，计算并更新用户对不同电影类型的偏好程度。
这些数据存储在user_genre_preferences表中，用于增强推荐系统的个性化能力。
"""

import logging
import pymysql
from datetime import datetime
import pandas as pd
import numpy as np
from movies_recommend.logger import get_logger
from movies_recommend.extensions import get_db_connection
from typing import List, Dict, Optional
from collections import Counter

# 获取日志记录器
logger = get_logger('user_preferences')

def update_user_genre_preferences(user_id, conn=None):
    """
    更新指定用户的电影类型偏好

    根据用户的评分历史，计算用户对不同电影类型的偏好程度，
    并将结果更新到user_genre_preferences表中。

    参数:
        user_id (int): 用户ID
        conn (pymysql.Connection, optional): 可选的数据库连接

    返回:
        bool: 更新成功返回True，否则返回False
    """
    should_close_conn = False
    try:
        # 如果没有提供连接，创建一个新的
        if conn is None:
            # 尝试通过扩展获取连接
            try:
                from movies_recommend.extensions import get_db_connection
                conn = get_db_connection()
            except Exception:
                # 失败时使用直接连接
                conn = pymysql.connect(
                    host='localhost',
                    user='root',
                    password='root',
                    database='movies_recommend',
                    charset='utf8mb4',
                    cursorclass=pymysql.cursors.DictCursor
                )
            should_close_conn = True
        
        cursor = conn.cursor()
        
        # 获取用户评分过的所有电影
        cursor.execute("""
            SELECT ur.movie_id, ur.rating, m.genres 
            FROM user_ratings ur
            JOIN movies m ON ur.movie_id = m.id
            WHERE ur.user_id = %s AND m.genres IS NOT NULL AND m.genres != ''
        """, (user_id,))
        
        ratings_data = cursor.fetchall()
        
        if not ratings_data:
            logger.info(f"用户 {user_id} 没有有效的评分记录，跳过类型偏好更新")
            if should_close_conn:
                conn.close()
            return False
        
        # 处理类型数据
        genre_ratings = {}  # 格式: {genre: [rating1, rating2, ...]}
        
        for movie_id, rating, genres in ratings_data:
            # 类型可能是逗号分隔的字符串
            if genres:
                for genre in [g.strip() for g in genres.split(',')]:
                    if genre:
                        if genre not in genre_ratings:
                            genre_ratings[genre] = []
                        genre_ratings[genre].append(rating)
        
        # 计算每个类型的偏好分数
        # 偏好分数计算方法: 归一化的平均评分 * (1 + log(评分数量))
        # 这样既考虑了评分高低，也考虑了用户对该类型电影的关注度
        preferences = {}
        
        all_scores = []  # 用于归一化
        
        for genre, ratings in genre_ratings.items():
            if len(ratings) > 0:
                avg_rating = sum(ratings) / len(ratings)
                # 加入评分数量的影响，但避免过度偏向热门类型
                import math
                score = avg_rating * (1 + 0.3 * math.log(1 + len(ratings)))
                preferences[genre] = score
                all_scores.append(score)
        
        # 如果没有任何有效偏好，退出
        if not preferences:
            logger.info(f"用户 {user_id} 没有有效的类型偏好，跳过更新")
            if should_close_conn:
                conn.close()
            return False
        
        # 归一化分数到0-10范围，使其与电影评分范围一致
        min_score = min(all_scores) if all_scores else 0
        max_score = max(all_scores) if all_scores else 10
        
        # 避免除以零
        score_range = max_score - min_score
        if score_range == 0:
            score_range = 1
        
        # 开始事务
        conn.begin()
        
        # 先删除用户现有的偏好记录
        cursor.execute("DELETE FROM user_genre_preferences WHERE user_id = %s", (user_id,))
        
        # 插入新的偏好记录
        for genre, score in preferences.items():
            # 归一化到0-10范围
            normalized_score = ((score - min_score) / score_range) * 10
            # 确保分数在合理范围内
            final_score = max(0.5, min(10.0, normalized_score))
            
            cursor.execute("""
                INSERT INTO user_genre_preferences (user_id, genre_name, preference_score) 
                VALUES (%s, %s, %s)
            """, (user_id, genre, final_score))
        
        # 提交事务
        conn.commit()
        
        logger.info(f"已更新用户 {user_id} 的类型偏好: {len(preferences)} 个类型")
        
        if should_close_conn:
            conn.close()
        
        return True
    
    except Exception as e:
        logger.error(f"更新用户 {user_id} 类型偏好失败: {str(e)}")
        if conn and conn.open:
            conn.rollback()
            if should_close_conn:
                conn.close()
        return False

def batch_update_all_users_preferences():
    """
    批量更新所有用户的电影类型偏好
    
    返回:
        tuple: (成功更新的用户数, 总用户数)
    """
    try:
        # 直接创建数据库连接，避免使用连接池
        try:
            from movies_recommend.extensions import get_db_connection
            conn = get_db_connection()
        except Exception:
            # 如果无法通过扩展获取连接，使用直接连接
            import pymysql
            conn = pymysql.connect(
                host='localhost',
                user='root',
                password='root',
                database='movies_recommend',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
        
        cursor = conn.cursor()
        
        # 获取所有有评分记录的用户
        cursor.execute("""
            SELECT DISTINCT user_id 
            FROM user_ratings
        """)
        
        users = [row[0] for row in cursor.fetchall()]
        
        if not users:
            logger.info("没有找到任何用户评分记录，跳过批量更新")
            conn.close()
            return (0, 0)
        
        logger.info(f"开始为 {len(users)} 个用户更新类型偏好")
        
        success_count = 0
        for user_id in users:
            if update_user_genre_preferences(user_id, conn):
                success_count += 1
                
            # 每50个用户打印一次进度
            if success_count % 50 == 0:
                logger.info(f"已更新 {success_count}/{len(users)} 个用户的类型偏好")
        
        cursor.close()
        conn.close()
        
        logger.info(f"批量更新完成: {success_count}/{len(users)} 个用户成功更新")
        return (success_count, len(users))
    
    except Exception as e:
        logger.error(f"批量更新用户类型偏好失败: {str(e)}")
        return (0, 0)

def get_user_top_genres(user_id: int, n: int = 5) -> List[tuple]:
    """获取用户最喜欢的电影类型
    
    通过分析用户的评分历史，找出用户最喜欢的电影类型。
    
    Args:
        user_id (int): 用户ID
        n (int): 返回的类型数量
        
    Returns:
        List[tuple]: 用户最喜欢的电影类型列表，每个元素为 (genre_name, score) 元组
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 从user_genre_preferences表获取用户的类型偏好
        cursor.execute("""
            SELECT genre_name, preference_score
            FROM user_genre_preferences
            WHERE user_id = %s
            ORDER BY preference_score DESC
            LIMIT %s
        """, (user_id, n))
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not results:
            return []
            
        # 返回(类型名称, 评分)元组列表
        return [(row[0], float(row[1])) for row in results]
        
    except Exception as e:
        logger.error(f"获取用户类型偏好失败: {str(e)}")
        return []

def get_users_by_genre_preference(genre_name, min_score=7.0, limit=20):
    """
    获取对特定电影类型有较高偏好的用户
    
    参数:
        genre_name (str): 电影类型名称
        min_score (float): 最低偏好分数
        limit (int): 返回用户数量上限
        
    返回:
        list: 用户ID列表
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_id 
            FROM user_genre_preferences 
            WHERE genre_name = %s AND preference_score >= %s 
            ORDER BY preference_score DESC 
            LIMIT %s
        """, (genre_name, min_score, limit))
        
        users = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return users
    
    except Exception as e:
        logger.error(f"获取偏好{genre_name}类型的用户失败: {str(e)}")
        return []

def update_user_genre_preferences_single_movie(user_id, movie_id, rating_value):
    """
    更新用户基于单个电影评分的类型偏好
    
    这是一个简化版本，专为电影评分后直接调用设计，
    只会根据当前评分的电影类型更新相关偏好，而不是全量更新所有类型偏好。
    
    参数:
        user_id (int): 用户ID
        movie_id (int): 电影ID
        rating_value (float): 评分值
        
    返回:
        bool: 更新成功返回True，否则返回False
    """
    try:
        # 获取数据库连接
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取电影类型
        cursor.execute(
            "SELECT genres FROM movies WHERE id = %s", 
            (movie_id,)
        )
        result = cursor.fetchone()
        
        # 如果找不到电影或没有类型信息，直接返回
        if not result or not result[0]:
            cursor.close()
            conn.close()
            return False
        
        # 解析类型字符串
        genres = [genre.strip() for genre in result[0].split(',') if genre.strip()]
        
        # 如果没有有效类型，直接返回
        if not genres:
            cursor.close()
            conn.close()
            return False
        
        # 更新每个类型的偏好
        for genre in genres:
            # 检查是否已有此类型的偏好记录
            cursor.execute(
                "SELECT preference_score FROM user_genre_preferences WHERE user_id = %s AND genre_name = %s",
                (user_id, genre)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 已有记录，计算新的偏好分数（考虑历史评分的影响）
                current_score = float(existing[0])
                # 新分数 = 旧分数 * 0.8 + 新评分 * 0.2，让最新评分有更大影响但不完全覆盖历史
                new_score = current_score * 0.8 + rating_value * 0.2
                # 确保分数在合理范围内
                final_score = max(0.5, min(10.0, new_score))
                
                # 更新偏好记录
                cursor.execute(
                    "UPDATE user_genre_preferences SET preference_score = %s WHERE user_id = %s AND genre_name = %s",
                    (final_score, user_id, genre)
                )
            else:
                # 没有记录，直接使用当前评分创建新记录
                cursor.execute(
                    "INSERT INTO user_genre_preferences (user_id, genre_name, preference_score) VALUES (%s, %s, %s)",
                    (user_id, genre, rating_value)
                )
        
        # 提交更改
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"更新用户 {user_id} 单个电影类型偏好失败: {str(e)}")
        if conn and conn.open:
            try:
                conn.rollback()
                conn.close()
            except:
                pass
        return False

def get_user_preferred_directors(user_id: int, n: int = 5) -> List[str]:
    """获取用户喜欢的导演
    
    通过分析用户的评分历史，找出用户喜欢的导演。
    
    Args:
        user_id (int): 用户ID
        n (int): 返回的导演数量
        
    Returns:
        List[str]: 用户喜欢的导演列表
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取用户评分过的电影及其导演
        cursor.execute("""
            SELECT m.directors, ur.rating
            FROM user_ratings ur
            JOIN movies m ON ur.movie_id = m.id
            WHERE ur.user_id = %s AND m.directors IS NOT NULL
        """, (user_id,))
        
        ratings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not ratings:
            return []
            
        # 统计每个导演的加权得分
        director_scores = Counter()
        
        for directors, rating in ratings:
            if not directors:
                continue
                
            # 将评分归一化到[0,1]区间
            weight = (float(rating) - 1) / 9
            
            # 为每个导演添加加权分数
            for director in directors.split(','):
                director = director.strip()
                if director:
                    director_scores[director] += weight
                    
        # 获取得分最高的n个导演
        top_directors = [
            director for director, _ in 
            sorted(director_scores.items(), key=lambda x: x[1], reverse=True)[:n]
        ]
        
        return top_directors
        
    except Exception as e:
        logger.error(f"获取用户导演偏好失败: {str(e)}")
        return []

def get_user_preferred_actors(user_id: int, n: int = 5) -> List[str]:
    """获取用户喜欢的演员
    
    通过分析用户的评分历史，找出用户喜欢的演员。
    
    Args:
        user_id (int): 用户ID
        n (int): 返回的演员数量
        
    Returns:
        List[str]: 用户喜欢的演员列表
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取用户评分过的电影及其演员
        cursor.execute("""
            SELECT m.actors, ur.rating
            FROM user_ratings ur
            JOIN movies m ON ur.movie_id = m.id
            WHERE ur.user_id = %s AND m.actors IS NOT NULL
        """, (user_id,))
        
        ratings = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not ratings:
            return []
            
        # 统计每个演员的加权得分
        actor_scores = Counter()
        
        for actors, rating in ratings:
            if not actors:
                continue
                
            # 将评分归一化到[0,1]区间
            weight = (float(rating) - 1) / 9
            
            # 为每个演员添加加权分数
            for actor in actors.split(','):
                actor = actor.strip()
                if actor:
                    actor_scores[actor] += weight
                    
        # 获取得分最高的n个演员
        top_actors = [
            actor for actor, _ in 
            sorted(actor_scores.items(), key=lambda x: x[1], reverse=True)[:n]
        ]
        
        return top_actors
        
    except Exception as e:
        logger.error(f"获取用户演员偏好失败: {str(e)}")
        return []

def save_user_preferences(user_id: int, preferences: Dict[str, List[str]]) -> bool:
    """保存用户的偏好设置
    
    用于新用户注册时保存初始偏好设置。
    
    Args:
        user_id (int): 用户ID
        preferences (Dict[str, List[str]]): 用户偏好，包含genres、directors、actors等
        
    Returns:
        bool: 是否保存成功
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 删除旧的偏好设置
        cursor.execute("""
            DELETE FROM user_preferences 
            WHERE user_id = %s
        """, (user_id,))
        
        # 插入新的偏好设置
        for pref_type, values in preferences.items():
            for value in values:
                cursor.execute("""
                    INSERT INTO user_preferences 
                    (user_id, preference_type, preference_value) 
                    VALUES (%s, %s, %s)
                """, (user_id, pref_type, value))
                
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"成功保存用户 {user_id} 的偏好设置")
        return True
        
    except Exception as e:
        logger.error(f"保存用户偏好失败: {str(e)}")
        return False

def get_user_preferences(user_id: int) -> Dict[str, List[str]]:
    """获取用户的所有偏好设置
    
    Args:
        user_id (int): 用户ID
        
    Returns:
        Dict[str, List[str]]: 用户的所有偏好设置
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT preference_type, preference_value
            FROM user_preferences
            WHERE user_id = %s
        """, (user_id,))
        
        preferences = {}
        for pref_type, value in cursor.fetchall():
            if pref_type not in preferences:
                preferences[pref_type] = []
            preferences[pref_type].append(value)
            
        cursor.close()
        conn.close()
        
        return preferences
        
    except Exception as e:
        logger.error(f"获取用户偏好失败: {str(e)}")
        return {}

# 测试功能
if __name__ == "__main__":
    print("开始测试用户偏好模块...")
    result = batch_update_all_users_preferences()
    print(f"批量更新结果: 成功 {result[0]}/{result[1]} 个用户") 