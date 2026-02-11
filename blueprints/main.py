"""
主蓝图，处理首页、电影列表等功能
"""
import math
import inspect
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, session, current_app
from flask_login import current_user, login_required
from movies_recommend.extensions import get_db_connection
from movies_recommend.request_utils import normalize_id_list
from movies_recommend.db_utils import fetch_random_rows_by_id_range
import pymysql
import random


# 创建蓝图
main_bp = Blueprint('main', __name__)


def _safe_error_message(action='操作失败'):
    """统一对外错误信息，避免泄露内部异常细节。"""
    return f'{action}，请稍后重试'


def _fetch_random_movie_rows(cursor, limit, select_columns, exclude_ids=None, extra_where='', extra_params=None):
    """按随机 ID 起点抓取电影，避免 ORDER BY RAND()。"""
    conditions = []
    params = []

    normalized_excluded_ids = normalize_id_list(exclude_ids or [])
    if normalized_excluded_ids:
        placeholders = ', '.join(['%s'] * len(normalized_excluded_ids))
        conditions.append(f'id NOT IN ({placeholders})')
        params.extend(normalized_excluded_ids)

    if extra_where:
        conditions.append(extra_where.strip())
    if extra_params:
        params.extend(list(extra_params))

    where_clause = ' AND '.join(conditions)
    return fetch_random_rows_by_id_range(
        cursor=cursor,
        table='movies',
        select_columns=select_columns,
        limit=limit,
        where_clause=where_clause,
        params=params,
    )


def _apply_movie_metadata(cursor, movies):
    """批量补充电影类型与发行年份，避免逐条查询。"""
    if not movies:
        return

    movie_ids = normalize_id_list([movie.get('id') for movie in movies])
    if not movie_ids:
        return

    placeholders = ', '.join(['%s'] * len(movie_ids))
    cursor.execute(
        f'SELECT id, genres, release_date FROM movies WHERE id IN ({placeholders})',
        movie_ids,
    )
    metadata_rows = cursor.fetchall() or []
    metadata_map = {row.get('id'): row for row in metadata_rows if isinstance(row, dict)}

    for movie in movies:
        metadata = metadata_map.get(movie.get('id')) or {}
        raw_genres = metadata.get('genres')
        if raw_genres:
            movie['genres'] = [genre.strip() for genre in str(raw_genres).split(',') if genre.strip()]
        else:
            movie['genres'] = []

        release_date = metadata.get('release_date')
        if release_date:
            try:
                if hasattr(release_date, 'year'):
                    movie['release_year'] = str(release_date.year)
                else:
                    movie['release_year'] = str(release_date).split('-')[0]
            except Exception:
                movie['release_year'] = None
        else:
            movie['release_year'] = None

# 更新电影评分函数
def update_movie_rating(cursor, movie_id):
    """更新电影的平均评分

    Args:
        cursor: 数据库游标对象
        movie_id (int): 电影ID
    """
    try:
        # 计算电影的平均评分
        cursor.execute(
            'SELECT AVG(rating), COUNT(*) FROM user_ratings WHERE movie_id = %s',
            (movie_id,)
        )
        result = cursor.fetchone()
        if result and result[0]:
            avg_rating = round(float(result[0]), 1)  # 保留一位小数
            count = int(result[1])
            
            # 更新电影表中的平均评分和评分计数
            cursor.execute(
                'UPDATE movies SET vote_average = %s, vote_count = %s WHERE id = %s',
                (avg_rating, count, movie_id)
            )
    except Exception as e:
        current_app.logger.error(f"更新电影评分失败: {e}")
        raise e

# 导入用户偏好更新函数
from movies_recommend.user_preferences import update_user_genre_preferences

@main_bp.route('/')
def index():
    """首页路由，展示个性化推荐或随机电影"""
    recommendations = []
    random_movies = []

    # 获取随机电影作为备用
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        random_movies_raw = _fetch_random_movie_rows(
            cursor,
            limit=5,
            select_columns="id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score",
        )

        # 清空随机电影列表并处理海报路径
        random_movies = []
        for movie in random_movies_raw:
            if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
            random_movies.append(movie)
    except Exception as e:
        current_app.logger.error(f"无法获取随机电影: {e}")
    finally:
        cursor.close()
        conn.close()

    # 检查推荐系统是否可用
    recommender_available = False
    try:
        from movies_recommend.recommender import get_recommendations_for_user
        recommender_available = True
    except ImportError:
        recommender_available = False

    if current_user.is_authenticated and recommender_available:
        # 如果用户已登录且推荐系统可用，则获取个性化推荐
        try:
            # 检查用户是否为管理员
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM admininfo WHERE id = %s', (current_user.id,))
            admin = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if admin:
                # 管理员不参与推荐系统，使用随机电影
                current_app.logger.info(f"用户 {current_user.id} 是管理员，不提供个性化推荐")
                recommendations = random_movies
            else:
                # 普通用户获取个性化推荐
                recommended_ids = get_recommendations_for_user(current_user.id, n=5)

                # 如果有推荐，获取完整的电影信息
                if recommended_ids:
                    conn = get_db_connection()
                    cursor = conn.cursor(pymysql.cursors.DictCursor)

                    try:
                        # 清空推荐列表
                        recommendations = []

                        # 查询推荐电影的完整信息
                        placeholders = ', '.join(['%s'] * len(recommended_ids))
                        query = f"""
                            SELECT id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score
                            FROM movies
                            WHERE id IN ({placeholders})
                        """
                        cursor.execute(query, recommended_ids)
                        recommendations_raw = cursor.fetchall()

                        # 处理推荐电影海报路径
                        for movie in recommendations_raw:
                            if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                                movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                            recommendations.append(movie)
                    except Exception as e:
                        current_app.logger.error(f"获取推荐电影信息失败: {e}")
                    finally:
                        cursor.close()
                        conn.close()
        except Exception as e:
            current_app.logger.error(f"推荐系统异常: {e}")

        # 如果没有获取到推荐，使用随机电影代替
        if not recommendations:
            recommendations = random_movies
    else:
        # 如果用户未登录或推荐系统不可用，使用随机电影
        recommendations = random_movies

    return render_template('index.html', recommendations=recommendations, random_movies=random_movies)

