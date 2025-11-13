"""
定时任务模块
包含系统需要定期执行的任务
"""
import datetime
import pymysql
from movies_recommend.extensions import get_db_connection
from movies_recommend.logger import get_logger

# 配置日志
logger = get_logger('tasks')

def clear_expired_mutes():
    """清理过期的用户禁言状态
    
    自动检查并重置已过期禁言用户的状态为正常状态
    
    Returns:
        bool: 清理操作是否成功
    """
    logger.info("开始清理过期的用户禁言...")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now()
        
        # 查询所有已过期的禁言
        cursor.execute(
            """
            SELECT id, username, mute_expires_at
            FROM userinfo
            WHERE status = 'banned' 
              AND mute_expires_at IS NOT NULL 
              AND mute_expires_at < %s
            """,
            (now,)
        )
        expired_mutes = cursor.fetchall()
        
        if not expired_mutes:
            logger.info("没有找到过期的禁言")
            return True
        
        # 清理过期禁言
        user_ids = [user[0] for user in expired_mutes]
        placeholders = ', '.join(['%s'] * len(user_ids))
        
        cursor.execute(
            f"""
            UPDATE userinfo
            SET status = 'active', mute_expires_at = NULL
            WHERE id IN ({placeholders})
            """,
            user_ids
        )
        
        conn.commit()
        logger.info(f"已清理 {len(user_ids)} 个过期禁言")
        
        return True
    
    except Exception as e:
        logger.error(f"清理过期禁言失败: {e}")
        if conn:
            conn.rollback()
        return False
    
    finally:
        if conn:
            conn.close() 

