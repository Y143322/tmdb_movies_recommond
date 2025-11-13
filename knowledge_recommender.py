"""基于知识的推荐模块

该模块实现了基于知识的推荐算法，主要用于处理冷启动问题。
包括新用户冷启动和新电影冷启动两种情况。
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
import logging
import random
import pymysql
from typing import List, Dict, Tuple, Optional

# 导入用户偏好模块
from movies_recommend.user_preferences import get_user_top_genres

# 从项目的日志模块导入日志记录器
from movies_recommend.logger import get_logger
logger = get_logger('knowledge_recommender')

from movies_recommend.extensions import get_db_connection

def get_knowledge_recommendations_for_user(user_id: int, n: int = 10, exclude_ids: List[int] = None) -> List[Tuple[int, float]]:
    """为新用户生成基于知识的推荐
    
    基于用户的初始偏好（如选择的电影类型）生成推荐。
    
    Args:
        user_id (int): 用户ID
        n (int): 推荐数量
        exclude_ids (List[int]): 需要排除的电影ID列表
        
    Returns:
        List[Tuple[int, float]]: 推荐电影列表，每个元素为(movie_id, score)
    """
    try:
        # 获取用户偏好的电影类型
        top_genres = get_user_top_genres(user_id)
        if not top_genres:
            return get_knowledge_recommendations_for_new_user(n, exclude_ids)
            
        # 构建SQL查询
        genre_conditions = []
        params = []
        for genre in top_genres:
            genre_conditions.append("genres LIKE %s")
            params.append(f"%{genre}%")
            
        genre_sql = " OR ".join(genre_conditions)
        
        # 添加排除条件
        exclude_condition = ""
        if exclude_ids and len(exclude_ids) > 0:
            exclude_condition = "AND id NOT IN (" + ",".join(map(str, exclude_ids)) + ")"
            
        # 获取符合用户偏好的电影
        conn = get_db_connection()
        cursor = conn.cursor()
            
        sql = f"""
            SELECT id, vote_average, popularity, release_date
            FROM movies
            WHERE ({genre_sql})
            {exclude_condition}
            ORDER BY vote_average * 0.7 + popularity * 0.3 DESC
            LIMIT %s
        """
        
        params.append(n * 2)  # 获取更多电影以便后续随机选择
        cursor.execute(sql, params)
        movies = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # 为每部电影计算综合得分
        recommendations = []
        for movie in movies:
            movie_id = int(movie[0])
            vote_avg = float(movie[1]) if movie[1] else 5.0
            popularity = float(movie[2]) if movie[2] else 0.0
            
            # 计算时间衰减因子
            release_date = movie[3]
            if release_date:
                years_old = (datetime.now().year - release_date.year)
                time_decay = 1.0 / (1.0 + 0.1 * years_old)  # 随时间缓慢衰减
            else:
                time_decay = 0.5
                
            # 计算综合得分
            score = (vote_avg * 0.6 + popularity * 0.2) * time_decay
            
            # 添加随机因子增加多样性
            score += np.random.normal(0, 0.5)
            
            recommendations.append((movie_id, score))
            
        # 随机选择n个推荐
        if len(recommendations) > n:
            recommendations = random.sample(recommendations, n)
            
        # 按得分排序
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations[:n]
            
    except Exception as e:
        logger.error(f"基于知识的用户推荐失败: {str(e)}")
        return []

def get_knowledge_recommendations_for_new_user(n: int = 10, exclude_ids: List[int] = None) -> List[Tuple[int, float]]:
    """为完全新用户生成推荐
    
    基于电影的整体质量和流行度生成推荐。
    
    Args:
        n (int): 推荐数量
        exclude_ids (List[int]): 需要排除的电影ID列表
        
    Returns:
        List[Tuple[int, float]]: 推荐电影列表，每个元素为(movie_id, score)
    """
    try:
        # 构建排除条件
        exclude_condition = ""
        if exclude_ids and len(exclude_ids) > 0:
            exclude_condition = f"WHERE id NOT IN ({','.join(map(str, exclude_ids))})"
            
        # 获取高质量且受欢迎的电影
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = f"""
            SELECT id, vote_average, popularity, release_date
            FROM movies
            {exclude_condition}
            ORDER BY (vote_average * popularity) DESC
            LIMIT %s
        """
            
        cursor.execute(sql, (n * 2,))  # 获取更多电影以便后续随机选择
        movies = cursor.fetchall()
        cursor.close()
        conn.close()
            
        # 为每部电影计算综合得分
        recommendations = []
        for movie in movies:
            movie_id = int(movie[0])
            vote_avg = float(movie[1]) if movie[1] else 5.0
            popularity = float(movie[2]) if movie[2] else 0.0
            
            # 计算时间衰减因子
            release_date = movie[3]
            if release_date:
                years_old = (datetime.now().year - release_date.year)
                time_decay = 1.0 / (1.0 + 0.1 * years_old)
            else:
                time_decay = 0.5
                
            # 计算综合得分
            score = (vote_avg * 0.4 + popularity * 0.4) * time_decay
            
            # 添加随机因子
            score += np.random.normal(0, 0.5)
            
            recommendations.append((movie_id, score))
            
        # 随机选择n个推荐
        if len(recommendations) > n:
            recommendations = random.sample(recommendations, n)
            
        # 按得分排序
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations[:n]
            
    except Exception as e:
        logger.error(f"新用户知识推荐失败: {str(e)}")
        return []

def get_similar_movies_by_metadata(movie_id: int, n: int = 10) -> List[Tuple[int, float]]:
    """基于电影元数据找出相似电影
    
    用于处理新电影的冷启动问题。
    
    Args:
        movie_id (int): 电影ID
        n (int): 推荐数量
        
    Returns:
        List[Tuple[int, float]]: 相似电影列表，每个元素为(movie_id, score)
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取目标电影的元数据
        cursor.execute("""
            SELECT m.genres,
                   GROUP_CONCAT(DISTINCT p_dir.name) as directors,
                   GROUP_CONCAT(DISTINCT p_cast.name) as actors
            FROM movies m
            LEFT JOIN movie_crew mcr ON m.id = mcr.movie_id AND mcr.job = 'Director'
            LEFT JOIN persons p_dir ON mcr.person_id = p_dir.id
            LEFT JOIN movie_cast mc ON m.id = mc.movie_id AND mc.cast_order < 5
            LEFT JOIN persons p_cast ON mc.person_id = p_cast.id
            WHERE m.id = %s
            GROUP BY m.id
        """, (movie_id,))
        
        movie = cursor.fetchone()
        if not movie:
            cursor.close()
            conn.close()
            return []
            
        genres = movie[0].split(',') if movie[0] else []
        directors = movie[1].split(',') if movie[1] else []
        actors = movie[2].split(',') if movie[2] else []
        
        # 构建相似度查询
        genre_conditions = []
        params = []
        
        # 类型匹配条件
        for genre in genres:
            if genre.strip():
                genre_conditions.append("m.genres LIKE %s")
                params.append(f"%{genre.strip()}%")
                
        # 构建导演和演员匹配条件
        director_conditions = []
        actor_conditions = []
        
        # 查询相似电影
        sql = """
            SELECT m.id, 
                   (
                       CASE WHEN m.genres LIKE %s THEN 0.4 ELSE 0 END +
                       CASE WHEN directors.director_names LIKE %s THEN 0.3 ELSE 0 END +
                       CASE WHEN actors.actor_names LIKE %s THEN 0.3 ELSE 0 END
                   ) * m.vote_average as similarity_score
            FROM movies m
            LEFT JOIN (
                SELECT movie_id, GROUP_CONCAT(p.name) as director_names
                FROM movie_crew mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.job = 'Director'
                GROUP BY movie_id
            ) directors ON m.id = directors.movie_id
            LEFT JOIN (
                SELECT movie_id, GROUP_CONCAT(p.name) as actor_names
                FROM movie_cast mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.cast_order < 5
                GROUP BY movie_id
            ) actors ON m.id = actors.movie_id
            WHERE m.id != %s
            AND (
        """
        
        # 添加类型条件
        if genre_conditions:
            sql += " OR ".join(genre_conditions)
        else:
            sql += "1=0"  # 如果没有类型条件，则添加一个始终为假的条件
        
        sql += """
            )
            ORDER BY similarity_score DESC
            LIMIT %s
        """
        
        # 添加额外的参数
        params = [f"%{genres[0]}%" if genres else "%", 
                 f"%{directors[0]}%" if directors else "%",
                 f"%{actors[0]}%" if actors else "%",
                 movie_id] + params + [n * 2]
        
        cursor.execute(sql, params)
        similar_movies = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # 处理结果
        recommendations = []
        for movie in similar_movies:
            movie_id = int(movie[0])
            score = float(movie[1])
            
            # 添加随机因子
            score += np.random.normal(0, 0.1)
            
            recommendations.append((movie_id, score))
            
        # 随机选择n个推荐
        if len(recommendations) > n:
            recommendations = random.sample(recommendations, n)
            
        # 按得分排序
        recommendations.sort(key=lambda x: x[1], reverse=True)
        
        return recommendations[:n]
        
    except Exception as e:
        logger.error(f"基于元数据的电影相似度推荐失败: {str(e)}")
        return []