@main_bp.route('/refresh_recommendations', methods=['POST'])
def refresh_recommendations():
    """刷新电影推荐"""
    try:
        # 检查是否为AJAX请求
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        # 检查用户是否已登录
        if current_user.is_authenticated:
            # 检查用户是否为管理员
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM admininfo WHERE id = %s', (current_user.id,))
            admin = cursor.fetchone()
            cursor.close()
            conn.close()


        # 结果电影列表
        result_movies = []

        # 获取当前推荐的电影ID列表(如果有)，用于排除
        current_movie_ids = []
        request_json = request.get_json(silent=True) or {}
        if 'current_movies' in request_json:
            current_movie_ids = normalize_id_list(request_json.get('current_movies', []))
            
        # 从会话中获取已推荐过的电影ID列表
        user_id_key = str(current_user.id) if current_user.is_authenticated else 'anonymous'
        session_key = f'recommended_movies_{user_id_key}'
        
        if session_key not in session:
            session[session_key] = []
        
        # 将当前显示的电影添加到已推荐列表中
        recommended_history = session[session_key]
        if current_movie_ids:
            for movie_id in current_movie_ids:
                if movie_id not in recommended_history:
                    recommended_history.append(movie_id)
            
            # 如果历史记录过长，只保留最近的100个
            if len(recommended_history) > 100:
                recommended_history = recommended_history[-100:]
            
            session[session_key] = recommended_history

        # 合并当前显示的电影ID和历史推荐ID作为排除列表
        exclude_ids = list(set(current_movie_ids + recommended_history))
        
        # 检查用户是否已登录
        if current_user.is_authenticated:
            # 检查用户是否为管理员
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM admininfo WHERE id = %s', (current_user.id,))
            admin = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if admin:
                # 管理员使用随机电影推荐
                conn = get_db_connection()
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                try:
                    # 排除当前显示的电影和历史推荐
                    result_movies = _fetch_random_movie_rows(
                        cursor,
                        limit=5,
                        select_columns="id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score",
                        exclude_ids=exclude_ids,
                    )

                    # 处理海报路径
                    for movie in result_movies:
                        if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                            movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                        elif not movie['image']:
                            # 如果没有海报，使用默认海报
                            movie['image'] = "/static/img/default-movie-placeholder.png"
                            
                    # 更新会话中的已推荐电影列表
                    if result_movies:
                        new_movie_ids = [movie['id'] for movie in result_movies]
                        for movie_id in new_movie_ids:
                            if movie_id not in recommended_history:
                                recommended_history.append(movie_id)
                        
                        # 如果历史记录过长，只保留最近的100个
                        if len(recommended_history) > 100:
                            recommended_history = recommended_history[-100:]
                        
                        session[session_key] = recommended_history
                finally:
                    cursor.close()
                    conn.close()

                # 记录日志
                current_app.logger.info(f"管理员用户 {current_user.id} 刷新推荐，返回 {len(result_movies)} 部随机电影")

                return jsonify({
                    'success': True,
                    'message': '已获取新的电影推荐',
                    'movies': result_movies
                })
            # 检查推荐系统是否可用
            try:
                from movies_recommend.recommender import get_recommendations_for_user

                # 检查函数是否支持exclude_ids参数
                import inspect
                params = inspect.signature(get_recommendations_for_user).parameters
                supports_exclude = 'exclude_ids' in params

                # 获取新的推荐
                if supports_exclude:
                    # 如果支持exclude_ids参数，则传递它
                    recommended_ids = get_recommendations_for_user(current_user.id, n=5, refresh=True, exclude_ids=exclude_ids)
                else:
                    # 否则只使用基本参数
                    recommended_ids = get_recommendations_for_user(current_user.id, n=10, refresh=True)
                    # 手动过滤排除的ID
                    if exclude_ids and recommended_ids:
                        recommended_ids = [m_id for m_id in recommended_ids if m_id not in exclude_ids]
                        recommended_ids = recommended_ids[:5]  # 只保留前5个

                # 获取电影详细信息
                if recommended_ids:
                    conn = get_db_connection()
                    cursor = conn.cursor(pymysql.cursors.DictCursor)
                    try:
                        # 查询推荐电影的完整信息
                        placeholders = ', '.join(['%s'] * len(recommended_ids))
                        query = f"""
                            SELECT id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score
                            FROM movies
                            WHERE id IN ({placeholders})
                        """
                        cursor.execute(query, recommended_ids)
                        result_movies = cursor.fetchall()

                        # 处理推荐电影海报路径
                        for movie in result_movies:
                            if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                                movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                    finally:
                        cursor.close()
                        conn.close()

                # 更新会话中的已推荐电影列表
                if result_movies:
                    new_movie_ids = [movie['id'] for movie in result_movies]
                    for movie_id in new_movie_ids:
                        if movie_id not in recommended_history:
                            recommended_history.append(movie_id)
                    
                    # 如果历史记录过长，只保留最近的100个
                    if len(recommended_history) > 100:
                        recommended_history = recommended_history[-100:]
                    
                    session[session_key] = recommended_history

                # 记录日志
                current_app.logger.info(f"为用户 {current_user.id} 刷新推荐，返回 {len(result_movies)} 部电影，已排除 {len(exclude_ids)} 部历史推荐")

                # 返回成功信息和电影数据
                return jsonify({
                    'success': True,
                    'message': '已成功刷新推荐',
                    'movies': result_movies
                })
            except Exception as e:
                # 记录错误信息
                current_app.logger.error(f"推荐系统异常: {str(e)}")

                # 推荐系统不可用，返回随机电影
                conn = get_db_connection()
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                try:
                    # 排除当前显示的电影和历史推荐
                    result_movies = _fetch_random_movie_rows(
                        cursor,
                        limit=5,
                        select_columns="id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score",
                        exclude_ids=exclude_ids,
                    )

                    # 处理海报路径
                    for movie in result_movies:
                        if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                            movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                        elif not movie['image']:
                            # 如果没有海报，使用默认海报
                            movie['image'] = "/static/img/default-movie-placeholder.png"
                            
                    # 更新会话中的已推荐电影列表
                    if result_movies:
                        new_movie_ids = [movie['id'] for movie in result_movies]
                        for movie_id in new_movie_ids:
                            if movie_id not in recommended_history:
                                recommended_history.append(movie_id)
                        
                        # 如果历史记录过长，只保留最近的100个
                        if len(recommended_history) > 100:
                            recommended_history = recommended_history[-100:]
                        
                        session[session_key] = recommended_history
                finally:
                    cursor.close()
                    conn.close()

                # 记录日志
                current_app.logger.info(f"推荐系统不可用，返回 {len(result_movies)} 部随机电影")

                return jsonify({
                    'success': True,
                    'message': '已获取新的随机电影',
                    'movies': result_movies
                })
        else:
            # 未登录用户，返回随机电影
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            try:
                # 排除当前显示的电影和历史推荐
                result_movies = _fetch_random_movie_rows(
                    cursor,
                    limit=5,
                    select_columns="id, title, poster_path as image, '' as actors, release_date as release_time, vote_average as score",
                    exclude_ids=exclude_ids,
                )

                # 处理海报路径
                for movie in result_movies:
                    if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                        movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                    elif not movie['image']:
                        # 如果没有海报，使用默认海报
                        movie['image'] = "/static/img/default-movie-placeholder.png"
                        
                # 更新会话中的已推荐电影列表
                if result_movies:
                    new_movie_ids = [movie['id'] for movie in result_movies]
                    for movie_id in new_movie_ids:
                        if movie_id not in recommended_history:
                            recommended_history.append(movie_id)
                    
                    # 如果历史记录过长，只保留最近的100个
                    if len(recommended_history) > 100:
                        recommended_history = recommended_history[-100:]
                    
                    session[session_key] = recommended_history
            finally:
                cursor.close()
                conn.close()

            # 记录日志
            current_app.logger.info(f"未登录用户刷新推荐，返回 {len(result_movies)} 部随机电影")

            return jsonify({
                'success': True,
                'message': '已获取新的随机电影',
                'movies': result_movies
            })
    except Exception as e:
        # 记录错误并返回错误信息
        current_app.logger.error(f"刷新推荐失败: {e}")
        return jsonify({'success': False, 'message': _safe_error_message('刷新推荐失败')}), 500