def update_movie_popularity_realtime(movie_id, action_type='view', action_weight=1.0):
    """实时更新单个电影的热度
    
    根据用户行为实时更新电影热度，支持不同类型的行为和权重
    
    Args:
        movie_id (int): 电影ID
        action_type (str): 行为类型，可选值：'view'(浏览)、'rate'(评分)、'comment'(评论)、'like'(点赞)、'search'(搜索)
        action_weight (float): 行为权重，默认为1.0
    
    Returns:
        bool: 更新操作是否成功
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now()
        
        # 设置更短的锁等待超时，避免长时间阻塞
        cursor.execute("SET innodb_lock_wait_timeout = 5")
        
        # 使用SELECT ... FOR UPDATE NOWAIT来避免长时间等待锁
        try:
            # 查询电影当前热度
            cursor.execute(
                """
                SELECT popularity, updated_at FROM movies
                WHERE id = %s
                FOR UPDATE NOWAIT
                """,
                (movie_id,)
            )
            movie_data = cursor.fetchone()
        except Exception as lock_error:
            # 如果获取锁失败，记录日志但不阻止主流程
            logger.warning(f"无法获取电影ID {movie_id} 的锁，热度更新将在后台任务中进行: {lock_error}")
            return False
        
        if not movie_data:
            logger.warning(f"电影ID {movie_id} 不存在，无法更新热度")
            return False
        
        current_popularity = float(movie_data[0]) if movie_data[0] is not None else 0
        last_updated = movie_data[1]
        
        # 计算时间衰减因子 - 距离上次更新时间越长，衰减越大
        # 最大衰减为30天，超过30天不再增加衰减
        if last_updated:
            days_since_update = min(30, (now - last_updated).days)
            time_decay = 1.0 - (days_since_update / 30.0) * 0.2  # 最多衰减20%
        else:
            time_decay = 1.0
        
        # 不同行为类型的基础增量
        action_increments = {
            'view': 0.05,      # 浏览，基础增量小
            'search': 0.08,    # 搜索，稍高于浏览
            'rate': 0.15,      # 评分，中等增量
            'comment': 0.2,    # 评论，较大增量
            'like': 0.1        # 点赞，中等偏小增量
        }
        
        # 获取基础增量
        base_increment = action_increments.get(action_type, 0.05)
        
        # 计算热度增量，考虑行为权重和时间衰减
        popularity_increment = base_increment * action_weight * time_decay
        
        # 计算新热度值
        new_popularity = current_popularity + popularity_increment
        
        # 更新数据库
        cursor.execute(
            """
            UPDATE movies
            SET popularity = %s, updated_at = %s
            WHERE id = %s
            """,
            (new_popularity, now, movie_id)
        )
        
        conn.commit()
        logger.debug(f"电影ID {movie_id} 热度已更新: {current_popularity} -> {new_popularity} (增量: +{popularity_increment}, 行为: {action_type})")
        
        return True
    
    except Exception as e:
        logger.error(f"实时更新电影热度失败: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass

def update_movie_popularity(apply_penalty=True):
    """批量更新所有电影热度
    
    根据用户行为数据动态计算电影热度，并更新到数据库
    计算因素包括：最近评分数量、评分平均值、观看次数、评论数量、点赞数量等
    
    Args:
        apply_penalty (bool): 是否应用惩罚机制，对长期无互动的电影降低热度
    
    Returns:
        bool: 更新操作是否成功
    """
    logger.info("开始批量更新电影热度...")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 获取当前时间和30天前的时间点
        now = datetime.datetime.now()
        thirty_days_ago = now - datetime.timedelta(days=30)
        ninety_days_ago = now - datetime.timedelta(days=90)
        
        # 计算每部电影的热度分数
        # 热度公式：
        # 基础热度 * 0.3 + 
        # 最近30天评分数量 * 0.25 + 
        # 最近30天观看次数 * 0.2 + 
        # 最近30天评论数量 * 0.15 + 
        # 最近30天评论点赞数 * 0.1
        
        cursor.execute(
            """
            WITH recent_ratings AS (
                SELECT 
                    movie_id, 
                    COUNT(*) as rating_count,
                    AVG(rating) as avg_rating
                FROM user_ratings
                WHERE created_at >= %s
                GROUP BY movie_id
            ),
            recent_watches AS (
                SELECT 
                    movie_id, 
                    COUNT(*) as watch_count
                FROM user_watch_history
                WHERE watched_at >= %s
                GROUP BY movie_id
            ),
            recent_comments AS (
                SELECT 
                    movie_id, 
                    COUNT(*) as comment_count
                FROM comments
                WHERE created_at >= %s
                GROUP BY movie_id
            ),
            recent_likes AS (
                SELECT 
                    ur.movie_id,
                    COUNT(cl.id) as like_count
                FROM comment_likes cl
                JOIN user_ratings ur ON cl.rating_id = ur.id
                WHERE cl.created_at >= %s
                GROUP BY ur.movie_id
            )
            SELECT 
                m.id,
                m.popularity as base_popularity,
                m.updated_at as last_updated,
                COALESCE(rr.rating_count, 0) as recent_rating_count,
                COALESCE(rr.avg_rating, 0) as recent_avg_rating,
                COALESCE(rw.watch_count, 0) as recent_watch_count,
                COALESCE(rc.comment_count, 0) as recent_comment_count,
                COALESCE(rl.like_count, 0) as recent_like_count
            FROM movies m
            LEFT JOIN recent_ratings rr ON m.id = rr.movie_id
            LEFT JOIN recent_watches rw ON m.id = rw.movie_id
            LEFT JOIN recent_comments rc ON m.id = rc.movie_id
            LEFT JOIN recent_likes rl ON m.id = rl.movie_id
            """,
            (thirty_days_ago, thirty_days_ago, thirty_days_ago, thirty_days_ago)
        )
        
        movies_data = cursor.fetchall()
        
        # 计算热度并更新数据库
        update_count = 0
        penalty_count = 0
        
        for movie in movies_data:
            movie_id = movie[0]
            base_popularity = float(movie[1]) if movie[1] is not None else 0
            last_updated = movie[2]
            recent_rating_count = int(movie[3]) if movie[3] is not None else 0
            recent_avg_rating = float(movie[4]) if movie[4] is not None else 0
            recent_watch_count = int(movie[5]) if movie[5] is not None else 0
            recent_comment_count = int(movie[6]) if movie[6] is not None else 0
            recent_like_count = int(movie[7]) if movie[7] is not None else 0
            
            # 标准化评分 (0-10 转为 0-1)
            normalized_rating = recent_avg_rating / 10.0 if recent_avg_rating > 0 else 0
            
            # 检查是否应用惩罚机制
            apply_movie_penalty = False
            penalty_factor = 1.0
            
            if apply_penalty and last_updated:
                # 计算电影上次更新距今的天数
                days_since_update = (now - last_updated).days
                
                # 如果超过90天没有任何互动，应用惩罚机制
                if days_since_update > 90 and recent_rating_count == 0 and recent_watch_count == 0 and recent_comment_count == 0 and recent_like_count == 0:
                    apply_movie_penalty = True
                    # 惩罚系数：超过90天，每30天额外降低5%，最多降低30%
                    extra_days = days_since_update - 90
                    extra_months = extra_days / 30
                    penalty_factor = max(0.7, 1.0 - min(0.3, extra_months * 0.05))
                    penalty_count += 1
            
            # 计算新热度值
            if apply_movie_penalty:
                # 应用惩罚机制，降低热度
                new_popularity = base_popularity * penalty_factor
                logger.debug(f"电影ID {movie_id} 应用惩罚机制: {base_popularity} -> {new_popularity} (惩罚因子: {penalty_factor})")
            else:
                # 正常计算热度
                # 基础热度保留一部分，其余部分由最近活动决定
                new_popularity = (
                    base_popularity * 0.3 +  # 保留30%的原有热度
                    recent_rating_count * 0.25 +  # 最近评分数量权重25%
                    normalized_rating * recent_rating_count * 0.2 +  # 最近评分质量权重20%
                    recent_watch_count * 0.15 +  # 最近观看次数权重15%
                    recent_comment_count * 0.05 +  # 最近评论数量权重5%
                    recent_like_count * 0.05  # 最近点赞数量权重5%
                )
                
                # 确保热度值不会低于原始值的一定比例（防止热门电影热度突然大幅下降）
                min_popularity = base_popularity * 0.7
                new_popularity = max(new_popularity, min_popularity)
            
            # 更新数据库
            cursor.execute(
                """
                UPDATE movies
                SET popularity = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                (new_popularity, now, movie_id)
            )
            update_count += 1
        
        conn.commit()
        logger.info(f"已更新 {update_count} 部电影的热度，其中 {penalty_count} 部应用了惩罚机制")
        
        return True
    
    except Exception as e:
        logger.error(f"更新电影热度失败: {e}")
        if conn:
            conn.rollback()
        return False
    
    finally:
        if conn:
            conn.close() 