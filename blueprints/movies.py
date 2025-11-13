"""
电影蓝图，处理电影详情、评分等功能
"""
import os
import sys
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from flask_login import current_user, login_required
from movies_recommend.extensions import get_db_connection
import pymysql
import math
import logging
from datetime import datetime

# 导入实时热度更新函数
from movies_recommend.tasks import update_movie_popularity_realtime

# 创建蓝图
movies_bp = Blueprint('movies', __name__)

# 获取日志记录器
logger = logging.getLogger(__name__)

@movies_bp.route('/movies', endpoint='show_movies_root')
@movies_bp.route('/movies/<int:page>', endpoint='show_movies_page')
def show_movies(page=1):
    """显示电影列表页面"""
    # 获取URL参数
    sort_by = request.args.get('sort', 'hot')  # 默认按热门排序
    
    # 记录请求参数以便调试
    logger.info(f"收到请求: URL={request.url}")
    logger.info(f"请求参数: page={page}, sort_by={sort_by}")
    logger.info(f"所有请求参数: {dict(request.args)}")
    
    per_page = 9  # 改为9个，适合3x3的网格布局

    conn = get_db_connection()
    movies = []
    total_pages = 1
    
    try:
        with conn.cursor() as cursor:
            # 构建基础SQL查询
            base_sql = '''
                SELECT id, title, poster_path AS image, release_date AS release_time, 
                       vote_average AS score, genres, popularity 
                FROM movies 
            '''
            count_sql = 'SELECT COUNT(*) FROM movies'
            params = []
            
            # 获取总记录数
            cursor.execute(count_sql)
            total_count = cursor.fetchone()[0]
            logger.info(f"总记录数: {total_count}")

            # 计算总页数
            total_pages = math.ceil(total_count / per_page)
            logger.info(f"总页数: {total_pages}, 每页记录数: {per_page}")

            # 确保页码有效
            if page < 1:
                page = 1
            elif page > total_pages and total_pages > 0:
                page = total_pages
                
            # 添加排序
            if sort_by == 'time':
                # 按上映时间降序排序（最新的排在前面）
                base_sql += ' ORDER BY release_date DESC'
            elif sort_by == 'rating':
                # 按评分降序排序，同时考虑评分人数
                base_sql += ' ORDER BY vote_average DESC, vote_count DESC'
            else:  # 默认按热门排序(sort_by == 'hot')
                # 按人气降序排序
                base_sql += ' ORDER BY popularity DESC'
            
            logger.info(f"应用排序: sort_by={sort_by}")
            
            # 添加分页
            base_sql += ' LIMIT %s OFFSET %s'
            params.extend([per_page, (page - 1) * per_page])
            
            # 执行查询
            logger.info(f"最终SQL: {base_sql}")
            logger.info(f"最终参数: {params}")
            
            cursor.execute(base_sql, params)
            movies_raw = cursor.fetchall()
            
            # 记录结果数量
            logger.info(f"查询到 {len(movies_raw)} 部电影")

            # 处理电影海报路径、类型和演员信息
            movies = []
            json_movies = []  # 用于JSON响应
            for movie in movies_raw:
                movie_id, title, poster_path, release_date, score, genres_str, popularity = movie
                # 如果海报路径存在且不是完整URL，添加基础URL
                if poster_path and not poster_path.startswith(('http://', 'https://')):
                    poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
                elif not poster_path:
                    # 使用默认图片占位符
                    poster_path = url_for('static', filename='img/default-movie-placeholder.png')

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

                # 将元组改为字典，与search_movies保持一致
                # 确保评分为最多一位小数
                vote_avg = round(float(score), 1) if score is not None else None
                
                movie_dict = {
                    'id': movie_id,
                    'title': title,
                    'poster_path': poster_path,
                    'release_date': release_date.strftime('%Y-%m-%d') if release_date else None,
                    'vote_average': vote_avg,
                    'genres': genres,
                    'popularity': float(popularity) if popularity is not None else None,
                    'actors': actors
                }
                movies.append(movie_dict)
                json_movies.append(movie_dict)  # JSON响应可以直接使用相同的字典
                
    except Exception as e:
        logger.error(f"查询电影列表出错: {e}")
        flash(f"获取电影列表失败: {str(e)}", "error")
        movies = []
        json_movies = []
        total_pages = 1
    finally:
        conn.close()

    # 判断是否为管理员用户
    is_admin = current_user.is_authenticated and current_user.is_admin
        
    # 调试信息：输出传递给模板的数据
    logger.info(f"传递给模板的结果: {len(movies)}部电影, 当前页={page}, 总页数={total_pages}")
    
    # 检查是否为API请求（Postman等）
    is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
    
    # 如果是API请求，返回JSON
    if is_api_request:
        return jsonify({
            'movies': json_movies,
            'page': page,
            'total_pages': total_pages,
            'sort_by': sort_by
        })

    return render_template(
        'movies.html', 
        movies=movies, 
        page=page, 
        total_pages=total_pages, 
        is_admin=is_admin, 
        sort_by=sort_by
    )