@main_bp.route('/movies')
@main_bp.route('/movies/<int:page>')
def show_movies(page=1):
    """显示电影列表页面"""
    # 获取排序参数
    sort_by = request.args.get('sort', 'hot')  # 默认按热门排序
    
    # 每页显示的电影数量
    per_page = 9  # 改为9个，适合3x3的网格布局

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 获取总记录数
            cursor.execute('SELECT COUNT(*) FROM movies')
            total_count = cursor.fetchone()[0]

            # 计算总页数
            total_pages = math.ceil(total_count / per_page)

            # 确保页码有效
            if page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                page = total_pages

            # 查询基础SQL
            base_sql = 'SELECT id, title, poster_path AS image, release_date AS release_time, vote_average AS score, genres, popularity FROM movies'
            
            # 根据排序参数添加排序条件
            if sort_by == 'time':
                # 按上映时间降序排序（最新的排在前面）
                base_sql += ' ORDER BY release_date DESC'
            elif sort_by == 'rating':
                # 按评分降序排序，同时考虑评分人数
                base_sql += ' ORDER BY vote_average DESC, vote_count DESC'
            else:  # 默认按热门排序(sort_by == 'hot')
                # 按人气降序排序
                base_sql += ' ORDER BY popularity DESC'
                
            # 添加分页
            base_sql += ' LIMIT %s OFFSET %s'
            cursor.execute(base_sql, (per_page, (page - 1) * per_page))
            movies_raw = cursor.fetchall()

            # 处理电影海报路径、类型和演员信息
            movies = []
            for movie in movies_raw:
                movie_id, title, poster_path, release_date, score, genres_str, popularity = movie
                # 如果海报路径存在且不是完整URL，添加基础URL
                if poster_path and not poster_path.startswith(('http://', 'https://')):
                    poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"

                # 处理电影类型
                genres = genres_str.split(',') if genres_str else []
                genres = [genre.strip() for genre in genres if genre.strip()]

                # 获取该电影的前三位演员
                cursor.execute("""
                    SELECT p.name
                    FROM movie_cast mc
                    JOIN persons p ON mc.person_id = p.id
                    WHERE mc.movie_id = %s
                    ORDER BY mc.cast_order
                    LIMIT 3
                """, (movie_id,))
                actors_raw = cursor.fetchall()
                actors = ', '.join([actor[0] for actor in actors_raw]) if actors_raw else '未知'

                # 将元组改为字典，与movies.py保持一致
                movie_dict = {
                    'id': movie_id,
                    'title': title,
                    'poster_path': poster_path,
                    'release_date': release_date.strftime('%Y-%m-%d') if release_date else None,
                    'vote_average': float(score) if score is not None else None,
                    'genres': genres,
                    'popularity': float(popularity) if popularity is not None else None,
                    'actors': actors
                }
                movies.append(movie_dict)
    finally:
        conn.close()

    # 判断是否为管理员用户
    is_admin = current_user.is_authenticated and current_user.is_admin

    # 预定义电影类型列表，确保模板能正常渲染
    all_genres = []
    regions = ["全部"]
    years = ["全部"]
    
    return render_template('movies.html', movies=movies, page=page, total_pages=total_pages, 
                         is_admin=is_admin, sort_by=sort_by, all_genres=all_genres, 
                         regions=regions, years=years)

@main_bp.route('/like_comment/<int:rating_id>', methods=['POST'], endpoint='like_comment_endpoint')
def like_comment(rating_id):
    """处理评论点赞

    用户点赞或取消点赞评论的API接口。如果用户已经点赞过该评论，则取消点赞；
    如果用户未点赞过该评论，则添加点赞。

    Args:
        rating_id (int): 要点赞的评论ID

    Returns:
        Response: JSON格式的处理结果，包含点赞状态和点赞数
    """
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'message': '请先登录'}), 403
        
    # 管理员不能点赞评论
    if current_user.is_admin:
        return jsonify({'success': False, 'message': '管理员不能点赞评论'}), 403

    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 检查评论是否存在
        cursor.execute('SELECT id FROM user_ratings WHERE id = %s', (rating_id,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': '评论不存在'}), 404

        # 获取评论所属的电影ID
        cursor.execute('SELECT movie_id FROM user_ratings WHERE id = %s', (rating_id,))
        movie_id = cursor.fetchone()[0]

        # 检查用户是否已经点赞过该评论
        cursor.execute(
            'SELECT id FROM comment_likes WHERE rating_id = %s AND user_id = %s',
            (rating_id, current_user.id)
        )
        existing_like = cursor.fetchone()

        if existing_like:
            # 如果已经点赞过，则取消点赞
            cursor.execute(
                'DELETE FROM comment_likes WHERE id = %s',
                (existing_like[0],)
            )
            liked = False
        else:
            # 如果未点赞过，则添加点赞
            cursor.execute(
                'INSERT INTO comment_likes (rating_id, user_id) VALUES (%s, %s)',
                (rating_id, current_user.id)
            )
            liked = True
            
            # 更新电影热度
            try:
                from movies_recommend.tasks import update_movie_popularity_realtime
                update_movie_popularity_realtime(movie_id, action_type='like', action_weight=1.0)
            except Exception as e:
                # 记录错误但不影响主流程
                current_app.logger.error(f"更新电影热度失败: {str(e)}")

        # 提交事务
        conn.commit()

        # 获取当前点赞数
        cursor.execute(
            'SELECT COUNT(*) FROM comment_likes WHERE rating_id = %s',
            (rating_id,)
        )
        like_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'liked': liked,
            'likeCount': like_count
        })

    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        cursor.close()
        conn.close()
        # 记录错误日志
        current_app.logger.error(f"点赞操作失败: {str(e)}")
        return jsonify({'success': False, 'message': _safe_error_message('操作失败')}), 500

