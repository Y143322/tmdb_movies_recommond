#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户类型偏好初始化脚本 - 修复版

该脚本用于批量分析所有用户的评分历史，并为每个用户生成电影类型偏好数据。
这些数据存储在user_genre_preferences表中，用于增强推荐系统的个性化能力。

用法：
    python movies_recommend/init_user_preferences.py
"""

import sys
import os
import pymysql
import logging
import time
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('init_preferences')

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',
    'database': 'movies_recommend',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def update_user_genre_preferences(user_id, conn):
    """
    更新指定用户的电影类型偏好

    根据用户的评分历史，计算用户对不同电影类型的偏好程度，
    并将结果更新到user_genre_preferences表中。

    参数:
        user_id (int): 用户ID
        conn (pymysql.Connection): 数据库连接

    返回:
        bool: 更新成功返回True，否则返回False
    """
    try:
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
            return False
        
        # 处理类型数据
        genre_ratings = {}  # 格式: {genre: [rating1, rating2, ...]}
        
        for movie in ratings_data:
            # 类型可能是逗号分隔的字符串
            genres = movie['genres']
            if genres:
                for genre in [g.strip() for g in genres.split(',')]:
                    if genre:
                        if genre not in genre_ratings:
                            genre_ratings[genre] = []
                        genre_ratings[genre].append(movie['rating'])
        
        # 计算每个类型的偏好分数
        # 偏好分数计算方法: 归一化的平均评分 * (1 + log(评分数量))
        # 这样既考虑了评分高低，也考虑了用户对该类型电影的关注度
        preferences = {}
        
        all_scores = []  # 用于归一化
        
        import math
        for genre, ratings in genre_ratings.items():
            if len(ratings) > 0:
                avg_rating = sum(ratings) / len(ratings)
                # 加入评分数量的影响，但避免过度偏向热门类型
                score = avg_rating * (1 + 0.3 * math.log(1 + len(ratings)))
                preferences[genre] = score
                all_scores.append(score)
        
        # 如果没有任何有效偏好，退出
        if not preferences:
            logger.info(f"用户 {user_id} 没有有效的类型偏好，跳过更新")
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
        
        return True
    
    except Exception as e:
        logger.error(f"更新用户 {user_id} 类型偏好失败: {str(e)}")
        conn.rollback()
        return False

def batch_update_users_preferences(batch_size=100, max_users=None):
    """
    批量更新所有用户的电影类型偏好
    
    参数:
        batch_size (int): 每批处理的用户数量
        max_users (int, optional): 最多处理的用户数量，为None时处理所有用户
    
    返回:
        tuple: (成功更新的用户数, 总用户数)
    """
    start_time = time.time()
    success_count = 0
    total_count = 0
    
    try:
        # 连接数据库
        print("正在连接数据库...")
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 获取有评分记录的所有用户
        cursor.execute("""
            SELECT DISTINCT user_id 
            FROM user_ratings
            ORDER BY user_id
        """)
        
        all_users = [row['user_id'] for row in cursor.fetchall()]
        
        if not all_users:
            logger.info("没有找到任何用户评分记录，跳过批量更新")
            conn.close()
            return (0, 0)
        
        # 限制用户数量
        if max_users:
            users = all_users[:max_users]
        else:
            users = all_users
        
        total_count = len(users)
        logger.info(f"开始为 {total_count} 个用户更新类型偏好")
        print(f"共找到 {total_count} 个用户，开始处理...")
        
        # 分批处理用户
        for i in range(0, total_count, batch_size):
            batch_users = users[i:i+batch_size]
            batch_start_time = time.time()
            
            batch_success = 0
            for user_id in batch_users:
                if update_user_genre_preferences(user_id, conn):
                    success_count += 1
                    batch_success += 1
            
            batch_end_time = time.time()
            batch_elapsed = batch_end_time - batch_start_time
            
            # 打印批处理进度
            current = i + len(batch_users)
            print(f"处理进度: {current}/{total_count} 用户 ({current/total_count*100:.1f}%), " +
                  f"批处理成功: {batch_success}/{len(batch_users)}, " +
                  f"耗时: {batch_elapsed:.2f}秒")
            
            # 每批处理后暂停一下，避免数据库负载过高
            if i + batch_size < total_count:
                time.sleep(0.1)
        
        cursor.close()
        conn.close()
        
        elapsed = time.time() - start_time
        logger.info(f"批量更新完成: {success_count}/{total_count} 个用户成功更新，耗时: {elapsed:.2f}秒")
        return (success_count, total_count)
    
    except Exception as e:
        logger.error(f"批量更新用户类型偏好失败: {str(e)}")
        return (success_count, total_count)

def main():
    """主函数：执行用户偏好初始化"""
    print("=" * 60)
    print("用户电影类型偏好初始化")
    print("=" * 60)
    print("\n此脚本将分析所有用户的评分历史，并生成类型偏好数据。")
    print("这些数据将用于增强电影推荐系统的个性化能力。\n")
    
    # 确认是否继续
    confirm = input("是否继续？(y/n): ").strip().lower()
    if confirm != 'y':
        print("操作已取消")
        return
    
    # 高级选项
    use_advanced = input("使用高级选项？(y/n, 默认n): ").strip().lower() == 'y'
    
    batch_size = 100
    max_users = None
    
    if use_advanced:
        try:
            batch_size_input = input(f"每批处理用户数 (默认 {batch_size}): ").strip()
            if batch_size_input:
                batch_size = int(batch_size_input)
                
            max_users_input = input("最多处理用户数 (默认处理所有用户): ").strip()
            if max_users_input:
                max_users = int(max_users_input)
        except ValueError:
            print("输入无效，使用默认值")
    
    print("\n开始处理用户类型偏好数据...\n")
    start_time = time.time()
    
    # 批量更新所有用户的类型偏好
    success_count, total_count = batch_update_users_preferences(batch_size, max_users)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    print("\n" + "=" * 60)
    print(f"处理完成! 耗时: {elapsed:.2f}秒")
    print(f"成功更新: {success_count}/{total_count} 个用户的类型偏好")
    print("=" * 60)
    
    # 提供后续建议
    if success_count > 0:
        print("\n接下来，推荐系统将根据用户的类型偏好提供更加个性化的电影推荐。")
        print("用户每次评分后，系统将自动更新其类型偏好数据。")
    else:
        print("\n警告: 没有成功更新任何用户的类型偏好数据!")
        print("请检查用户评分数据是否存在，或查看日志了解详细错误信息。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n操作已中断")
    except Exception as e:
        logger.error(f"初始化过程发生错误: {e}")
        print(f"\n初始化过程发生错误: {e}")
        print("请查看日志获取详细信息。")
    finally:
        print("\n程序结束") 