@movies_bp.route('/search')
def search_movies():
    """搜索电影功能，支持电影名、导演、演员模糊搜索，极致性能优化"""
    keyword = request.args.get('keyword', '').strip()
    sort_by = request.args.get('sort', 'hot')
    page = request.args.get('page', 1, type=int)
    per_page = 9
    conn = get_db_connection()
    movies_list = []
    total_pages = 1
    
    # 如果有搜索关键词，更新相关电影的热度
    if keyword:
        try:
            # 获取搜索到的电影ID
            with conn.cursor() as cursor:
                # 使用简单查询获取匹配电影的ID
                cursor.execute("""
                    SELECT id FROM movies 
                    WHERE title LIKE %s 
                    LIMIT 20
                """, (f'%{keyword}%',))
                search_movie_ids = [row[0] for row in cursor.fetchall()]
                
                # 为每个匹配的电影增加搜索热度
                for movie_id in search_movie_ids:
                    update_movie_popularity_realtime(movie_id, action_type='search', action_weight=1.0)
                    
                logger.info(f"已为 {len(search_movie_ids)} 部与关键词 '{keyword}' 匹配的电影更新搜索热度")
        except Exception as e:
            logger.error(f"更新搜索热度失败: {e}")
    
    try:
        with conn.cursor() as cursor:
            if not keyword:
                # 无关键词，极致性能：只查movies表
                count_sql = 'SELECT COUNT(*) FROM movies'
                cursor.execute(count_sql)
                total_movies = cursor.fetchone()[0]
                total_pages = math.ceil(total_movies / per_page)
                base_sql = '''
                    SELECT id, title, poster_path, release_date, vote_average, genres, popularity
                    FROM movies
                    ORDER BY popularity DESC
                    LIMIT %s OFFSET %s
                '''
                cursor.execute(base_sql, (per_page, (page - 1) * per_page))
                movies = cursor.fetchall()
            else:
                # 使用简化的搜索逻辑，确保显示所有匹配的电影
                # 直接使用LIKE查询匹配电影标题
                like_kw = f'%{keyword}%'
                cursor.execute('''
                    SELECT COUNT(*) 
                    FROM movies 
                    WHERE title LIKE %s OR original_title LIKE %s
                ''', (like_kw, like_kw))
                title_count = cursor.fetchone()[0]
                
                # 获取匹配演员的电影数量
                cursor.execute('''
                    SELECT COUNT(DISTINCT m.id)
                    FROM movie_cast mc 
                    JOIN persons p ON mc.person_id=p.id 
                    JOIN movies m ON mc.movie_id=m.id 
                    WHERE p.name LIKE %s
                ''', (like_kw,))
                actor_count = cursor.fetchone()[0]
                
                # 获取匹配导演的电影数量
                cursor.execute('''
                    SELECT COUNT(DISTINCT m.id)
                    FROM movie_crew mw 
                    JOIN persons p ON mw.person_id=p.id 
                    JOIN movies m ON mw.movie_id=m.id 
                    WHERE mw.job='Director' AND p.name LIKE %s
                ''', (like_kw,))
                director_count = cursor.fetchone()[0]
                
                # 估算总电影数量（可能有重复，但这只是用于分页计算）
                total_movies = title_count + actor_count + director_count
                total_pages = math.ceil(total_movies / per_page)
                
                # 获取所有匹配的电影ID
                movie_ids = set()
                
                # 1. 匹配电影标题
                cursor.execute('''
                    SELECT id 
                    FROM movies 
                    WHERE title LIKE %s OR original_title LIKE %s
                ''', (like_kw, like_kw))
                movie_ids.update([row[0] for row in cursor.fetchall()])
                
                # 2. 匹配演员
                cursor.execute('''
                    SELECT DISTINCT m.id
                    FROM movie_cast mc 
                    JOIN persons p ON mc.person_id=p.id 
                    JOIN movies m ON mc.movie_id=m.id 
                    WHERE p.name LIKE %s
                ''', (like_kw,))
                movie_ids.update([row[0] for row in cursor.fetchall()])
                
                # 3. 匹配导演
                cursor.execute('''
                    SELECT DISTINCT m.id
                    FROM movie_crew mw 
                    JOIN persons p ON mw.person_id=p.id 
                    JOIN movies m ON mw.movie_id=m.id 
                    WHERE mw.job='Director' AND p.name LIKE %s
                ''', (like_kw,))
                movie_ids.update([row[0] for row in cursor.fetchall()])
                
                # 转为列表并更新总数
                movie_ids = list(movie_ids)
                total_movies = len(movie_ids)
                total_pages = math.ceil(total_movies / per_page)
                
                # 分页切片
                if not movie_ids:
                    movies = []
                else:
                    # 应用排序并获取分页数据
                    format_strings = ','.join(['%s'] * len(movie_ids))
                    base_sql = f'''
                        SELECT id, title, poster_path, release_date, vote_average, genres, popularity 
                        FROM movies 
                        WHERE id IN ({format_strings})
                    '''
                    
                    # 排序
                    if sort_by == 'hot':
                        base_sql += ' ORDER BY popularity DESC, vote_average DESC'
                    elif sort_by == 'rating':
                        base_sql += ' ORDER BY vote_average DESC, vote_count DESC'
                    elif sort_by == 'time':
                        base_sql += ' ORDER BY release_date DESC'
                    else:
                        base_sql += ' ORDER BY popularity DESC'
                    
                    # 执行查询获取所有匹配的电影
                    cursor.execute(base_sql, movie_ids)
                    all_movies = cursor.fetchall()
                    
                    # 手动分页
                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    movies = all_movies[start_idx:end_idx] if start_idx < len(all_movies) else []
                    
            # 组装结果
            for movie in movies:
                # 确保评分为最多一位小数
                vote_avg = round(float(movie[4]), 1) if movie[4] is not None else 0
                formatted_vote = f"{vote_avg:.1f}" if movie[4] is not None else "N/A"
                # 获取演员信息
                try:
                    cursor.execute('''
                        SELECT p.name
                        FROM movie_cast mc
                        JOIN persons p ON mc.person_id = p.id
                        WHERE mc.movie_id = %s
                        ORDER BY mc.cast_order
                        LIMIT 3
                    ''', (movie[0],))
                    actors_raw = cursor.fetchall()
                    actors = ', '.join([actor[0] for actor in actors_raw]) if actors_raw else '未知'
                except Exception as e:
                    logger.warning(f"获取电影 {movie[0]} 的演员信息失败: {e}")
                    actors = '未知'
                # 处理海报路径
                poster_path = movie[2]
                if poster_path and not poster_path.startswith(('http://', 'https://')):
                    poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
                elif not poster_path:
                    poster_path = url_for('static', filename='img/default-movie-placeholder.png')
                # 处理发布日期
                if movie[3]:
                    if isinstance(movie[3], datetime):
                        release_date = movie[3].strftime('%Y-%m-%d')
                    else:
                        release_date = str(movie[3])
                else:
                    release_date = "未知"
                movie_dict = {
                    'id': movie[0],
                    'title': movie[1],
                    'poster_path': poster_path,
                    'release_date': release_date,
                    'vote_average': formatted_vote,
                    'genres': movie[5].split(',') if movie[5] else [],
                    'popularity': float(movie[6]) if movie[6] is not None else 0,
                    'actors': actors
                }
                movies_list.append(movie_dict)
    except Exception as e:
        logger.error(f"搜索电影时发生错误: {e}")
        movies_list = []
        total_pages = 1
    finally:
        conn.close()
    # 检查是否为API请求
    is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
    if is_api_request:
        return jsonify({
            'movies': movies_list,
            'page': page,
            'total_pages': total_pages,
            'keyword': keyword,
            'sort_by': sort_by
        })
    return render_template(
        'movies.html',
        movies=movies_list,
        page=page,
        total_pages=total_pages,
        keyword=keyword,
        sort_by=sort_by
    )