@main_bp.route('/reply_comment/<int:rating_id>', methods=['POST'], endpoint='reply_comment_endpoint')
def reply_comment(rating_id):
    """回复评论

    用户对评论进行回复的处理函数。

    Args:
        rating_id (int): 要回复的评论ID

    Returns:
        Response: 重定向到电影详情页面
    """
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '请先登录'}), 403
        else:
            flash('请先登录', 'info')
            movie_id = request.form.get('movie_id')
            if movie_id:
                return redirect(url_for('main.movie_detail', movie_id=movie_id))
            else:
                return redirect(url_for('main.index'))

    # 获取表单数据
    reply_content = (request.form.get('reply') or '').strip()
    movie_id = request.form.get('movie_id')

    # 验证数据
    if not reply_content:
        flash('回复内容不能为空', 'error')
        return redirect(url_for('main.movie_detail', movie_id=movie_id))

    if not movie_id:
        flash('缺少电影ID', 'error')
        return redirect(url_for('main.index'))

    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 首先检查用户是否被禁言
        cursor.execute(
            'SELECT status, mute_expires_at FROM userinfo WHERE id = %s',
            (current_user.id,)
        )
        user_status = cursor.fetchone()
        
        # 如果用户被禁言，直接返回禁言提示，不允许任何形式的评分操作
        if user_status and user_status[0] == 'banned':
            import datetime
            now = datetime.datetime.now()
            
            # 检查禁言是否已过期
            if user_status[1] and user_status[1] > now:
                # 计算剩余时间
                time_left = user_status[1] - now
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                ban_message = f'您已被禁言，无法发表评论。禁言将在{hours}小时{minutes}分钟后解除。'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': ban_message
                    }), 403
                else:
                    flash(ban_message, 'error')
                    return redirect(url_for('main.movie_detail', movie_id=movie_id))
                    
            elif not user_status[1]:  # 永久禁言
                ban_message = '您已被永久禁言，无法发表评论。'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': ban_message
                    }), 403
                else:
                    flash(ban_message, 'error')
                    return redirect(url_for('main.movie_detail', movie_id=movie_id))
            else:
                # 禁言已过期，自动解除
                cursor.execute(
                    'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s',
                    (current_user.id,)
                )
                conn.commit()
        
        # 检查评论是否存在
        cursor.execute('SELECT id FROM user_ratings WHERE id = %s', (rating_id,))
        if not cursor.fetchone():
            flash('评论不存在', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('main.movie_detail', movie_id=movie_id))

        # 添加回复
        cursor.execute(
            'INSERT INTO comment_replies (rating_id, user_id, content) VALUES (%s, %s, %s)',
            (rating_id, current_user.id, reply_content)
        )

        # 更新电影热度
        try:
            from movies_recommend.tasks import update_movie_popularity_realtime
            # 回复评论的权重略高于普通评论
            action_weight = 1.2
            action_type = 'comment'
            # 非阻塞方式更新热度
            update_movie_popularity_realtime(int(movie_id), action_type=action_type, action_weight=action_weight)
        except Exception as e:
            # 记录错误但不影响主流程
            current_app.logger.error(f"更新电影热度失败: {str(e)}")

        # 提交事务
        conn.commit()
        flash('回复已发布', 'success')
    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        flash(_safe_error_message('发布回复失败'), 'error')
    finally:
        # 关闭数据库连接
        cursor.close()
        conn.close()

    # 重定向回电影详情页面
    return redirect(url_for('main.movie_detail', movie_id=movie_id))

@main_bp.route('/delete_reply/<int:reply_id>', methods=['POST'], endpoint='delete_reply_endpoint')
def delete_reply(reply_id):
    """删除回复

    用户删除自己的回复或管理员删除任何回复的处理函数。

    Args:
        reply_id (int): 要删除的回复ID

    Returns:
        Response: 重定向到电影详情页面
    """
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': '请先登录'}), 403
        else:
            flash('请先登录', 'info')
            return redirect(url_for('main.index'))

    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 获取回复信息和关联的电影ID
        cursor.execute(
            '''
            SELECT cr.id, cr.user_id, ur.movie_id
            FROM comment_replies cr
            JOIN user_ratings ur ON cr.rating_id = ur.id
            WHERE cr.id = %s
            ''',
            (reply_id,)
        )
        reply_info = cursor.fetchone()

        if not reply_info:
            flash('回复不存在', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('main.index'))

        # 获取电影ID用于重定向
        movie_id = reply_info[2]

        # 检查权限：只有回复的作者或管理员可以删除回复
        if reply_info[1] != current_user.id and not current_user.is_admin:
            flash('您没有权限删除此回复', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('main.movie_detail', movie_id=movie_id))

        # 删除回复
        cursor.execute('DELETE FROM comment_replies WHERE id = %s', (reply_id,))

        # 提交事务
        conn.commit()
        flash('回复已删除', 'success')
    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        flash(_safe_error_message('删除回复失败'), 'error')
        # 重定向到首页（因为可能无法获取电影ID）
        cursor.close()
        conn.close()
        return redirect(url_for('main.index'))

    # 关闭数据库连接
    cursor.close()
    conn.close()

    # 重定向回电影详情页面
    return redirect(url_for('main.movie_detail', movie_id=movie_id))

