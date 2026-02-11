#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
电影评分推荐系统模块

实现了基于用户和基于物品的协同过滤算法、基于内容的推荐算法，用于为用户推荐可能感兴趣的电影。
"""
import os
import sys

import numpy as np
import pandas as pd
import warnings
from scipy.sparse import csr_matrix
from sklearn.neighbors import NearestNeighbors
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pymysql
import logging
import time
import json
from datetime import datetime
import random
from pathlib import Path
import math
from typing import List, Dict, Tuple, Set, Optional, Any, Union

# 导入用户偏好模块
from movies_recommend.user_preferences import get_user_top_genres

# 导入基于知识的推荐模块
from movies_recommend.knowledge_recommender import (
    get_knowledge_recommendations_for_user,
    get_knowledge_recommendations_for_new_user
)

# 导入自定义模块
from movies_recommend.similarity_calculators import SimilarityCalculatorFactory

# 仅在开发环境屏蔽部分噪声警告，避免掩盖生产问题
if os.environ.get('FLASK_ENV', 'development') == 'development':
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    warnings.filterwarnings('ignore', category=UserWarning)

# 从项目的日志模块导入日志记录器
from movies_recommend.logger import get_logger
logger = get_logger('recommender')

from movies_recommend.extensions import get_db_connection
from movies_recommend.db_utils import fetch_random_rows_by_id_range


def _extract_row_id(row):
    """兼容 tuple/dict 游标的 ID 取值。"""
    if isinstance(row, dict):
        return row.get('id')
    if isinstance(row, (list, tuple)) and row:
        return row[0]
    return None


def _fetch_random_movie_ids(cursor, limit, exclude_ids=None, extra_where='', extra_params=None):
    """按随机 ID 起点获取电影 ID，避免 ORDER BY RAND()。"""
    if limit <= 0:
        return []

    conditions = []
    params = []

    if exclude_ids:
        normalized_exclude = [int(x) for x in exclude_ids if x is not None]
        if normalized_exclude:
            placeholders = ', '.join(['%s'] * len(normalized_exclude))
            conditions.append(f'id NOT IN ({placeholders})')
            params.extend(normalized_exclude)

    if extra_where:
        conditions.append(extra_where.strip())
    if extra_params:
        params.extend(list(extra_params))

    where_clause = ' AND '.join(conditions)
    rows = fetch_random_rows_by_id_range(
        cursor=cursor,
        table='movies',
        select_columns='id',
        limit=limit,
        where_clause=where_clause,
        params=params,
    )
    return [int(movie_id) for movie_id in (_extract_row_id(row) for row in rows) if movie_id is not None]

class MovieRecommender:
    """电影评分推荐系统类"""

    def __init__(self, verbose=False):
        """初始化推荐系统
        
        Args:
            verbose (bool): 是否输出详细日志
        """
        self.user_ratings_df: pd.DataFrame = pd.DataFrame()
        self.movies_df: pd.DataFrame = pd.DataFrame()
        self.user_movie_matrix = None
        self.movie_movie_matrix = None  # 电影-电影相似度矩阵
        self.movie_features = None
        self.model = None
        self.last_update = None
        self.verbose = verbose
        self.random_factor = 0.1  # 随机因子，用于增加推荐多样性
        self.user_to_idx: Dict[Any, int] = {}
        self.movie_to_idx: Dict[Any, int] = {}

        # 尝试加载缓存的模型
        self.load_data()

    def load_data(self, verbose=None):
        """从数据库加载评分和电影数据
        
        Args:
            verbose (bool, optional): 是否输出详细日志，覆盖类实例的verbose设置
        """
        # 确定是否输出详细日志
        is_verbose = self.verbose if verbose is None else verbose
        
        try:
            conn = get_db_connection()
            if is_verbose:
                logger.info("数据库连接成功，开始加载数据")
            else:
                logger.debug("数据库连接成功，开始加载数据")

            # 加载用户评分数据
            query_ratings = """
                SELECT
                    ur.user_id, ur.movie_id, ur.rating, ur.created_at,
                    m.title, '' as actors, m.release_date as release_time
                FROM user_ratings ur
                JOIN movies m ON ur.movie_id = m.id
            """
            if is_verbose:
                logger.info(f"执行评分查询: {query_ratings}")
            self.user_ratings_df = pd.read_sql(query_ratings, conn)
            if is_verbose:
                logger.info(f"查询到 {len(self.user_ratings_df)} 条评分记录")
            else:
                logger.debug(f"查询到 {len(self.user_ratings_df)} 条评分记录")

            # 加载电影数据，增加导演和演员信息
            query_movies = """
                SELECT 
                    m.id, m.title, 
                    GROUP_CONCAT(DISTINCT CASE WHEN mc.job = 'Director' THEN p.name ELSE NULL END SEPARATOR ', ') as directors,
                    GROUP_CONCAT(DISTINCT CASE WHEN mca.cast_order <= 5 THEN p2.name ELSE NULL END SEPARATOR ', ') as actors,
                    m.release_date as release_time, m.vote_average, m.genres
                FROM movies m
                LEFT JOIN movie_crew mc ON m.id = mc.movie_id AND mc.job = 'Director'
                LEFT JOIN persons p ON mc.person_id = p.id
                LEFT JOIN movie_cast mca ON m.id = mca.movie_id AND mca.cast_order <= 5
                LEFT JOIN persons p2 ON mca.person_id = p2.id
                GROUP BY m.id
                ORDER BY m.popularity DESC
            """
            if is_verbose:
                logger.info(f"执行电影查询: {query_movies}")
            self.movies_df = pd.read_sql(query_movies, conn)
            if is_verbose:
                logger.info(f"查询到 {len(self.movies_df)} 部电影")
            else:
                logger.debug(f"查询到 {len(self.movies_df)} 部电影")

            # 查询电影总数
            query_total_movies = "SELECT COUNT(*) as total FROM movies"
            total_movies_df = pd.read_sql(query_total_movies, conn)
            total_movies = total_movies_df['total'].iloc[0] if not total_movies_df.empty else 0
            if is_verbose:
                logger.info(f"数据库中共有 {total_movies} 部电影")
            else:
                logger.debug(f"数据库中共有 {total_movies} 部电影")

            conn.close()

            # 记录最后更新时间
            self.last_update = datetime.now()

            # 数据预处理
            if not self.user_ratings_df.empty:
                self._preprocess_data(is_verbose)

            logger.info(f"数据加载完成: {len(self.user_ratings_df)} 条评分, {len(self.movies_df)} 部电影，数据库总共 {total_movies} 部电影")

        except Exception as e:
            logger.error(f"加载数据失败: {str(e)}")
            # 不要raise异常，而是记录错误并继续
            self.last_update = datetime.now()  # 设置更新时间以避免频繁重试

    def _preprocess_data(self, verbose=False):
        """预处理数据
        
        Args:
            verbose (bool): 是否输出详细日志
        """
        # 创建用户-电影评分矩阵
        if not self.user_ratings_df.empty and 'user_id' in self.user_ratings_df.columns:
            # 创建用户ID到索引的映射
            unique_users = self.user_ratings_df['user_id'].unique()
            self.user_to_idx = {user_id: idx for idx, user_id in enumerate(unique_users)}

            # 创建电影ID到索引的映射
            unique_movies = self.user_ratings_df['movie_id'].unique()
            self.movie_to_idx = {movie_id: idx for idx, movie_id in enumerate(unique_movies)}

            user_movie_df = self.user_ratings_df.pivot_table(
                index='user_id',
                columns='movie_id',
                values='rating'
            ).fillna(0)

            # 转换为稀疏矩阵以提高计算效率
            self.user_movie_matrix = csr_matrix(user_movie_df.values)

            # 构建电影特征（用于基于内容的推荐）
            self.movies_df['features'] = ''

            # 合并导演、演员、上映时间和类型作为特征
            for idx, row in self.movies_df.iterrows():
                features = []
                # 添加导演信息（权重高）
                directors = row.get('directors')
                if directors is not None and not pd.isna(directors) and str(directors).strip():
                    directors_text = str(directors)
                    # 重复3次导演名字，增加权重
                    features.append(directors_text)
                    features.append(directors_text)
                    features.append(directors_text)
                
                # 添加演员信息
                actors = row.get('actors')
                if actors is not None and not pd.isna(actors) and str(actors).strip():
                    features.append(str(actors))
                
                # 添加上映时间
                release_time = row.get('release_time')
                if release_time is not None and not pd.isna(release_time):
                    features.append(str(release_time))
                    
                # 添加电影类型
                genres = row.get('genres')
                if genres is not None and not pd.isna(genres) and str(genres).strip():
                    features.append(str(genres))

                self.movies_df.at[idx, 'features'] = ' '.join(features)

            # 使用TF-IDF向量化电影特征
            if not self.movies_df.empty and 'features' in self.movies_df.columns:
                vectorizer = TfidfVectorizer(stop_words='english')
                tfidf_matrix = vectorizer.fit_transform(self.movies_df['features'].fillna(''))
                self.movie_features = tfidf_matrix

            # 初始化KNN模型
            self.model = NearestNeighbors(metric='cosine', algorithm='brute')
            self.model.fit(self.user_movie_matrix)

            if verbose:
                logger.info("数据预处理完成")
            else:
                logger.debug("数据预处理完成")

    def check_update_needed(self, max_age_minutes=30):
        """检查是否需要更新模型"""
        if self.last_update is None:
            return True

        time_diff = (datetime.now() - self.last_update).total_seconds() / 60
        return time_diff > max_age_minutes

    def update_if_needed(self):
        """如果需要则更新模型"""
        if self.check_update_needed():
            logger.info("推荐模型需要更新")
            self.load_data()

    def get_collaborative_recommendations(self, user_id, n=10):
        """基于协同过滤获取推荐电影

        参数:
            user_id (int): 用户ID
            n (int): 推荐电影数量

        返回:
            list: 推荐电影ID列表及其分数
        """
        self.update_if_needed()

        if self.user_movie_matrix is None or self.model is None or not hasattr(self, 'user_to_idx'):
            logger.warning("推荐模型未初始化，返回多样化电影推荐")
            try:
                # 使用get_popular_movies方法获取多样化的电影推荐
                movie_ids = self.get_popular_movies(n)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 构建查询条件，获取这些电影的详细信息
                placeholders = ','.join(['%s'] * len(movie_ids))
                cursor.execute(f"""
                    SELECT id, title, vote_average, popularity 
                    FROM movies
                    WHERE id IN ({placeholders})
                """, movie_ids)
                movies = cursor.fetchall()
                cursor.close()
                conn.close()

                result = []
                for movie in movies:
                    # 计算综合评分：结合评分和热度
                    vote_avg = float(movie[2]) if movie[2] is not None else 5.0
                    popularity = float(movie[3]) if movie[3] is not None else 0.0
                    
                    # 基础评分 + 随机波动（±1.5分）让评分更加多样化
                    adjusted_score = vote_avg + (random.random() * 3 - 1.5)
                    # 确保评分在合理范围内，并保留一位小数
                    adjusted_score = round(max(5.0, min(9.5, adjusted_score)), 1)
                    
                    result.append({
                        'movie_id': int(movie[0]),
                        'title': movie[1],
                        'score': adjusted_score
                    })
                logger.info(f"返回 {len(result)} 部多样化电影")
                return result
            except Exception as e:
                logger.error(f"获取多样化电影失败: {str(e)}")
                return []

        try:
            # 检查用户是否有评分记录
            if user_id not in self.user_to_idx:
                logger.warning(f"用户 {user_id} 没有评分记录，返回多样化电影")
                # 使用get_popular_movies方法获取多样化的电影推荐
                movie_ids = self.get_popular_movies(n)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 构建查询条件
                placeholders = ','.join(['%s'] * len(movie_ids))
                cursor.execute(f"""
                    SELECT id, title, vote_average, popularity 
                    FROM movies
                    WHERE id IN ({placeholders})
                """, movie_ids)
                movies = cursor.fetchall()
                cursor.close()
                conn.close()

                result = []
                for movie in movies:
                    # 计算综合评分：结合评分和热度
                    vote_avg = float(movie[2]) if movie[2] is not None else 5.0
                    popularity = float(movie[3]) if movie[3] is not None else 0.0
                    
                    # 基础评分 + 随机波动（±1.5分）
                    adjusted_score = vote_avg + (random.random() * 3 - 1.5)
                    # 确保评分在合理范围内
                    adjusted_score = max(5.0, min(9.5, adjusted_score))
                    
                    result.append({
                        'movie_id': int(movie[0]),
                        'title': movie[1],
                        'score': adjusted_score
                    })
                logger.info(f"返回 {len(result)} 部多样化电影")
                return result
            
            # 获取用户在矩阵中的索引
            user_idx = self.user_to_idx[user_id]

            # 获取用户评分过的电影
            rated_movies = set(self.user_ratings_df[self.user_ratings_df['user_id'] == user_id]['movie_id'].tolist())

            # 找到相似用户
            distances, indices = self.model.kneighbors(
                self.user_movie_matrix[user_idx].reshape(1, -1),
                n_neighbors=min(10, len(self.user_to_idx))
            )

            similar_users_indices = indices.flatten()[1:]  # 排除自己

            # 将索引转换回用户ID
            similar_users = [list(self.user_to_idx.keys())[list(self.user_to_idx.values()).index(idx)] for idx in similar_users_indices]

            # 获取相似用户评分的电影
            similar_user_movies = pd.DataFrame(
                self.user_ratings_df[self.user_ratings_df['user_id'].isin(similar_users)]
            ).copy()

            # 排除用户已评分的电影
            recommendations = pd.DataFrame(
                similar_user_movies[
                    ~similar_user_movies['movie_id'].isin(list(rated_movies))
                ]
            ).copy()

            if recommendations.empty:
                return []

            # 计算推荐分数
            recommendations = recommendations.groupby('movie_id').agg({
                'rating': 'mean',
                'title': 'first'
            }).reset_index()

            # 按评分排序并选择前n个
            recommendations = recommendations.sort_values('rating', ascending=False).head(n*2)  # 获取更多候选电影，以便后面调整

            # 获取用户的类型偏好
            user_genre_preferences = {}
            try:
                top_genres = get_user_top_genres(user_id)
                for genre, score in top_genres:
                    user_genre_preferences[genre] = score
                logger.info(f"获取到用户 {user_id} 的 {len(user_genre_preferences)} 个类型偏好")
            except Exception as e:
                logger.warning(f"获取用户类型偏好失败，使用原始推荐: {e}")

            # 构建结果，根据用户类型偏好调整分数
            result = []
            
            # 创建电影ID到类型的映射
            movie_id_to_genres = {}
            for movie_id in recommendations['movie_id'].tolist():
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT genres FROM movies WHERE id = %s", (movie_id,))
                    genres_data = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    
                    if genres_data and genres_data[0]:
                        movie_id_to_genres[movie_id] = [g.strip() for g in genres_data[0].split(',') if g.strip()]
                except Exception as e:
                    logger.warning(f"获取电影 {movie_id} 类型失败: {e}")
                    movie_id_to_genres[movie_id] = []
            
            # 为每部电影计算调整后的分数
            for _, row in recommendations.iterrows():
                movie_id = int(row['movie_id'])
                base_score = float(row['rating'])
                adjusted_score = base_score
                
                # 如果有类型偏好和电影类型信息，调整分数
                if user_genre_preferences and movie_id in movie_id_to_genres:
                    movie_genres = movie_id_to_genres[movie_id]
                    # 计算类型匹配度加权调整
                    if movie_genres:
                        genre_match_boost = 0
                        matched_genres = 0
                        for genre in movie_genres:
                            if genre in user_genre_preferences:
                                # 类型偏好分数转换为0-1范围的提升系数
                                genre_weight = (user_genre_preferences[genre] - 5) / 5
                                genre_match_boost += max(0, genre_weight)
                                matched_genres += 1
                        
                        # 有匹配的类型时，应用提升系数
                        if matched_genres > 0:
                            # 调整系数，避免过度提升
                            boost_factor = genre_match_boost / matched_genres
                            # 应用提升（最多提升20%）
                            adjusted_score = base_score * (1 + min(0.2, boost_factor))
                
                # 添加一些随机扰动，让推荐结果更多样化（±0.5分）
                adjusted_score += random.random() - 0.5
                
                result.append({
                    'movie_id': movie_id,
                    'title': row['title'],
                    'score': adjusted_score,
                    'original_score': base_score  # 保留原始分数以便比较
                })
            
            # 按调整后的分数重新排序
            result.sort(key=lambda x: x['score'], reverse=True)
            
            # 截取前n个结果
            result = result[:n]

            # 如果推荐数量不足，添加多样化的热门电影
            if len(result) < n:
                # 获取多样化热门电影
                additional_movie_ids = self.get_popular_movies(n - len(result))
                
                # 排除已经推荐的电影
                recommended_ids = [item['movie_id'] for item in result]
                additional_movie_ids = [m_id for m_id in additional_movie_ids if m_id not in recommended_ids and m_id not in rated_movies]
                
                if additional_movie_ids:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # 查询这些电影的信息
                    placeholders = ','.join(['%s'] * len(additional_movie_ids))
                    cursor.execute(f"""
                        SELECT id, title, vote_average 
                        FROM movies 
                        WHERE id IN ({placeholders})
                    """, additional_movie_ids)
                    
                    additional_movies = cursor.fetchall()
                    cursor.close()
                    conn.close()
                    
                    # 添加到结果列表
                    for movie in additional_movies:
                        # 添加一些随机性到评分
                        score = float(movie[2]) if movie[2] else 7.0
                        # 评分波动 ±1分
                        adjusted_score = score + (random.random() * 2 - 1)
                        # 确保评分在合理范围
                        adjusted_score = max(5.0, min(9.0, adjusted_score))
                        
                        result.append({
                            'movie_id': int(movie[0]),
                            'title': movie[1],
                            'score': adjusted_score
                        })

            return result

        except Exception as e:
            logger.error(f"协同过滤推荐失败: {str(e)}")
            # 出错时返回多样化热门电影
            try:
                # 使用我们的多样化电影获取方法
                movie_ids = self.get_popular_movies(n)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 构建查询条件
                placeholders = ','.join(['%s'] * len(movie_ids))
                cursor.execute(f"""
                    SELECT id, title, vote_average, popularity 
                    FROM movies
                    WHERE id IN ({placeholders})
                """, movie_ids)
                movies = cursor.fetchall()
                cursor.close()
                conn.close()

                result = []
                for movie in movies:
                    # 计算多样化评分
                    vote_avg = float(movie[2]) if movie[2] is not None else 5.0
                    popularity = float(movie[3]) if movie[3] is not None else 0.0
                    
                    # 基础评分 + 随机波动
                    adjusted_score = vote_avg + (random.random() * 2 - 1)
                    # 确保评分在合理范围内
                    adjusted_score = max(5.0, min(9.0, adjusted_score))
                    
                    result.append({
                        'movie_id': int(movie[0]),
                        'title': movie[1],
                        'score': adjusted_score
                    })
                logger.info(f"协同过滤失败，返回 {len(result)} 部多样化电影")
                return result
            except Exception as e2:
                logger.error(f"获取多样化电影失败: {str(e2)}")
                return []

    def get_content_based_recommendations(self, user_id, n=10):
        """基于内容的推荐算法
        
        通过分析电影的特征（类型、导演、演员、剧情等）来推荐相似的电影。
        
        Args:
            user_id (int): 用户ID
            n (int): 推荐数量
            
        Returns:
            list: 推荐电影列表，每个元素为(movie_id, score)
        """
        try:
            if self.user_ratings_df.empty or self.movies_df.empty:
                return []

            # 获取用户评分过的电影
            user_ratings = self.user_ratings_df[
                self.user_ratings_df['user_id'] == user_id
            ]
            
            if user_ratings.empty:
                return []
                
            # 获取电影特征
            movie_features = self._extract_movie_features()
            if movie_features is None:
                return []
                
            # 构建用户画像
            user_profile = self._build_user_profile(user_ratings, movie_features)
            if user_profile is None:
                return []
                
            # 计算用户画像与所有电影的相似度
            similarities = cosine_similarity([user_profile], movie_features)[0]
            
            # 获取用户未评分的电影
            rated_movies = set(user_ratings['movie_id'])
            all_movies = set(self.movies_df['id'])
            unrated_movies = list(all_movies - rated_movies)
            
            # 为每个未评分电影计算推荐分数
            movie_scores = []
            for movie_id in unrated_movies:
                movie_idx = self.movie_to_idx.get(movie_id)
                if movie_idx is not None:
                    similarity = similarities[movie_idx]
                    # 添加随机因子以增加多样性
                    random_boost = np.random.normal(0, self.random_factor)
                    score = similarity + random_boost
                    movie_scores.append((movie_id, score))
            
            # 排序并返回前n个推荐
            movie_scores.sort(key=lambda x: x[1], reverse=True)
            return movie_scores[:n]
            
        except Exception as e:
            logger.error(f"基于内容的推荐失败: {str(e)}")
            return []
            
    def _extract_movie_features(self):
        """提取电影特征
        
        将电影的类型、导演、演员、剧情等信息转换为特征向量。
        
        Returns:
            numpy.ndarray: 电影特征矩阵
        """
        try:
            # 获取电影详细信息
            movies = self.movies_df.copy()
            
            # 合并所有文本特征
            movies['features'] = movies.apply(
                lambda row: ' '.join(filter(None, [
                    str(row.get('genres', '')),
                    str(row.get('directors', '')),
                    str(row.get('actors', '')),
                    str(row.get('overview', ''))
                ])),
                axis=1
            )
            
            # 使用TF-IDF向量化文本特征
            tfidf = TfidfVectorizer(
                stop_words='english',
                max_features=5000,
                ngram_range=(1, 2)
            )
            
            # 转换为特征矩阵
            feature_matrix = tfidf.fit_transform(movies['features'])
            to_array = getattr(feature_matrix, 'toarray', None)
            if callable(to_array):
                return np.asarray(to_array())

            return np.asarray(feature_matrix)
            
        except Exception as e:
            logger.error(f"提取电影特征失败: {str(e)}")
            return None
            
    def _build_user_profile(self, user_ratings, movie_features):
        """构建用户画像
        
        通过用户评分过的电影特征的加权平均来构建用户画像。
        
        Args:
            user_ratings (pandas.DataFrame): 用户评分数据
            movie_features (numpy.ndarray): 电影特征矩阵
            
        Returns:
            numpy.ndarray: 用户画像向量
        """
        try:
            if movie_features is None or len(movie_features) == 0:
                return None
                
            # 初始化用户画像向量
            user_profile = np.zeros(movie_features.shape[1])
            weight_sum = 0
            
            # 对每部评分过的电影进行加权
            for _, rating in user_ratings.iterrows():
                movie_id = rating['movie_id']
                movie_idx = self.movie_to_idx.get(movie_id)
                
                if movie_idx is not None:
                    # 将评分归一化到[0,1]区间
                    weight = (rating['rating'] - 1) / 9  # 假设评分范围是1-10
                    user_profile += weight * movie_features[movie_idx]
                    weight_sum += weight
            
            # 归一化用户画像
            if weight_sum > 0:
                user_profile /= weight_sum
                
            return user_profile
            
        except Exception as e:
            logger.error(f"构建用户画像失败: {str(e)}")
            return None

    def save_recommendations(self, user_id, recommendations, recommendation_type):
        """保存推荐结果到数据库

        参数:
            user_id (int): 用户ID
            recommendations (list): 推荐电影列表
            recommendation_type (str): 推荐类型
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # 检查是否为管理员
            cursor.execute('SELECT id FROM admininfo WHERE id = %s', (user_id,))
            admin = cursor.fetchone()
            if admin:
                logger.info(f"用户 {user_id} 是管理员，不保存推荐")
                cursor.close()
                conn.close()
                return

            # 检查用户是否存在
            cursor.execute('SELECT id FROM userinfo WHERE id = %s', (user_id,))
            user = cursor.fetchone()
            if not user:
                logger.info(f"用户 {user_id} 不存在，不保存推荐")
                cursor.close()
                conn.close()
                return

            # 使用INSERT ... ON DUPLICATE KEY UPDATE语法替代先删除再插入的方式
            for rec in recommendations:
                # 检查rec的类型，支持字典和整数两种格式
                if isinstance(rec, dict):
                    movie_id = rec.get('movie_id', rec.get('id'))
                    score = rec.get('score', 0.0)
                elif isinstance(rec, (int, str)):
                    # 如果是整数或字符串，直接作为movie_id
                    movie_id = int(rec)
                    score = 0.0
                else:
                    logger.warning(f"推荐项格式不支持: {rec}")
                    continue
                    
                if movie_id is None:
                    logger.warning(f"推荐项缺少movie_id或id: {rec}")
                    continue
                cursor.execute(
                    """
                    INSERT INTO recommendations (user_id, movie_id, score, recommendation_type) 
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                    score = VALUES(score),
                    created_at = CURRENT_TIMESTAMP
                    """,
                    (user_id, movie_id, score, recommendation_type)
                )

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"已为用户 {user_id} 保存 {len(recommendations)} 条 {recommendation_type} 类型推荐")

        except Exception as e:
            logger.error(f"保存推荐失败: {str(e)}")

    def get_user_recommendations(self, user_id, n=10):
        """获取用户的电影推荐
        
        整合混合推荐策略，并根据用户状态选择合适的推荐方法：
        - 新用户使用基于知识的推荐
        - 有评分记录的用户使用混合推荐策略
        - 推荐失败时回退到热门电影推荐
        
        Args:
            user_id (int): 用户ID
            n (int): 推荐数量
            
        Returns:
            list: 推荐电影列表，每个元素为字典格式
        """
        try:
            # 检查是否需要更新推荐模型
            if self.check_update_needed():
                self.load_data()

            if self.user_ratings_df.empty:
                recommendations = get_knowledge_recommendations_for_user(user_id, n)
                return [
                    {'movie_id': movie_id, 'score': score}
                    for movie_id, score in recommendations
                ]

            # 获取用户评分记录
            user_ratings = self.user_ratings_df[
                self.user_ratings_df['user_id'] == user_id
            ]

            # 根据用户状态选择推荐策略
            if user_ratings.empty:
                # 新用户使用基于知识的推荐
                logger.info(f"用户 {user_id} 没有评分记录，使用基于知识的推荐")
                recommendations = get_knowledge_recommendations_for_user(user_id, n)
                # 转换为字典格式
                recommendations = [
                    {'movie_id': movie_id, 'score': score}
                    for movie_id, score in recommendations
                ]
            else:
                # 使用混合推荐策略
                logger.info(f"用户 {user_id} 使用混合推荐策略")
                hybrid_recs = self.get_hybrid_recommendations(user_id, n)
                # 转换为字典格式
                recommendations = [
                    {'movie_id': movie_id, 'score': score}
                    for movie_id, score in hybrid_recs
                ]

            # 如果推荐结果不足，补充热门电影
            if len(recommendations) < n:
                logger.info(f"推荐结果不足 {n} 个，补充热门电影")
                exclude_ids = [rec['movie_id'] for rec in recommendations]
                popular_recs = self._get_popular_movies_excluding(
                    n - len(recommendations),
                    exclude_ids,
                    user_id
                )
                recommendations.extend(popular_recs)

            # 保存推荐结果到数据库
            if recommendations:
                self.save_recommendations(user_id, recommendations, 'hybrid')

            return recommendations[:n]

        except Exception as e:
            logger.error(f"获取推荐失败: {str(e)}")
            # 发生错误时返回热门电影
            return self.get_popular_movies_as_recommendations(n)

    def get_popular_movies_as_recommendations(self, n=10):
        """获取热门电影作为推荐格式

        参数:
            n (int): 推荐数量

        返回:
            list: 推荐电影详情列表
        """
        try:
            movie_ids = self.get_popular_movies(n)
            return self.get_movie_details(movie_ids)
        except Exception as e:
            logger.error(f"获取热门电影推荐失败: {e}")
            return []

    def _get_popular_movies_excluding(self, n, exclude_ids, user_id=None):
        """获取热门电影，排除指定的电影ID

        参数:
            n (int): 需要的电影数量
            exclude_ids (list): 要排除的电影ID列表
            user_id (int): 用户ID（用于排除已评分电影）

        返回:
            list: 电影详情列表
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 构建排除条件
            all_exclude_ids = exclude_ids.copy()
            
            # 如果提供了用户ID，排除用户已评分的电影
            if user_id:
                cursor.execute("SELECT movie_id FROM user_ratings WHERE user_id = %s", (user_id,))
                rated_movies = [row[0] for row in cursor.fetchall()]
                all_exclude_ids.extend(rated_movies)
            
            # 去重
            all_exclude_ids = list(set(all_exclude_ids))

            # 获取热门电影
            movie_ids = _fetch_random_movie_ids(cursor, limit=n, exclude_ids=all_exclude_ids)
            cursor.close()
            conn.close()

            return self.get_movie_details(movie_ids)

        except Exception as e:
            logger.error(f"获取排除特定电影的热门电影失败: {e}")
            return []

    def get_movie_details(self, movie_ids):
        """获取电影详细信息

        参数:
            movie_ids (list): 电影ID列表

        返回:
            list: 包含电影详细信息的字典列表
        """
        if not movie_ids:
            return []

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            movie_details = []
            for movie_id in movie_ids:
                # 获取基本电影信息
                cursor.execute(
                    "SELECT id, title, poster_path as image, vote_average, vote_count, genres, release_date FROM movies WHERE id = %s",
                    (movie_id,)
                )
                movie = cursor.fetchone()
                
                if movie:
                    # 获取导演信息
                    cursor.execute("""
                        SELECT p.name
                        FROM movie_crew mc
                        JOIN persons p ON mc.person_id = p.id
                        WHERE mc.movie_id = %s AND mc.job = 'Director'
                        ORDER BY p.popularity DESC
                    """, (movie_id,))
                    directors_raw = cursor.fetchall()
                    directors = [director[0] for director in directors_raw] if directors_raw else []
                    
                    # 获取主要演员
                    cursor.execute("""
                        SELECT p.name
                        FROM movie_cast mc
                        JOIN persons p ON mc.person_id = p.id
                        WHERE mc.movie_id = %s
                        ORDER BY mc.cast_order
                        LIMIT 5
                    """, (movie_id,))
                    actors_raw = cursor.fetchall()
                    actors = [actor[0] for actor in actors_raw] if actors_raw else []
                    
                    # 处理海报URL，添加基础URL
                    image_url = movie[2]
                    if image_url and not image_url.startswith(('http://', 'https://')):
                        image_url = f"https://image.tmdb.org/t/p/w500{image_url}"
                    elif not image_url:
                        # 如果没有海报，使用默认海报
                        image_url = "/static/img/default-movie-placeholder.png"
                        
                    # 获取类型列表
                    genres = []
                    if movie[5] and movie[5].strip():
                        genres = [genre.strip() for genre in movie[5].split(',') if genre.strip()]
                    
                    # 获取发行年份
                    release_year = None
                    if movie[6]:
                        try:
                            release_year = str(movie[6]).split('-')[0]
                        except:
                            pass
                            
                    movie_details.append({
                        'id': movie[0],
                        'movie_id': movie[0],  # 添加movie_id，保持与id相同
                        'title': movie[1],
                        'image': image_url,
                        'score': round(float(movie[3]), 1) if movie[3] else 0.0,
                        'vote_count': movie[4],
                        'genres': genres,
                        'release_year': release_year,
                        'directors': directors,
                        'actors': actors
                    })

            cursor.close()
            conn.close()

            return movie_details

        except Exception as e:
            logger.error(f"获取电影详情失败: {str(e)}")
            return []

    def get_recommendations(self, user_id, n=10):
        """兼容历史调用，转调统一实现。"""
        return self.get_user_recommendations(user_id, n)

    def get_popular_movies(self, n=10):
        """获取热门电影ID列表

        参数:
            n (int): 电影数量

        返回:
            list: 热门电影ID列表
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 使用更新后的热度值作为主要排序依据，并结合评分和观看时间
            cursor.execute("""
                SELECT id FROM movies
                WHERE vote_count > 20
                ORDER BY 
                    popularity * 0.6 + 
                    vote_average * 0.3 + 
                    (DATEDIFF(CURRENT_DATE, release_date) < 180) * 0.1
                    DESC
                LIMIT %s
            """, (n*2,))  # 获取两倍的结果再随机筛选
            
            all_movie_ids = [int(row[0]) for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            # 随机打乱后取前n个，增加多样性
            if all_movie_ids:
                random.shuffle(all_movie_ids)
                movie_ids = all_movie_ids[:n]
                return movie_ids
            else:
                # 如果没有结果，使用备用查询
                conn = get_db_connection()
                cursor = conn.cursor()
                movie_ids = _fetch_random_movie_ids(cursor, limit=n)
                cursor.close()
                conn.close()
                return movie_ids

        except Exception as e:
            logger.error(f"获取热门电影失败: {str(e)}")
            # 出错时返回空列表而不是抛出异常
            return []

    def calculate_item_similarity(self):
        """计算电影之间的相似度矩阵（基于物品的协同过滤）"""
        if self.user_movie_matrix is None:
            return

        # 转置用户-电影矩阵得到电影-用户矩阵
        movie_user_matrix = self.user_movie_matrix.T.tocsr()
        
        # 计算电影之间的余弦相似度
        self.movie_movie_matrix = cosine_similarity(movie_user_matrix)
        
        # 将对角线元素设为0，避免推荐电影本身
        np.fill_diagonal(self.movie_movie_matrix, 0)
        
        logger.info(f"已计算电影相似度矩阵，形状: {self.movie_movie_matrix.shape}")

    def get_item_based_recommendations(self, user_id, n=10):
        """基于物品的协同过滤推荐
        
        Args:
            user_id (int): 用户ID
            n (int): 推荐数量
            
        Returns:
            list: 推荐电影列表，每个元素为(movie_id, predicted_rating)
        """
        if self.movie_movie_matrix is None:
            self.calculate_item_similarity()
            
        if self.movie_movie_matrix is None:
            return []

        try:
            if self.user_ratings_df.empty or self.movies_df.empty:
                return []

            # 获取用户评分过的电影
            user_ratings = self.user_ratings_df[self.user_ratings_df['user_id'] == user_id]
            if user_ratings.empty:
                return []

            # 获取用户未评分的电影
            rated_movies = set(user_ratings['movie_id'])
            all_movies = set(self.movies_df['id'])
            unrated_movies = list(all_movies - rated_movies)

            # 为每个未评分电影计算预测评分
            predictions = []
            for movie_id in unrated_movies:
                # 获取当前电影与所有电影的相似度
                movie_idx = self.movie_to_idx.get(movie_id)
                if movie_idx is None:
                    continue

                # 获取用户评分过的电影与当前电影的相似度
                similarities = self.movie_movie_matrix[movie_idx]
                
                # 获取用户对评分过的电影的评分
                user_movie_ratings = user_ratings.set_index('movie_id')['rating']
                
                # 计算预测评分（加权平均）
                weighted_sum = 0
                similarity_sum = 0
                
                for rated_movie_id in rated_movies:
                    rated_movie_idx = self.movie_to_idx.get(rated_movie_id)
                    if rated_movie_idx is not None:
                        similarity = similarities[rated_movie_idx]
                        if similarity > 0:  # 只考虑正相似度
                            rating = user_movie_ratings.get(rated_movie_id, 0)
                            weighted_sum += similarity * rating
                            similarity_sum += similarity

                # 添加随机因子以增加多样性
                random_boost = np.random.normal(0, self.random_factor)
                
                if similarity_sum > 0:
                    predicted_rating = (weighted_sum / similarity_sum) + random_boost
                    predictions.append((movie_id, predicted_rating))

            # 排序并返回前n个推荐
            predictions.sort(key=lambda x: x[1], reverse=True)
            return predictions[:n]

        except Exception as e:
            logger.error(f"基于物品的推荐失败: {str(e)}")
            return []

    def get_hybrid_recommendations(self, user_id, n=10):
        """混合推荐策略
        
        结合基于用户的协同过滤、基于物品的协同过滤和基于内容的推荐，
        使用加权融合的方式生成最终推荐结果。
        
        Args:
            user_id (int): 用户ID
            n (int): 推荐数量
            
        Returns:
            list: 推荐电影列表
        """
        try:
            if self.user_ratings_df.empty:
                return []

            # 获取各种推荐结果
            user_cf_recs = self.get_collaborative_recommendations(user_id, n=n)
            item_cf_recs = self.get_item_based_recommendations(user_id, n=n)
            content_recs = self.get_content_based_recommendations(user_id, n=n)

            # 定义各种推荐方法的权重
            weights = {
                'user_cf': 0.4,
                'item_cf': 0.3,
                'content': 0.3
            }

            # 合并所有推荐结果
            movie_scores = {}
            
            # 处理基于用户的协同过滤结果 (字典格式)
            for rec in user_cf_recs:
                movie_id = rec.get('movie_id', rec.get('id'))
                score = rec.get('score', 0)
                if movie_id not in movie_scores:
                    movie_scores[movie_id] = 0
                movie_scores[movie_id] += score * weights['user_cf']

            # 处理基于物品的协同过滤结果 (元组格式)
            for movie_id, score in item_cf_recs:
                if movie_id not in movie_scores:
                    movie_scores[movie_id] = 0
                movie_scores[movie_id] += score * weights['item_cf']

            # 处理基于内容的推荐结果 (元组格式)
            for movie_id, score in content_recs:
                if movie_id not in movie_scores:
                    movie_scores[movie_id] = 0
                movie_scores[movie_id] += score * weights['content']

            # 获取用户已评分的电影
            rated_movies = set(self.user_ratings_df[
                self.user_ratings_df['user_id'] == user_id
            ]['movie_id'])

            # 过滤掉已评分的电影
            movie_scores = {
                movie_id: score 
                for movie_id, score in movie_scores.items() 
                if movie_id not in rated_movies
            }

            # 应用多样性优化
            final_recommendations = self._apply_diversity_optimization(
                movie_scores, user_id, n
            )

            return final_recommendations

        except Exception as e:
            logger.error(f"混合推荐失败: {str(e)}")
            return []

    def _apply_diversity_optimization(self, movie_scores, user_id, n):
        """应用多样性优化策略
        
        Args:
            movie_scores (dict): 电影ID到分数的映射
            user_id (int): 用户ID
            n (int): 需要返回的推荐数量
            
        Returns:
            list: 优化后的推荐列表，每个元素为(movie_id, score)元组
        """
        try:
            # 获取电影详细信息
            movie_ids = list(movie_scores.keys())
            movie_details_list = self.get_movie_details(movie_ids)
            
            # 转换为字典，便于按ID查找
            movie_details = {}
            for movie in movie_details_list:
                movie_id = movie.get('id') or movie.get('movie_id')
                if movie_id:
                    movie_details[movie_id] = movie
            
            # 初始化计数器
            director_count = {}
            actor_count = {}
            genre_count = {}
            
            # 设置多样性阈值
            MAX_SAME_DIRECTOR = 2
            MAX_SAME_ACTOR = 3
            MAX_SAME_GENRE = 4
            
            final_recommendations = []
            
            # 按分数排序的电影ID列表
            sorted_movies = sorted(
                movie_scores.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # 遍历排序后的电影
            for movie_id, score in sorted_movies:
                if len(final_recommendations) >= n:
                    break
                    
                movie = movie_details.get(movie_id, {})
                
                # 检查导演限制
                directors = movie.get('directors', [])
                if isinstance(directors, str):
                    directors = [directors]
                
                director_exceeded = False
                for director in directors:
                    if director and director_count.get(director, 0) >= MAX_SAME_DIRECTOR:
                        director_exceeded = True
                        break
                if director_exceeded:
                    continue
                    
                # 检查演员限制
                actors = movie.get('actors', [])
                if isinstance(actors, str):
                    actors = actors.split(',')
                
                actor_exceeded = False
                for actor in actors:
                    if actor and actor_count.get(actor.strip(), 0) >= MAX_SAME_ACTOR:
                        actor_exceeded = True
                        break
                if actor_exceeded:
                    continue
                    
                # 检查类型限制
                genres = movie.get('genres', [])
                if isinstance(genres, str):
                    genres = genres.split(',')
                
                genre_exceeded = False
                for genre in genres:
                    if genre and genre_count.get(genre.strip(), 0) >= MAX_SAME_GENRE:
                        genre_exceeded = True
                        break
                if genre_exceeded:
                    continue
                
                # 更新计数器
                for director in directors:
                    if director:
                        director_count[director] = director_count.get(director, 0) + 1
                for actor in actors:
                    if actor:
                        actor = actor.strip()
                        actor_count[actor] = actor_count.get(actor, 0) + 1
                for genre in genres:
                    if genre:
                        genre = genre.strip()
                        genre_count[genre] = genre_count.get(genre, 0) + 1
                
                # 添加到最终推荐列表
                final_recommendations.append((movie_id, score))
            
            return final_recommendations

        except Exception as e:
            logger.error(f"应用多样性优化失败: {str(e)}")
            return sorted(
                movie_scores.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:n]

_recommender = MovieRecommender()

def get_recommendations_for_user(user_id, n=5, refresh=False, exclude_ids=None):
    """获取用户推荐电影

    参数:
        user_id (int): 用户ID
        n (int): 推荐电影数量
        refresh (bool): 是否强制刷新推荐，为True时会获取新的推荐
        exclude_ids (list): 需要排除的电影ID列表

    返回:
        list: 推荐电影ID列表
    """
    try:
        from movies_recommend.extensions import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查用户是否为管理员
        cursor.execute('SELECT id FROM admininfo WHERE id = %s', (user_id,))
        admin = cursor.fetchone()
        
        # 如果是管理员用户，直接返回随机电影，不查询或生成推荐
        if admin:
            logger.info(f"用户 {user_id} 是管理员，使用随机电影推荐")
            try:
                # 构建排除条件
                exclude_condition = ""
                params = []
                if exclude_ids and len(exclude_ids) > 0:
                    exclude_condition = "WHERE id NOT IN (" + ", ".join(["%s"] * len(exclude_ids)) + ")"
                    params = exclude_ids
                
                # 获取随机电影
                normalized_exclude = [int(x) for x in params if x is not None]
                movie_ids = _fetch_random_movie_ids(cursor, limit=n, exclude_ids=normalized_exclude)
                cursor.close()
                conn.close()
                return movie_ids
            except Exception as e:
                logger.error(f"获取管理员随机电影推荐失败: {e}")
                cursor.close()
                conn.close()
                return []
        
        # 确保exclude_ids是列表
        if exclude_ids is None:
            exclude_ids = []
        elif isinstance(exclude_ids, (int, str)):
            exclude_ids = [exclude_ids]
        elif not isinstance(exclude_ids, list):
            exclude_ids = list(exclude_ids) if hasattr(exclude_ids, '__iter__') else []
        
        logger.info(f"获取用户 {user_id} 的推荐 (n={n}, refresh={refresh}, exclude={len(exclude_ids)}个ID)")

        # 如果需要刷新，或者没有缓存的推荐，则生成新的推荐
        if refresh:
            logger.info(f"用户 {user_id} 请求刷新推荐")
            
            # 如果缓存中有旧的推荐，先清除所有类型的推荐
            cursor.execute("DELETE FROM recommendations WHERE user_id = %s", (user_id,))
            conn.commit()
            
            # 使用全局推荐器实例，避免重复加载数据；如有必要会自动检查更新
            try:
                _recommender.update_if_needed()
                
                # 获取新的推荐，考虑排除的电影ID
                user_recommendations = _recommender.get_user_recommendations(user_id, n + len(exclude_ids))
                # 提取电影ID，支持字典和整数两种格式
                movie_ids = []
                for rec in user_recommendations:
                    if isinstance(rec, dict) and 'movie_id' in rec:
                        movie_ids.append(rec['movie_id'])
                    elif isinstance(rec, (int, str)):
                        movie_ids.append(int(rec))
                
                # 排除指定的电影ID
                if exclude_ids and movie_ids:
                    # 确保exclude_ids中的元素都是整数
                    exclude_ids_int = [int(x) for x in exclude_ids if x is not None]
                    movie_ids = [m_id for m_id in movie_ids if m_id not in exclude_ids_int]
                    logger.info(f"排除 {len(exclude_ids_int)} 个电影ID后，剩余 {len(movie_ids)} 个推荐")
            except Exception as e:
                logger.error(f"无法获取用户推荐: {e}")
                # 出现异常时，尝试获取热门电影作为后备
                movie_ids = []
                try:
                    # 直接从数据库获取热门电影
                    all_ids = _fetch_random_movie_ids(
                        cursor,
                        limit=n + len(exclude_ids),
                        extra_where='vote_count > %s',
                        extra_params=[50],
                    )
                    # 确保exclude_ids中的元素都是整数
                    exclude_ids_int = [int(x) for x in exclude_ids if x is not None]
                    movie_ids = [m_id for m_id in all_ids if m_id not in exclude_ids_int]
                    logger.info(f"使用热门电影作为后备，获取到 {len(movie_ids)} 个推荐")
                except Exception as e2:
                    logger.error(f"获取热门电影失败: {e2}")
        else:
            # 检查数据库中是否有缓存的推荐
            try:
                # 先查询用户的推荐缓存记录数量
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM recommendations 
                    WHERE user_id = %s
                """, (user_id,))
                result = cursor.fetchone()
                
                # 判断用户是否有缓存的推荐（记录数不为0）
                if result and result[0] > 0:
                    # 如果有缓存的推荐，获取具体推荐内容
                    cursor.execute("""
                        SELECT movie_id FROM recommendations 
                        WHERE user_id = %s
                        ORDER BY score DESC
                        LIMIT %s
                    """, (user_id, n + len(exclude_ids)))
                    movie_results = cursor.fetchall()
                    
                    # 处理推荐结果
                    all_movie_ids = [int(row[0]) for row in movie_results]
                    # 确保exclude_ids中的元素都是整数
                    exclude_ids_int = [int(x) for x in exclude_ids if x is not None]
                    movie_ids = [m_id for m_id in all_movie_ids if m_id not in exclude_ids_int]
                    logger.info(f"从缓存中获取用户 {user_id} 的 {len(movie_ids)} 条推荐")
                else:
                    # 没有缓存，使用全局实例生成新推荐，避免重复加载数据
                    logger.info(f"用户 {user_id} 没有缓存的推荐，使用全局推荐器生成")
                    try:
                        _recommender.update_if_needed()
                        user_recommendations = _recommender.get_user_recommendations(user_id, n + len(exclude_ids))
                        # 提取电影ID，支持字典和整数两种格式
                        movie_ids = []
                        for rec in user_recommendations:
                            if isinstance(rec, dict) and 'movie_id' in rec:
                                movie_ids.append(rec['movie_id'])
                            elif isinstance(rec, (int, str)):
                                movie_ids.append(int(rec))
                        
                        # 排除指定的电影ID
                        if exclude_ids and movie_ids:
                            # 确保exclude_ids中的元素都是整数
                            exclude_ids_int = [int(x) for x in exclude_ids if x is not None]
                            movie_ids = [m_id for m_id in movie_ids if m_id not in exclude_ids_int]
                    except Exception as e:
                        logger.error(f"无法获取用户推荐: {e}")
                        # 出错时使用热门电影
                        movie_ids = []
                        all_ids = _fetch_random_movie_ids(cursor, limit=n + len(exclude_ids))
                        # 确保exclude_ids中的元素都是整数
                        exclude_ids_int = [int(x) for x in exclude_ids if x is not None]
                        movie_ids = [m_id for m_id in all_ids if m_id not in exclude_ids_int]
                        logger.info(f"使用热门电影作为后备，获取到 {len(movie_ids)} 个推荐")
            except Exception as e:
                logger.error(f"无法获取缓存推荐: {e}")
                # 异常情况下返回热门电影
                movie_ids = []
                try:
                    movie_ids = _fetch_random_movie_ids(cursor, limit=n)
                except Exception as e2:
                    logger.error(f"获取热门电影失败: {e2}")
        
        # 关闭数据库连接
        cursor.close()
        conn.close()
        
        # 如果推荐数量少于请求数量，补充随机电影
        if len(movie_ids) < n:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # 构建排除条件：已推荐和需要排除的电影ID
                all_excluded_ids = list(movie_ids) + list(exclude_ids)

                rated_movie_ids = []
                cursor.execute('SELECT movie_id FROM user_ratings WHERE user_id = %s', (user_id,))
                rated_movie_ids = [int(_extract_row_id(row)) for row in cursor.fetchall() if _extract_row_id(row) is not None]

                random_movie_ids = _fetch_random_movie_ids(
                    cursor,
                    limit=n - len(movie_ids),
                    exclude_ids=all_excluded_ids + rated_movie_ids,
                )
                cursor.close()
                conn.close()
                
                # 添加随机电影到推荐列表
                for random_id in random_movie_ids:
                    movie_ids.append(int(random_id))
                
                logger.info(f"补充 {len(random_movie_ids)} 部随机电影，最终推荐 {len(movie_ids)} 部电影")
            except Exception as e:
                logger.error(f"补充随机电影失败: {e}")
        
        # 确保不返回超过请求数量的电影
        return movie_ids[:n]
    except Exception as e:
        logger.error(f"获取用户推荐失败: {e}")
        # 出错时返回空列表
        return []

def get_similar_movies(movie_id, n=3, exclude_ids=None):
    """获取相似电影

    参数:
        movie_id (int): 电影ID
        n (int): 推荐电影数量
        exclude_ids (list): 需要排除的电影ID列表

    返回:
        list: 相似电影详情
    """
    try:
        global _recommender
        _recommender.update_if_needed()
        
        # 确保exclude_ids是列表
        if exclude_ids is None:
            exclude_ids = []
        elif isinstance(exclude_ids, (int, str)):
            exclude_ids = [int(exclude_ids)]
        elif not isinstance(exclude_ids, list):
            exclude_ids = list(exclude_ids) if hasattr(exclude_ids, '__iter__') else []
            
        # 转换所有exclude_ids为整数，确保类型一致
        exclude_ids = [int(x) for x in exclude_ids]
        movie_id = int(movie_id)
            
        logger.info(f"获取电影 {movie_id} 的相似电影 (n={n}, exclude={len(exclude_ids)}个ID)")
        
        # 获取当前电影详情
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前电影的信息，包括导演和主要演员
        cursor.execute("""
            SELECT 
                m.*, 
                GROUP_CONCAT(DISTINCT mc.person_id) as actor_ids,
                GROUP_CONCAT(DISTINCT mcr.person_id) as director_ids
            FROM movies m
            LEFT JOIN movie_cast mc ON m.id = mc.movie_id AND mc.cast_order < 3
            LEFT JOIN movie_crew mcr ON m.id = mcr.movie_id AND mcr.job = 'Director'
            WHERE m.id = %s
            GROUP BY m.id
        """, (movie_id,))
        
        current_movie = cursor.fetchone()
        if not current_movie:
            logger.warning(f"无法获取电影 {movie_id} 的详情")
            cursor.close()
            conn.close()
            return []
        
        # 解析当前电影的信息
        target_movie = {
            "id": current_movie[0],
            "title": current_movie[1],
            "original_title": current_movie[2],
            "overview": current_movie[3],
            "poster_path": current_movie[4],
            "backdrop_path": current_movie[5],
            "release_date": current_movie[6],
            "release_year": str(current_movie[6]).split('-')[0] if current_movie[6] else None,
            "popularity": current_movie[7],
            "vote_average": current_movie[8],
            "vote_count": current_movie[9],
            "original_language": current_movie[10],
            "genres": [g.strip() for g in current_movie[11].split(',')] if current_movie[11] else [],
            "actor_ids": [a.strip() for a in current_movie[-2].split(',')] if current_movie[-2] else [],
            "director_ids": [d.strip() for d in current_movie[-1].split(',')] if current_movie[-1] else []
        }
        
        # 获取当前电影导演的详细信息，以便后续比较
        if target_movie["director_ids"]:
            director_ids_str = ','.join(f"'{d}'" for d in target_movie["director_ids"])
            try:
                cursor.execute(f"""
                    SELECT id, name 
                    FROM persons
                    WHERE id IN ({director_ids_str})
                """)
                directors_data = cursor.fetchall()
                
                # 创建ID到名称的映射
                target_movie["directors_with_ids"] = {
                    str(d[0]): d[1] for d in directors_data if d[0] and d[1]
                }
            except Exception as e:
                logger.warning(f"获取当前电影导演详情失败: {str(e)}")
                target_movie["directors_with_ids"] = {}
        
        # 获取当前电影演员的详细信息，以便后续比较
        if target_movie["actor_ids"]:
            actor_ids_str = ','.join(f"'{a}'" for a in target_movie["actor_ids"])
            try:
                cursor.execute(f"""
                    SELECT id, name 
                    FROM persons
                    WHERE id IN ({actor_ids_str})
                """)
                actors_data = cursor.fetchall()
                
                # 创建ID到名称的映射
                target_movie["actors_with_ids"] = {
                    str(a[0]): a[1] for a in actors_data if a[0] and a[1]
                }
            except Exception as e:
                logger.warning(f"获取当前电影演员详情失败: {str(e)}")
                target_movie["actors_with_ids"] = {}
        
        # 构建排除ID列表
        exclude_ids.append(movie_id)  # 确保排除当前电影
        exclude_ids_str = ','.join(map(str, exclude_ids))
        
        # 构建类型匹配条件
        genre_conditions = []
        params = []
        for genre in target_movie["genres"]:
            genre_conditions.append("m.genres LIKE %s")
            params.append(f"%{genre}%")
        
        # 构建年份条件
        year_condition = ""
        if target_movie["release_year"]:
            try:
                year = int(target_movie["release_year"])
                year_condition = "AND YEAR(m.release_date) BETWEEN %s AND %s"
                params.extend([year - 2, year + 2])
            except (ValueError, TypeError):
                logger.warning(f"年份转换失败: {target_movie['release_year']}")
        
        # 查询相似电影，包括演员和导演信息
        # 为了提高导演相似性的优先级，添加导演匹配条件
        director_condition = ""
        director_ids_str = "-1"  # 默认值，避免SQL错误
        if target_movie["director_ids"]:
            # 创建导演ID条件
            director_ids_list = [d.strip() for d in target_movie["director_ids"] if d and d.strip()]
            if director_ids_list:
                director_ids_str = ','.join(f"'{d}'" for d in director_ids_list)
                director_condition = f" OR mcr.person_id IN ({director_ids_str})"
                logger.info(f"添加导演匹配条件: {director_condition}")
        
        query = f"""
            SELECT 
                m.*,
                GROUP_CONCAT(DISTINCT mc.person_id) as actor_ids,
                GROUP_CONCAT(DISTINCT p_cast.name ORDER BY mc.cast_order SEPARATOR '||') as actor_names,
                GROUP_CONCAT(DISTINCT mcr.person_id) as director_ids,
                GROUP_CONCAT(DISTINCT p_crew.name) as director_names,
                MAX(IF(mcr.person_id IN ({director_ids_str}), 1, 0)) as director_match
            FROM movies m
            LEFT JOIN movie_cast mc ON m.id = mc.movie_id AND mc.cast_order < 3
            LEFT JOIN persons p_cast ON mc.person_id = p_cast.id
            LEFT JOIN movie_crew mcr ON m.id = mcr.movie_id AND mcr.job = 'Director'
            LEFT JOIN persons p_crew ON mcr.person_id = p_crew.id
            WHERE m.id NOT IN ({exclude_ids_str})
            AND (({' OR '.join(genre_conditions) if genre_conditions else '1=1'}) {director_condition}) {year_condition}
            GROUP BY m.id
            ORDER BY 
                director_match DESC,  -- 优先导演匹配的电影
                m.vote_average DESC, 
                m.vote_count DESC
            LIMIT %s
        """
        
        cursor.execute(query, params + [n * 3])  # 获取更多候选电影以增加多样性
        similar_movies_raw = cursor.fetchall()
        
        # 创建相似度计算器工厂
        similarity_factory = SimilarityCalculatorFactory()
        
        # 处理候选电影结果
        result_movies = []
        for movie in similar_movies_raw:
            # 记录结果的列，帮助调试
            if len(result_movies) == 0:
                logger.info(f"查询结果列: {[i for i in range(len(movie))]}")
                logger.info(f"最后几列的值: actor_ids={movie[-5]}, actor_names={movie[-4]}, director_ids={movie[-3]}, director_names={movie[-2]}, director_match={movie[-1]}")
            
            # 处理演员ID和名称，创建ID到名称的映射
            actor_ids = movie[-5].split(',') if movie[-5] else []
            actor_names = movie[-4].split('||') if movie[-4] else []
            actors_with_ids = {}
            
            for i, actor_id in enumerate(actor_ids):
                if actor_id and actor_id.strip():  # 确保ID不是空字符串
                    actor_id = actor_id.strip()
                    if i < len(actor_names):
                        actor_name = actor_names[i]
                        if actor_name and actor_name.strip():  # 确保名称不是空字符串
                            actors_with_ids[actor_id] = actor_name.strip()
            
            # 处理导演ID和名称，创建ID到名称的映射
            director_ids = movie[-3].split(',') if movie[-3] else []
            director_names = movie[-2].split(',') if movie[-2] else []
            directors_with_ids = {}
            
            for i, director_id in enumerate(director_ids):
                if director_id and director_id.strip():  # 确保ID不是空字符串
                    director_id = director_id.strip()
                    if i < len(director_names):
                        director_name = director_names[i]
                        if director_name and director_name.strip():  # 确保名称不是空字符串
                            directors_with_ids[director_id] = director_name.strip()
            
            # 构建候选电影字典
            candidate_movie = {
                "id": movie[0],
                "title": movie[1],
                "original_title": movie[2],
                "overview": movie[3],
                "image": movie[4],  # poster_path
                "score": float(movie[8]) if movie[8] else 0,
                "release_year": str(movie[6]).split('-')[0] if movie[6] else None,
                "genres": [g.strip() for g in movie[11].split(',')] if movie[11] else [],
                "directors": [d.strip() for d in (movie[-2] or '').split(',')] if movie[-2] else [],
                "actors": [a.strip() for a in (movie[-4] or '').split('||')] if movie[-4] else [],
                "actors_with_ids": actors_with_ids,
                "directors_with_ids": directors_with_ids,
                "director_match": bool(int(movie[-1])) if movie[-1] is not None else False  # 转换director_match
            }
            
            # 处理海报路径
            if candidate_movie['image'] and not candidate_movie['image'].startswith(('http://', 'https://')):
                candidate_movie['image'] = f"https://image.tmdb.org/t/p/w500{candidate_movie['image']}"
            
            # 使用相似度计算器工厂获取最佳相似度原因
            # 如果数据库查询已经标记了导演匹配，则提供额外信息给相似度计算器
            if candidate_movie['director_match'] and target_movie.get("directors_with_ids") and candidate_movie.get("directors_with_ids"):
                logger.info(f"找到导演匹配: target={target_movie.get('directors_with_ids')}, candidate={candidate_movie.get('directors_with_ids')}")
                
                # 查找目标电影和候选电影之间的共同导演
                target_director_ids = set(target_movie["directors_with_ids"].keys())
                candidate_director_ids = set(candidate_movie["directors_with_ids"].keys())
                common_director_ids = target_director_ids.intersection(candidate_director_ids)
                
                if common_director_ids:
                    # 获取共同导演的名称
                    common_director_names = []
                    for d_id in common_director_ids:
                        if d_id in candidate_movie["directors_with_ids"]:
                            director_name = candidate_movie["directors_with_ids"][d_id]
                            if director_name:
                                common_director_names.append(director_name)
                    
                    if common_director_names:
                        similarity_reason = {
                            "type": "director",
                            "reason": f"相同导演: {', '.join(common_director_names)}",
                            "common_names": common_director_names
                        }
                    else:
                        # 尝试基于名称比较
                        target_director_names = set(n.lower() for n in target_movie["directors_with_ids"].values() if n)
                        candidate_director_names = set(n.lower() for n in candidate_movie["directors_with_ids"].values() if n)
                        common_names = target_director_names.intersection(candidate_director_names)
                        
                        if common_names:
                            original_names = []
                            for name in common_names:
                                for original in candidate_movie["directors"]:
                                    if original.lower() == name:
                                        original_names.append(original)
                                        break
                            
                            similarity_reason = {
                                "type": "director",
                                "reason": f"相同导演: {', '.join(original_names or [name.title() for name in common_names])}",
                                "common_names": list(common_names)
                            }
                        else:
                            # 如果找不到共同导演名称，则使用工厂计算相似度
                            similarity_reason = similarity_factory.get_best_similarity_reason(target_movie, candidate_movie)
                else:
                    # 尝试基于名称比较
                    target_director_names = set(n.lower() for n in target_movie["directors_with_ids"].values() if n)
                    candidate_director_names = set(n.lower() for n in candidate_movie["directors_with_ids"].values() if n)
                    common_names = target_director_names.intersection(candidate_director_names)
                    
                    if common_names:
                        original_names = []
                        for name in common_names:
                            for original in candidate_movie["directors"]:
                                if original.lower() == name:
                                    original_names.append(original)
                                    break
                        
                        similarity_reason = {
                            "type": "director",
                            "reason": f"相同导演: {', '.join(original_names or [name.title() for name in common_names])}",
                            "common_names": list(common_names)
                        }
                    else:
                        # 如果找不到共同导演名称，则使用工厂计算相似度
                        similarity_reason = similarity_factory.get_best_similarity_reason(target_movie, candidate_movie)
            else:
                # 使用常规方式计算相似度
                similarity_reason = similarity_factory.get_best_similarity_reason(target_movie, candidate_movie)
                
            candidate_movie['similarity_reason'] = similarity_reason
            
            result_movies.append(candidate_movie)
        
        cursor.close()
        conn.close()
        
        # 按相似度原因类型排序，优先考虑导演相似性
        priority_order = {'director': 1, 'actors': 2, 'genres': 3, 'year': 4, 'rating': 5, 'default': 6}
        result_movies.sort(key=lambda x: priority_order.get(x['similarity_reason']['type'], 999))
        
        # 增加随机性，对每种类型的推荐结果进行混合
        import random
        
        # 按相似度类型分组
        grouped_movies = {}
        for movie in result_movies:
            reason_type = movie['similarity_reason']['type']
            if reason_type not in grouped_movies:
                grouped_movies[reason_type] = []
            grouped_movies[reason_type].append(movie)
        
        # 对每组内的电影进行随机排序
        for reason_type in grouped_movies:
            random.shuffle(grouped_movies[reason_type])
        
        # 从每组中依次选取电影，确保多样性
        final_result = []
        remaining_slots = n
        
        # 按优先级依次处理各类型
        for reason_type in sorted(grouped_movies.keys(), key=lambda x: priority_order.get(x, 999)):
            movies_of_type = grouped_movies[reason_type]
            # 确定从这一类型中选取的电影数量
            if reason_type == 'director':
                # 导演相似性最重要，但最多分配2个位置，确保多样性
                take_count = min(2, len(movies_of_type), remaining_slots)
            elif reason_type == 'actors':
                # 演员相似性次之
                take_count = min(remaining_slots // 3 + 1, len(movies_of_type))
            else:
                # 其他类型平均分配剩余位置
                take_count = min(remaining_slots // 4 + 1, len(movies_of_type))
            
            take_count = max(1, take_count)  # 至少选择1个
            take_count = min(take_count, remaining_slots)  # 不超过剩余位置
            
            final_result.extend(movies_of_type[:take_count])
            remaining_slots -= take_count
            
            logger.info(f"选择了 {take_count} 部 {reason_type} 类型的电影，剩余位置: {remaining_slots}")
            
            if remaining_slots <= 0:
                break
        
        # 如果还有剩余位置，从所有候选电影中随机选择
        if remaining_slots > 0:
            all_remaining = [m for m in result_movies if m not in final_result]
            random.shuffle(all_remaining)
            final_result.extend(all_remaining[:remaining_slots])
        
        # 确保只返回请求的数量
        return final_result[:n]

    except Exception as e:
        logger.error(f"获取相似电影失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

# 导入时尝试初始化模型
try:
    logger.info("初始化推荐系统...")
    logger.info("推荐系统初始化完成")
except Exception as e:
    logger.error(f"初始化推荐系统失败: {e}")

 