@movies_bp.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    """显示电影详情页面"""
    conn = get_db_connection()
    movie = None
    similar_movies = []
    user_rating = None
    
    try:
        # 更新电影浏览热度
        update_movie_popularity_realtime(movie_id, action_type='view', action_weight=1.0)
        logger.info(f"已更新电影 {movie_id} 的浏览热度")
        
        with conn.cursor() as cursor:
            # 获取电影基本信息
            cursor.execute("""
                SELECT id, title, poster_path, backdrop_path, overview, 
                       release_date, vote_average, vote_count, popularity, genres
                FROM movies
                WHERE id = %s
            """, (movie_id,))
            movie_data = cursor.fetchone()
            
            if not movie_data:
                logger.error(f"电影不存在: id={movie_id}")
                
                # 检查是否为API请求
                is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
                if is_api_request:
                    return jsonify({'error': '电影不存在'}), 404
                    
                flash("电影不存在", "error")
                return redirect(url_for('movies.show_movies_root'))
            
            # 处理电影信息
            id, title, poster_path, backdrop_path, overview, release_date, vote_average, vote_count, popularity, genres_str = movie_data
            
            # 如果海报路径存在且不是完整URL，添加基础URL
            if poster_path and not poster_path.startswith(('http://', 'https://')):
                poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
            elif not poster_path:
                # 使用默认图片占位符
                poster_path = url_for('static', filename='img/default-movie-placeholder.png')
            
            # 如果背景图路径存在且不是完整URL，添加基础URL
            if backdrop_path and not backdrop_path.startswith(('http://', 'https://')):
                backdrop_path = f"https://image.tmdb.org/t/p/original{backdrop_path}"
            elif not backdrop_path:
                # 使用默认背景图占位符
                backdrop_path = url_for('static', filename='img/default-backdrop-placeholder.png')
            
            # 处理电影类型
            genres = genres_str.split(',') if genres_str else []
            genres = [genre.strip() for genre in genres if genre.strip()]
            
            # 获取电影演员信息
            cursor.execute("""
                SELECT p.id, p.name, mc.character, p.profile_path
                FROM movie_cast mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s
                ORDER BY mc.cast_order
                LIMIT 8
            """, (movie_id,))
            cast_data = cursor.fetchall()
            
            cast = []
            for actor in cast_data:
                actor_id, name, character, profile_path = actor
                # 处理演员头像路径
                if profile_path and not profile_path.startswith(('http://', 'https://')):
                    profile_path = f"https://image.tmdb.org/t/p/w185{profile_path}"
                elif not profile_path:
                    # 使用默认头像占位符
                    profile_path = url_for('static', filename='img/default-profile-placeholder.png')
                cast.append({
                    'id': actor_id,
                    'name': name,
                    'character': character,
                    'profile_path': profile_path
                })
            
            # 获取导演信息
            cursor.execute("""
                SELECT p.id, p.name
                FROM movie_crew mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s AND mc.job = 'Director'
                LIMIT 3
            """, (movie_id,))
            directors_data = cursor.fetchall()
            directors = [{'id': d[0], 'name': d[1]} for d in directors_data]
            
            # 构建电影对象
            movie = {
                'id': id,
                'title': title,
                'poster_path': poster_path,
                'backdrop_path': backdrop_path,
                'overview': overview,
                'release_date': release_date.strftime('%Y-%m-%d') if release_date else None,
                'vote_average': float(vote_average) if vote_average is not None else None,
                'vote_count': vote_count,
                'popularity': float(popularity) if popularity is not None else None,
                'genres': genres,
                'cast': cast,
                'directors': directors
            }
            
            # 获取用户评分
            if current_user.is_authenticated:
                cursor.execute("""
                    SELECT rating, created_at
                    FROM user_ratings
                    WHERE user_id = %s AND movie_id = %s
                """, (current_user.id, movie_id))
                rating_data = cursor.fetchone()
                if rating_data:
                    user_rating = {
                        'score': float(rating_data[0]),
                        'date': rating_data[1].strftime('%Y-%m-%d %H:%M:%S') if rating_data[1] else None
                    }
            
            # 获取相似电影
            cursor.execute("""
                SELECT m.id, m.title, m.poster_path, m.vote_average
                FROM movies m
                WHERE m.id != %s AND m.genres LIKE %s
                ORDER BY m.vote_average DESC, m.popularity DESC
                LIMIT 12
            """, (movie_id, f"%{genres[0]}%" if genres else '%'))
            similar_movies_data = cursor.fetchall()
            
            similar_movies = []
            for similar in similar_movies_data:
                sim_id, sim_title, sim_poster, sim_vote = similar
                # 处理海报路径
                if sim_poster and not sim_poster.startswith(('http://', 'https://')):
                    sim_poster = f"https://image.tmdb.org/t/p/w300{sim_poster}"
                elif not sim_poster:
                    # 使用默认图片占位符
                    sim_poster = url_for('static', filename='img/default-movie-placeholder.png')
                similar_movies.append({
                    'id': sim_id,
                    'title': sim_title,
                    'poster_path': sim_poster,
                    'vote_average': float(sim_vote) if sim_vote is not None else None
                })
            
    except Exception as e:
        logger.error(f"获取电影详情失败: {e}")
        
        # 检查是否为API请求
        is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
        if is_api_request:
            return jsonify({'error': f'获取电影详情失败: {str(e)}'}), 500
            
        flash(f"获取电影详情失败: {str(e)}", "error")
        return redirect(url_for('movies.show_movies_root'))
    finally:
        conn.close()
    
    # 检查是否为API请求
    is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
    if is_api_request:
        return jsonify({
            'movie': movie,
            'similar_movies': similar_movies,
            'user_rating': user_rating
        })
    
    return render_template(
        'movie_detail.html', 
        movie=movie, 
        similar_movies=similar_movies,
        user_rating=user_rating
    )