@main_bp.route('/movie/<int:movie_id>')
@main_bp.route('/movie/<int:movie_id>/page/<int:page>')
def movie_detail(movie_id, page=1):
    """显示电影详情页面"""
    conn = None
    cursor = None
    movie = None
    reviews = []
    similar_movies = []
    user_rating = None
    has_user_ratings = False
    movie_genres = []
    movie_director = None
    movie_actors = []

    # 每页显示的评论数量
    per_page = 10

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 获取电影详情（基本信息）
        sql = """SELECT m.* FROM movies m WHERE m.id = %s"""
        cursor.execute(sql, (movie_id,))
        movie_raw = cursor.fetchone()

        # 处理电影数据，添加完整的海报URL
        if movie_raw:
            movie = list(movie_raw)  # 转换为列表以便修改
            # 处理release_date，确保是字符串格式
            if movie[7] and isinstance(movie[7], datetime):  # 假设release_date在索引7位置
                movie[7] = movie[7].strftime('%Y-%m-%d')
                
            # 处理海报路径 (poster_path 在索引位置 4)
            if movie[4] and not movie[4].startswith(('http://', 'https://')):
                movie[4] = f"https://image.tmdb.org/t/p/w500{movie[4]}"
            # 处理背景图路径 (backdrop_path 在索引位置 5)
            if movie[5] and not movie[5].startswith(('http://', 'https://')):
                movie[5] = f"https://image.tmdb.org/t/p/original{movie[5]}"

            # 记录观影历史（只记录已登录的普通用户的，管理员不记录）
            if current_user.is_authenticated and not current_user.is_admin:
                try:
                    # 检查是否已有历史记录
                    cursor.execute(
                        'SELECT id FROM user_watch_history WHERE user_id = %s AND movie_id = %s',
                        (current_user.id, movie_id)
                    )
                    history_record = cursor.fetchone()

                    if history_record:
                        # 更新已有历史记录的时间
                        cursor.execute(
                            'UPDATE user_watch_history SET watched_at = CURRENT_TIMESTAMP WHERE id = %s',
                            (history_record[0],)
                        )
                    else:
                        # 添加新的历史记录
                        cursor.execute(
                            'INSERT INTO user_watch_history (user_id, movie_id) VALUES (%s, %s)',
                            (current_user.id, movie_id)
                        )
                    conn.commit()
                    
                    # 更新电影热度 - 浏览行为
                    try:
                        from movies_recommend.tasks import update_movie_popularity_realtime
                        update_movie_popularity_realtime(movie_id, action_type='view', action_weight=1.0)
                    except Exception as e:
                        # 记录错误但不影响主流程
                        current_app.logger.error(f"更新电影热度失败: {str(e)}")
                        
                except Exception as e:
                    conn.rollback()
                    current_app.logger.warning(f"记录观影历史失败: {e}")

            # 获取电影类型，只从 movies 表的 genres 列中获取
            if movie[12] and isinstance(movie[12], str) and movie[12].strip():  # genres 列在索引位置 12
                movie_genres = [genre.strip() for genre in movie[12].split(',')]
            else:
                # 如果 genres 列为空，则设置为空列表
                movie_genres = []

            # 获取导演信息（可能有多个导演）
            cursor.execute("""
                SELECT p.name
                FROM movie_crew mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s AND mc.job = 'Director'
                ORDER BY p.popularity DESC
            """, (movie_id,))
            directors_raw = cursor.fetchall()
            movie_director = ', '.join([director[0] for director in directors_raw]) if directors_raw else '未知'

            # 获取主要演员（按cast_order排序，只取前5个）
            cursor.execute("""
                SELECT p.name
                FROM movie_cast mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s
                ORDER BY mc.cast_order
                LIMIT 5
            """, (movie_id,))
            actors_raw = cursor.fetchall()
            movie_actors = [actor[0] for actor in actors_raw] if actors_raw else []

        # 检查是否有用户评分，并获取本地评分数据
        sql = "SELECT COUNT(*) FROM user_ratings WHERE movie_id = %s"
        cursor.execute(sql, (movie_id,))
        local_ratings_count = cursor.fetchone()[0]
        has_user_ratings = (local_ratings_count > 0)
        
        # 获取本地用户的平均评分
        if has_user_ratings:
            sql = "SELECT AVG(rating) FROM user_ratings WHERE movie_id = %s"
            cursor.execute(sql, (movie_id,))
            local_avg_rating = cursor.fetchone()[0]
            
            # 更新电影信息中的评分和评分人数
            if local_avg_rating is not None and movie is not None:
                movie[8] = round(float(local_avg_rating), 1)  # 用本地平均评分替换TMDB评分，保留一位小数
                movie[9] = local_ratings_count      # 用本地评分人数替换TMDB评分人数

        # 如果是已登录的普通用户，则获取其评分信息
        if current_user.is_authenticated and not current_user.is_admin:
            cursor.execute(
                'SELECT id, user_id, movie_id, rating, comment, created_at FROM user_ratings WHERE user_id = %s AND movie_id = %s',
                (current_user.id, movie_id)
            )
            user_rating = cursor.fetchone()

        # 获取评论总数
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_ratings
            WHERE movie_id = %s AND comment IS NOT NULL AND comment != ''
            """,
            (movie_id,)
        )
        total_reviews = cursor.fetchone()[0]

        # 计算总页数
        import math
        total_pages = math.ceil(total_reviews / per_page) if total_reviews > 0 else 1

        # 确保页码在有效范围内
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages

        # 计算偏移量
        offset = (page - 1) * per_page

        # 获取分页的用户评论
        cursor.execute(
            """
            SELECT
                ur.id, ur.rating, ur.comment, ur.created_at, u.username,
                COUNT(cl.id) AS like_count,
                MAX(CASE WHEN cl.user_id = %s THEN 1 ELSE 0 END) AS user_liked
            FROM user_ratings ur
            JOIN userinfo u ON ur.user_id = u.id
            LEFT JOIN comment_likes cl ON ur.id = cl.rating_id
            WHERE ur.movie_id = %s AND ur.comment IS NOT NULL AND ur.comment != ''
            GROUP BY ur.id, ur.rating, ur.comment, ur.created_at, u.username
            ORDER BY like_count DESC, ur.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (current_user.id if current_user.is_authenticated else -1, movie_id, per_page, offset)
        )
        reviews_raw = cursor.fetchall()

        # 为每条评论获取回复
        reviews = []
        for review in reviews_raw:
            review_data = list(review)  # 转换为列表以便添加回复数据

            # 获取评论的回复
            cursor.execute(
                """
                SELECT cr.id, cr.content, cr.created_at, u.username, cr.user_id
                FROM comment_replies cr
                JOIN userinfo u ON cr.user_id = u.id
                WHERE cr.rating_id = %s
                ORDER BY cr.created_at ASC
                """,
                (review[0],)  # review[0] 是评论ID
            )
            replies = cursor.fetchall()

            # 将回复添加到评论数据中
            review_data.append(replies)
            reviews.append(review_data)

        # 获取相似电影推荐
        similar_movies = []
        try:
            from movies_recommend.recommender import get_similar_movies
            similar_movies_raw = get_similar_movies(movie_id, n=3)
            # 处理相似电影的海报URL
            for movie_dict in similar_movies_raw:
                if movie_dict.get('image') and not movie_dict['image'].startswith(('http://', 'https://')):
                    movie_dict['image'] = f"https://image.tmdb.org/t/p/w500{movie_dict['image']}"
                similar_movies.append(movie_dict)
        except ImportError:
            # 如果推荐系统不可用，使用基于类型的简单推荐
            if movie_genres:
                # 构建 LIKE 条件进行模糊匹配
                like_conditions = []
                for genre in movie_genres:
                    like_conditions.append(f"genres LIKE '%{genre}%'")

                # 将所有LIKE条件用OR连接
                genres_condition = " OR ".join(like_conditions)

                # 查找具有相同类型的电影
                query = f"""
                SELECT
                    m.id, m.title, m.poster_path as image,
                    m.vote_average as score, m.vote_count
                FROM movies m
                WHERE m.id != %s AND ({genres_condition})
                ORDER BY m.vote_average DESC, m.vote_count DESC
                LIMIT 4
                """

                cursor.execute(query, (movie_id,))
                similar_movies_raw = cursor.fetchall()

                # 将结果转换为字典列表
                for movie in similar_movies_raw:
                    movie_dict = {
                        'id': movie[0],
                        'title': movie[1],
                        'image': movie[2],
                        'score': round(float(movie[3]), 1) if movie[3] is not None else 0.0
                    }
                    if movie_dict['image'] and not movie_dict['image'].startswith(('http://', 'https://')):
                        movie_dict['image'] = f"https://image.tmdb.org/t/p/w500{movie_dict['image']}"
                    similar_movies.append(movie_dict)

        # 判断是否为管理员用户
        is_admin = current_user.is_authenticated and current_user.is_admin

        cursor.close()
        conn.close()

        return render_template(
            'movie_detail.html',
            movie=movie,
            user_rating=user_rating,
            user_reviews=reviews,
            similar_movies=similar_movies,
            is_admin=is_admin,
            has_user_ratings=has_user_ratings,
            local_ratings_count=local_ratings_count,
            movie_genres=movie_genres,
            movie_director=movie_director,
            movie_actors=movie_actors,
            current_page=page,
            total_pages=total_pages,
            total_reviews=total_reviews
        )
    except Exception as e:
        flash(_safe_error_message('获取电影详情失败'), 'error')
        return redirect(url_for('main.show_movies', page=1))

@main_bp.route('/rate_movie/<int:movie_id>', methods=['POST'])
def rate_movie(movie_id):
    """用户对电影进行评分或修改评分

    处理用户提交的电影评分和评论，更新或创建评分记录。
    如果用户未登录，会提示登录。
    支持AJAX请求和传统表单提交。
    被禁言用户不能进行评分或发表评论。

    Args:
        movie_id (int): 要评分的电影ID

    Returns:
        Response: 返回JSON响应或重定向到电影详情页面
    """
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response = {
                'success': False,
                'message': '请先登录'
            }
            return jsonify(response), 403
        else:
            flash('请先登录', 'info')
            return redirect(url_for('main.movie_detail', movie_id=movie_id))
        
    # 如果用户是管理员，不允许评分
    if current_user.is_admin:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response = {
                'success': False,
                'message': '管理员账户不能对电影进行评分'
            }
            return jsonify(response), 403
        else:
            flash('管理员账户不能对电影进行评分', 'error')
            return redirect(url_for('main.movie_detail', movie_id=movie_id))

    # 从表单获取评分和评论数据
    rating_value = request.form.get('rating', type=float)
    comment = (request.form.get('comment') or '').strip()

    # 检查评分值是否有效
    if not rating_value or rating_value < 0.5 or rating_value > 10:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response = {
                'success': False,
                'message': '请提供有效的评分（1-10）'
            }
            return jsonify(response), 400
        else:
            flash('请提供有效的评分（1-10）', 'error')
            return redirect(url_for('main.movie_detail', movie_id=movie_id))

    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 首先检查用户是否被禁言
        cursor.execute(
            'SELECT status, mute_expires_at FROM userinfo WHERE id = %s',
            (current_user.id,)
        )
        user_status = cursor.fetchone()
        
        # 如果用户被禁言，直接返回禁言提示，不允许任何形式的评分操作
        if user_status and user_status[0] == 'banned':
            import datetime
            now = datetime.datetime.now()
            
            # 检查禁言是否已过期
            if user_status[1] and user_status[1] > now:
                # 计算剩余时间
                time_left = user_status[1] - now
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                ban_message = f'您已被禁言，无法进行评分或发表评论。禁言将在{hours}小时{minutes}分钟后解除。'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': ban_message
                    }), 403
                else:
                    flash(ban_message, 'error')
                    return redirect(url_for('main.movie_detail', movie_id=movie_id))
                    
            elif not user_status[1]:  # 永久禁言
                ban_message = '您已被永久禁言，无法进行评分或发表评论。'
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': ban_message
                    }), 403
                else:
                    flash(ban_message, 'error')
                    return redirect(url_for('main.movie_detail', movie_id=movie_id))
            else:
                # 禁言已过期，自动解除
                cursor.execute(
                    'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s',
                    (current_user.id,)
                )
                conn.commit()
        
        # 检查用户是否已经评分过这部电影
        cursor.execute(
            'SELECT id FROM user_ratings WHERE user_id = %s AND movie_id = %s',
            (current_user.id, movie_id)
        )
        existing_rating = cursor.fetchone()

        if existing_rating:
            # 更新现有评分
            cursor.execute(
                'UPDATE user_ratings SET rating = %s, comment = %s WHERE user_id = %s AND movie_id = %s',
                (rating_value, comment, current_user.id, movie_id)
            )
            message = '您的评分已更新'
        else:
            # 创建新评分
            cursor.execute(
                'INSERT INTO user_ratings (user_id, movie_id, rating, comment) VALUES (%s, %s, %s, %s)',
                (current_user.id, movie_id, rating_value, comment)
            )
            message = '您的评分已提交'

        # 更新电影的平均评分
        update_movie_rating(cursor, movie_id)

        # 提交事务 - 先确保评分数据已保存
        conn.commit()
        
        # 在主要操作完成后，尝试更新用户偏好和电影热度
        # 即使这些操作失败，也不会影响评分的提交
        try:
            # 更新用户偏好
            from movies_recommend.user_preferences import update_user_genre_preferences_single_movie
            update_user_genre_preferences_single_movie(current_user.id, movie_id, rating_value)
        except Exception as e:
            current_app.logger.error(f"更新用户偏好失败: {e}")
            # 忽略失败，不影响评分主流程
            
        try:
            # 更新电影热度
            from movies_recommend.tasks import update_movie_popularity_realtime
            # 如果有评论，权重更高
            action_weight = 1.5 if comment else 1.0
            action_type = 'comment' if comment else 'rate'
            # 非阻塞方式更新热度
            update_movie_popularity_realtime(movie_id, action_type=action_type, action_weight=action_weight)
        except Exception as e:
            # 记录错误但不影响主流程
            current_app.logger.error(f"更新电影热度失败: {str(e)}")
        
        # 响应成功
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response = {
                'success': True,
                'message': message
            }
            return jsonify(response)
        else:
            flash(message, 'success')

    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        
        # 响应错误
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response = {
                'success': False,
                'message': _safe_error_message('评分失败')
            }
            return jsonify(response), 500
        else:
            flash(_safe_error_message('评分失败'), 'error')
    finally:
        # 关闭数据库连接
        cursor.close()
        conn.close()

    # 对于非AJAX请求，重定向回电影详情页面
    if not (request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
        return redirect(url_for('main.movie_detail', movie_id=movie_id))

    return jsonify({'success': False, 'message': _safe_error_message('评分失败')}), 500

@main_bp.route('/user_ratings')
@main_bp.route('/user_ratings/<int:page>')
def user_ratings(page=1):
    """用户评分历史页面，支持分页"""
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        flash('请先登录', 'info')
        return render_template('errors/not_authenticated.html')
    
    # 每页显示的评分记录数量
    per_page = 10

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    # 获取总记录数
    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM user_ratings
        WHERE user_id = %s
        ''',
        (current_user.id,)
    )
    total_count = cursor.fetchone()['COUNT(*)']
    
    # 计算总页数
    total_pages = math.ceil(total_count / per_page)
    
    # 确保页码有效
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages
    
    # 使用LIMIT和OFFSET进行分页查询
    cursor.execute(
        '''
        SELECT ur.id, ur.user_id, ur.movie_id, ur.rating, ur.comment, ur.created_at,
               m.title, m.poster_path
        FROM user_ratings ur
        JOIN movies m ON ur.movie_id = m.id
        WHERE ur.user_id = %s
        ORDER BY ur.created_at DESC
        LIMIT %s OFFSET %s
        ''',
        (current_user.id, per_page, (page - 1) * per_page)
    )
    ratings_raw = cursor.fetchall()

    ratings = []
    for item in ratings_raw:
        poster_path = item['poster_path']
        if poster_path and not poster_path.startswith(('http://', 'https://')):
            poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif not poster_path:
            poster_path = url_for('static', filename='img/default-movie-placeholder.png')

        ratings.append({
            'id': item['id'],
            'user_id': item['user_id'],
            'movie_id': item['movie_id'],
            'rating': item['rating'],
            'comment': item['comment'],
            'created_at': item['created_at'],
            'title': item['title'],
            'image': poster_path
        })

    cursor.close()
    conn.close()

    return render_template('user_ratings.html', ratings=ratings, page=page, total_pages=total_pages)

@main_bp.route('/watch_history')
@main_bp.route('/watch_history/<int:page>')
def watch_history(page=1):
    """用户观看历史页面"""
    # 检查用户是否已登录
    if not current_user.is_authenticated:
        flash('请先登录', 'info')
        return render_template('errors/not_authenticated.html')
        
    # 每页显示的记录数量
    per_page = 10

    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取总记录数
    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM user_watch_history
        WHERE user_id = %s
        ''',
        (current_user.id,)
    )
    total_count = cursor.fetchone()[0]

    # 计算总页数
    total_pages = math.ceil(total_count / per_page)

    # 确保页码有效
    if page < 1:
        page = 1
    elif page > total_pages and total_pages > 0:
        page = total_pages

    # 使用LIMIT和OFFSET进行分页查询
    cursor.execute(
        '''
        SELECT uwh.*, m.title, m.poster_path as image
        FROM user_watch_history uwh
        JOIN movies m ON uwh.movie_id = m.id
        WHERE uwh.user_id = %s
        ORDER BY uwh.watched_at DESC
        LIMIT %s OFFSET %s
        ''',
        (current_user.id, per_page, (page - 1) * per_page)
    )
    history_raw = cursor.fetchall()

    # 将元组结果转换为字典列表
    history = []
    for item in history_raw:
        # 处理海报路径
        poster_path = item[5]  # image在索引位置5
        if poster_path and not poster_path.startswith(('http://', 'https://')):
            poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif not poster_path:
            # 使用默认图片占位符
            poster_path = url_for('static', filename='img/default-movie-placeholder.png')

        history.append({
            'id': item[0],
            'user_id': item[1],
            'movie_id': item[2],
            'watched_at': item[3],
            'title': item[4],
            'image': poster_path
        })

    cursor.close()
    conn.close()

    return render_template('watch_history.html', history=history, page=page, total_pages=total_pages)