@movies_bp.route('/rate_movie/<int:movie_id>', methods=['POST'])
@login_required
def rate_movie(movie_id):
    """给电影评分"""
    # 获取JSON数据或表单数据
    if request.is_json:
        data = request.get_json()
        score = data.get('score')
    else:
        score = request.form.get('score')
        
    # 检查评分值是否有效
    try:
        score = float(score)
        if score < 0 or score > 10:
            raise ValueError("评分必须在0-10之间")
    except (ValueError, TypeError) as e:
        logger.error(f"评分无效: {e}")
        
        # 检查是否API请求
        is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
        if is_api_request:
            return jsonify({'error': f'评分无效: {str(e)}'}), 400
            
        flash("评分必须是0-10之间的数字", "error")
        return redirect(url_for('movies.movie_detail', movie_id=movie_id))
    
    # 检查电影是否存在
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM movies WHERE id = %s", (movie_id,))
            movie = cursor.fetchone()
            if not movie:
                logger.error(f"电影不存在: id={movie_id}")
                
                # 检查是否API请求
                is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
                if is_api_request:
                    return jsonify({'error': '电影不存在'}), 404
                    
                flash("电影不存在", "error")
                return redirect(url_for('movies.show_movies_root'))
            
            # 检查用户是否已经评分过这部电影
            cursor.execute(
                "SELECT id FROM user_ratings WHERE user_id = %s AND movie_id = %s", 
                (current_user.id, movie_id)
            )
            existing_rating = cursor.fetchone()
            
            if existing_rating:
                # 更新现有评分
                cursor.execute(
                    "UPDATE user_ratings SET rating = %s, created_at = NOW() WHERE user_id = %s AND movie_id = %s",
                    (score, current_user.id, movie_id)
                )
                logger.info(f"用户 {current_user.id} 更新了电影 {movie_id} 的评分: {score}")
                # 评分更新，热度增加较少
                update_movie_popularity_realtime(movie_id, action_type='rate', action_weight=0.7)
            else:
                # 新增评分
                cursor.execute(
                    "INSERT INTO user_ratings (user_id, movie_id, rating, created_at) VALUES (%s, %s, %s, NOW())",
                    (current_user.id, movie_id, score)
                )
                logger.info(f"用户 {current_user.id} 对电影 {movie_id} 进行了评分: {score}")
                # 新增评分，热度增加较多
                update_movie_popularity_realtime(movie_id, action_type='rate', action_weight=1.5)
            
            conn.commit()
            
            # 检查是否API请求
            is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
            if is_api_request:
                return jsonify({
                    'success': True,
                    'message': f'电影评分成功: {score}',
                    'movie_id': movie_id,
                    'score': score
                })
                
            flash(f"评分成功: {score}", "success")
    except Exception as e:
        logger.error(f"评分出错: {e}")
        conn.rollback()
        
        # 检查是否API请求
        is_api_request = 'application/json' in request.headers.get('Accept', '') or 'Postman' in request.headers.get('User-Agent', '')
        if is_api_request:
            return jsonify({'error': f'评分失败: {str(e)}'}), 500
            
        flash(f"评分失败: {str(e)}", "error")
    finally:
        conn.close()
    
    return redirect(url_for('movies.movie_detail', movie_id=movie_id))

@movies_bp.route('/refresh_similar_movies/<int:movie_id>', methods=['POST'])
@login_required
def refresh_similar_movies(movie_id):
    """刷新相似电影推荐"""
    try:
        # 获取当前显示的电影ID列表
        exclude_ids = request.json.get('exclude_ids', []) if request.is_json else []
        
        # 获取新的相似电影
        from movies_recommend.recommender import get_similar_movies
        similar_movies = get_similar_movies(movie_id, 3, exclude_ids)
        
        logger.info(f"刷新电影 {movie_id} 的相似推荐，返回 {len(similar_movies)} 部电影")
        
        return jsonify({
            'success': True,
            'movies': similar_movies
        })
    except Exception as e:
        logger.error(f"刷新相似电影推荐失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