@main_bp.route('/refresh_similar_movies/<int:movie_id>', methods=['POST'])
def refresh_similar_movies(movie_id):
    """刷新相似电影推荐"""
    try:
        # 检查是否为AJAX请求
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        # 获取当前推荐的电影ID列表(如果有)，用于排除
        current_movie_ids = []
        request_json = request.get_json(silent=True) or {}
        if 'current_movies' in request_json:
            current_movie_ids = normalize_id_list(request_json.get('current_movies', []))

        # 确保movie_id不在排除列表中
        if movie_id in current_movie_ids:
            current_movie_ids.remove(movie_id)

        # 固定返回的电影数量
        fixed_movie_count = 3

        # 结果电影列表
        result_movies = []

        try:
            # 调用推荐系统获取相似电影
            from movies_recommend.recommender import get_similar_movies

            # 检查函数参数
            import inspect
            params = inspect.signature(get_similar_movies).parameters

            # 请求更多电影以确保有足够的选择
            request_count = 10

            # 如果支持排除ID，使用排除参数获取新的相似电影
            if 'exclude_ids' in params:
                similar_movies = get_similar_movies(movie_id, n=request_count, exclude_ids=current_movie_ids)
            else:
                # 不支持排除参数，获取更多电影然后手动过滤
                similar_movies = get_similar_movies(movie_id, n=request_count)

                # 手动过滤排除当前显示的电影
                if current_movie_ids and similar_movies:
                    similar_movies = [movie for movie in similar_movies if movie.get('id') not in current_movie_ids]

            # 确保有电影可选择
            if similar_movies:
                # 随机打乱电影顺序
                import random
                random.shuffle(similar_movies)

                # 只取固定数量的电影
                result_movies = similar_movies[:fixed_movie_count]

                # 如果电影不足，再随机获取一些电影补充
                if len(result_movies) < fixed_movie_count:
                    # 需要补充的数量
                    need_more = fixed_movie_count - len(result_movies)

                    # 记录已选择的电影ID
                    selected_ids = normalize_id_list([movie.get('id') for movie in result_movies])

                    # 获取随机电影补充
                    conn = get_db_connection()
                    cursor = conn.cursor(pymysql.cursors.DictCursor)

                    # 构建排除条件
                    excluded_ids = [movie_id] + current_movie_ids + selected_ids
                    additional_movies = _fetch_random_movie_rows(
                        cursor,
                        limit=need_more,
                        select_columns='id, title, poster_path as image, vote_average as score, vote_count',
                        exclude_ids=excluded_ids,
                    )
                    cursor.close()
                    conn.close()

                    # 处理补充电影的海报路径
                    for movie in additional_movies:
                        if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                            movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                        # 同样随机设置相似度，但比推荐的稍低
                        movie['score'] = float(movie['score']) * 0.8 if movie['score'] else 0.5

                    # 添加到结果列表
                    result_movies.extend(additional_movies)
            else:
                # 如果没有获取到相似电影，获取随机电影
                conn = get_db_connection()
                cursor = conn.cursor(pymysql.cursors.DictCursor)

                # 构建排除条件
                excluded_ids = [movie_id] + current_movie_ids
                result_movies = _fetch_random_movie_rows(
                    cursor,
                    limit=fixed_movie_count,
                    select_columns='id, title, poster_path as image, vote_average as score, vote_count',
                    exclude_ids=excluded_ids,
                )

                # 处理海报路径并添加相似性原因
                for movie in result_movies:
                    if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                        movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                    elif not movie['image']:
                        # 如果没有海报，使用默认海报
                        movie['image'] = "/static/img/default-movie-placeholder.png"

                    # 为随机电影添加默认的相似性原因
                    movie['similarity_reason'] = {
                        'type': 'popular',
                        'reason': "热门推荐"
                    }

                _apply_movie_metadata(cursor, result_movies)

                cursor.close()
                conn.close()

        except Exception as e:
            # 记录错误并获取随机电影作为备选
            current_app.logger.error(f"获取相似电影失败: {e}")

            # 如果无法获取相似电影，返回随机电影
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # 构建排除条件
            excluded_ids = [movie_id] + current_movie_ids
            result_movies = _fetch_random_movie_rows(
                cursor,
                limit=fixed_movie_count,
                select_columns='id, title, poster_path as image, vote_average as score, vote_count',
                exclude_ids=excluded_ids,
            )

            # 处理海报路径并添加相似性原因
            for movie in result_movies:
                if movie['image'] and not movie['image'].startswith(('http://', 'https://')):
                    movie['image'] = f"https://image.tmdb.org/t/p/w500{movie['image']}"
                elif not movie['image']:
                    # 如果没有海报，使用默认海报
                    movie['image'] = "/static/img/default-movie-placeholder.png"

                # 为随机电影添加默认的相似性原因
                movie['similarity_reason'] = {
                    'type': 'popular',
                    'reason': "热门推荐"
                }

            _apply_movie_metadata(cursor, result_movies)

            cursor.close()
            conn.close()

        # 最终确保返回固定数量的电影
        if len(result_movies) > fixed_movie_count:
            result_movies = result_movies[:fixed_movie_count]

        # 记录日志
        current_app.logger.info(f"刷新电影 {movie_id} 的相似推荐，返回 {len(result_movies)} 部电影")

        # 返回成功信息和电影数据
        return jsonify({
            'success': True,
            'message': '已为您推荐相似内容',
            'movies': result_movies
        })

    except Exception as e:
        # 记录错误并返回错误信息
        current_app.logger.error(f"刷新相似电影推荐失败: {e}")
        return jsonify({'success': False, 'message': _safe_error_message('刷新推荐失败')}), 500

@main_bp.route('/user_preferences')
@login_required
def user_preferences():
    """用户电影类型偏好页面"""
    if current_user.is_admin:
        flash('管理员账户不支持此功能', 'warning')
        return redirect(url_for('main.index'))
    
    try:
        # 获取用户的类型偏好
        from movies_recommend.user_preferences import get_user_top_genres
        top_genres = get_user_top_genres(current_user.id, n=10)
        
        if not top_genres:
            return render_template('user_preferences.html', user_genres=None)
        
        # 处理类型数据，添加视觉样式
        user_genres = []
        for genre_name, score in top_genres:
            # 确定徽章和进度条颜色
            if score >= 9:
                badge_class = "bg-primary"
                progress_class = "bg-primary"
            elif score >= 7:
                badge_class = "bg-success"
                progress_class = "bg-success"
            elif score >= 4:
                badge_class = "bg-warning text-dark"
                progress_class = "bg-warning"
            else:
                badge_class = "bg-danger"
                progress_class = "bg-danger"
            
            # 计算百分比宽度
            percentage = max(10, min(100, score * 10))
            
            user_genres.append({
                'name': genre_name,
                'score': score,
                'badge_class': badge_class,
                'progress_class': progress_class,
                'percentage': percentage
            })
        
        return render_template('user_preferences.html', user_genres=user_genres)
    
    except Exception as e:
        current_app.logger.error(f"获取用户类型偏好失败: {e}")
        flash('获取类型偏好数据失败，请稍后再试', 'error')
        return render_template('user_preferences.html', user_genres=None)

@main_bp.route('/refresh_user_preferences', methods=['GET', 'POST'])
@login_required
def refresh_user_preferences():
    """手动刷新用户类型偏好"""
    if current_user.is_admin:
        if request.headers.get('Content-Type') == 'application/json' or request.is_json:
            return jsonify({
                'success': False,
                'message': '管理员账户不支持此功能'
            }), 403
        flash('管理员账户不支持此功能', 'warning')
        return redirect(url_for('main.index'))
    
    # 检查是否为AJAX请求
    is_ajax = request.headers.get('Content-Type') == 'application/json' or request.is_json
    
    try:
        # 导入用户偏好模块
        from movies_recommend.user_preferences import update_user_genre_preferences
        
        # 更新用户类型偏好
        result = update_user_genre_preferences(current_user.id)
        
        if result:
            # 打印调试信息
            from movies_recommend.user_preferences import get_user_top_genres
            top_genres = get_user_top_genres(current_user.id, n=10)
            current_app.logger.debug(f"用户偏好数据: {top_genres}")
            
            if is_ajax:
                return jsonify({
                    'success': True,
                    'message': '您的电影类型偏好已成功更新'
                })
            flash('您的电影类型偏好已成功更新', 'success')
        else:
            if is_ajax:
                return jsonify({
                    'success': False,
                    'message': '无法生成类型偏好，您可能需要对更多不同类型的电影进行评分'
                })
            flash('无法生成类型偏好，您可能需要对更多不同类型的电影进行评分', 'warning')
    
    except Exception as e:
        current_app.logger.error(f"手动刷新用户 {current_user.id} 类型偏好失败: {e}")
        if is_ajax:
            return jsonify({
                'success': False,
                'message': '更新类型偏好数据失败，请稍后再试'
            }), 500
        flash('更新类型偏好数据失败，请稍后再试', 'error')
    
    return redirect(url_for('main.user_preferences'))
