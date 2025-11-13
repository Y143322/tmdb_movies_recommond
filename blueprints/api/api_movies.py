"""
电影API模块 - 提供RESTful风格的电影相关接口
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

import math
from flask import request, jsonify, current_app
from flask_login import login_required, current_user
import pymysql
from movies_recommend.extensions import get_db_connection
from movies_recommend.blueprints.api import api_bp
from movies_recommend.logger import get_logger

logger = get_logger('api_movies')


def api_response(success=True, message='', data=None, code=200):
    """统一API响应格式"""
    response = {
        'code': code,
        'success': success,
        'message': message
    }
    if data is not None:
        response['data'] = data
    return jsonify(response), code


def format_movie_data(movie_data, cursor=None):
    """格式化电影数据
    
    Args:
        movie_data: 电影原始数据（字典）
        cursor: 数据库游标（可选，用于查询额外信息）
    
    Returns:
        dict: 格式化后的电影数据
    """
    movie = dict(movie_data)
    
    # 处理海报路径
    poster_path = movie.get('poster_path') or movie.get('image')
    if poster_path and not poster_path.startswith(('http://', 'https://')):
        movie['posterPath'] = f"https://image.tmdb.org/t/p/w500{poster_path}"
    else:
        movie['posterPath'] = poster_path or ''
    
    # 处理背景图片
    backdrop_path = movie.get('backdrop_path')
    if backdrop_path and not backdrop_path.startswith(('http://', 'https://')):
        movie['backdropPath'] = f"https://image.tmdb.org/t/p/original{backdrop_path}"
    else:
        movie['backdropPath'] = backdrop_path or ''
    
    # 统一字段名（camelCase）
    formatted = {
        'id': movie.get('id'),
        'title': movie.get('title'),
        'originalTitle': movie.get('original_title'),
        'overview': movie.get('overview'),
        'posterPath': movie['posterPath'],
        'backdropPath': movie['backdropPath'],
        'releaseDate': str(movie.get('release_date')) if movie.get('release_date') else None,
        'releaseTime': str(movie.get('release_time')) if movie.get('release_time') else None,
        'popularity': float(movie.get('popularity', 0)) if movie.get('popularity') else None,
        'voteAverage': float(movie.get('vote_average', 0)) if movie.get('vote_average') else float(movie.get('score', 0)) if movie.get('score') else None,
        'voteCount': movie.get('vote_count'),
        'genres': movie.get('genres', ''),
    }
    
    return formatted


@api_bp.route('/movies', methods=['GET'])
def get_movies():
    """获取电影列表
    
    GET /api/movies?page=1&pageSize=10&sort=hot
    
    Query Parameters:
        page: 页码（默认1）
        pageSize: 每页数量（默认10）
        sort: 排序方式 hot/time/rating（默认hot）
    
    Returns:
        {
            "code": 200,
            "success": true,
            "message": "获取成功",
            "data": {
                "list": [...],
                "total": 1000,
                "page": 1,
                "pageSize": 10,
                "totalPages": 100
            }
        }
    """
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)
        sort_by = request.args.get('sort', 'hot')
        
        # 参数验证
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 50:
            page_size = 10
        if sort_by not in ['hot', 'time', 'rating']:
            sort_by = 'hot'
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取总记录数
            cursor.execute('SELECT COUNT(*) as total FROM movies')
            total = cursor.fetchone()['total']
            total_pages = math.ceil(total / page_size)
            
            # 确保页码有效
            if page > total_pages and total_pages > 0:
                page = total_pages
            
            # 构建查询SQL
            base_sql = '''
                SELECT id, title, original_title, overview, poster_path, backdrop_path,
                       release_date, popularity, vote_average, vote_count, genres
                FROM movies
            '''
            
            # 添加排序
            if sort_by == 'time':
                base_sql += ' ORDER BY release_date DESC'
            elif sort_by == 'rating':
                base_sql += ' ORDER BY vote_average DESC, vote_count DESC'
            else:  # hot
                base_sql += ' ORDER BY popularity DESC'
            
            # 添加分页
            offset = (page - 1) * page_size
            base_sql += ' LIMIT %s OFFSET %s'
            
            cursor.execute(base_sql, (page_size, offset))
            movies_raw = cursor.fetchall()
            
            # 格式化电影数据
            movies_list = [format_movie_data(movie, cursor) for movie in movies_raw]
            
            return api_response(
                success=True,
                message='获取成功',
                data={
                    'list': movies_list,
                    'total': total,
                    'page': page,
                    'pageSize': page_size,
                    'totalPages': total_pages
                }
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"获取电影列表失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/<int:movie_id>', methods=['GET'])
def get_movie_detail(movie_id):
    """获取电影详情
    
    GET /api/movies/:id
    
    Returns:
        电影详细信息，包括演员、剧组、关键词等
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取电影基本信息
            cursor.execute('''
                SELECT id, title, original_title, overview, poster_path, backdrop_path,
                       release_date, popularity, vote_average, vote_count, genres,
                       runtime, budget, revenue, tagline, status
                FROM movies
                WHERE id = %s
            ''', (movie_id,))
            
            movie = cursor.fetchone()
            if not movie:
                return api_response(False, '电影不存在', code=404)
            
            # 格式化基本信息
            movie_detail = format_movie_data(movie)
            movie_detail['runtime'] = movie.get('runtime')
            movie_detail['budget'] = movie.get('budget')
            movie_detail['revenue'] = movie.get('revenue')
            movie_detail['tagline'] = movie.get('tagline')
            movie_detail['status'] = movie.get('status')
            
            # 获取演员信息
            cursor.execute('''
                SELECT p.id, p.name, mc.character_name as roleName, mc.cast_order as `order`
                FROM movie_cast mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s
                ORDER BY mc.cast_order
                LIMIT 20
            ''', (movie_id,))
            movie_detail['cast'] = list(cursor.fetchall())
            
            # 获取剧组信息
            cursor.execute('''
                SELECT p.id, p.name, mc.job, mc.department
                FROM movie_crew mc
                JOIN persons p ON mc.person_id = p.id
                WHERE mc.movie_id = %s
                ORDER BY 
                    CASE mc.job
                        WHEN 'Director' THEN 1
                        WHEN 'Producer' THEN 2
                        WHEN 'Screenplay' THEN 3
                        ELSE 4
                    END
                LIMIT 20
            ''', (movie_id,))
            movie_detail['crew'] = list(cursor.fetchall())
            
            # 获取关键词
            cursor.execute('''
                SELECT k.name
                FROM movie_keywords mk
                JOIN keywords k ON mk.keyword_id = k.id
                WHERE mk.movie_id = %s
                LIMIT 10
            ''', (movie_id,))
            keywords = cursor.fetchall()
            movie_detail['keywords'] = [k['name'] for k in keywords]
            
            # 获取制作公司
            cursor.execute('''
                SELECT c.name
                FROM movie_production_companies mpc
                JOIN production_companies c ON mpc.company_id = c.id
                WHERE mpc.movie_id = %s
            ''', (movie_id,))
            companies = cursor.fetchall()
            movie_detail['productionCompanies'] = [c['name'] for c in companies]
            
            return api_response(
                success=True,
                message='获取成功',
                data=movie_detail
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"获取电影详情失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/random', methods=['GET'])
def get_random_movies():
    """获取随机电影
    
    GET /api/movies/random?count=5
    """
    try:
        count = request.args.get('count', 5, type=int)
        if count < 1 or count > 20:
            count = 5
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            cursor.execute('''
                SELECT id, title, poster_path, release_date, vote_average, genres, popularity
                FROM movies
                ORDER BY RAND()
                LIMIT %s
            ''', (count,))
            
            movies_raw = cursor.fetchall()
            movies_list = [format_movie_data(movie) for movie in movies_raw]
            
            return api_response(
                success=True,
                message='获取成功',
                data=movies_list
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"获取随机电影失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/recommendations', methods=['GET'])
@login_required
def get_recommendations():
    """获取个性化推荐
    
    GET /api/movies/recommendations
    
    需要登录。管理员返回随机电影，普通用户返回个性化推荐。
    """
    try:
        # 检查是否是管理员
        if current_user.is_admin:
            logger.info(f"管理员用户 {current_user.id} 请求推荐，返回随机电影")
            # 管理员返回随机电影
            return get_random_movies()
        
        # 普通用户获取个性化推荐
        from movies_recommend.recommender import get_recommendations_for_user
        
        recommended_ids = get_recommendations_for_user(current_user.id, n=10)
        
        if not recommended_ids:
            logger.warning(f"用户 {current_user.id} 未获取到推荐，返回随机电影")
            return get_random_movies()
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 查询推荐电影的完整信息
            placeholders = ', '.join(['%s'] * len(recommended_ids))
            cursor.execute(f'''
                SELECT id, title, poster_path, release_date, vote_average, genres, popularity
                FROM movies
                WHERE id IN ({placeholders})
            ''', recommended_ids)
            
            movies_raw = cursor.fetchall()
            
            # 按照推荐顺序排序
            movies_dict = {movie['id']: movie for movie in movies_raw}
            movies_ordered = [movies_dict[mid] for mid in recommended_ids if mid in movies_dict]
            
            movies_list = [format_movie_data(movie) for movie in movies_ordered]
            
            logger.info(f"为用户 {current_user.id} 返回 {len(movies_list)} 个推荐")
            
            return api_response(
                success=True,
                message='获取成功',
                data=movies_list
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"获取推荐失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/recommendations/refresh', methods=['POST'])
@login_required
def refresh_recommendations():
    """刷新推荐电影列表

    POST /api/movies/recommendations/refresh
    Body: {"current_movies": [电影ID列表]}

    返回新的推荐电影列表，排除当前已显示的电影
    """
    try:
        data = request.get_json() or {}
        current_movies = data.get('current_movies', [])

        # 检查是否是管理员
        if current_user.is_admin:
            logger.info(f"管理员用户 {current_user.id} 刷新推荐，返回随机电影")
            return get_random_movies()

        # 普通用户获取个性化推荐
        from movies_recommend.recommender import get_recommendations_for_user

        # 获取更多推荐（20个），然后排除已显示的
        recommended_ids = get_recommendations_for_user(current_user.id, n=20)

        # 过滤掉当前已显示的电影
        filtered_ids = [mid for mid in recommended_ids if mid not in current_movies]

        # 如果过滤后不够，返回随机电影
        if len(filtered_ids) < 6:
            logger.warning(f"用户 {current_user.id} 刷新推荐后数量不足，返回随机电影")
            return get_random_movies()

        # 取前10个
        filtered_ids = filtered_ids[:10]

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        try:
            # 查询推荐电影的完整信息
            placeholders = ', '.join(['%s'] * len(filtered_ids))
            cursor.execute(f'''
                SELECT id, title, poster_path, release_date, vote_average, genres, popularity
                FROM movies
                WHERE id IN ({placeholders})
            ''', filtered_ids)

            movies_raw = cursor.fetchall()

            # 按照推荐顺序排序
            movies_dict = {movie['id']: movie for movie in movies_raw}
            movies_ordered = [movies_dict[mid] for mid in filtered_ids if mid in movies_dict]

            movies_list = [format_movie_data(movie) for movie in movies_ordered]

            logger.info(f"为用户 {current_user.id} 刷新推荐，返回 {len(movies_list)} 个新推荐")

            return api_response(
                success=True,
                message='刷新成功',
                data=movies_list
            )

        finally:
            cursor.close()
            conn.close()

    except Exception as e:
        logger.error(f"刷新推荐失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/search', methods=['GET'])
def search_movies():
    """搜索电影
    
    GET /api/movies/search?keyword=xxx&page=1&pageSize=10
    """
    try:
        keyword = request.args.get('keyword', '').strip()
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)
        
        if not keyword:
            return api_response(False, '搜索关键词不能为空', code=400)
        
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 50:
            page_size = 10
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取匹配的总数
            count_sql = '''
                SELECT COUNT(DISTINCT m.id) as total
                FROM movies m
                LEFT JOIN movie_cast mc ON m.id = mc.movie_id
                LEFT JOIN persons p ON mc.person_id = p.id
                LEFT JOIN movie_crew mcr ON m.id = mcr.movie_id
                LEFT JOIN persons d ON mcr.person_id = d.id AND mcr.job = 'Director'
                WHERE m.title LIKE %s OR p.name LIKE %s OR d.name LIKE %s
            '''
            search_pattern = f'%{keyword}%'
            cursor.execute(count_sql, (search_pattern, search_pattern, search_pattern))
            total = cursor.fetchone()['total']
            total_pages = math.ceil(total / page_size)
            
            if page > total_pages and total_pages > 0:
                page = total_pages
            
            # 搜索电影
            search_sql = '''
                SELECT DISTINCT m.id, m.title, m.poster_path, m.release_date, 
                       m.vote_average, m.genres, m.popularity
                FROM movies m
                LEFT JOIN movie_cast mc ON m.id = mc.movie_id
                LEFT JOIN persons p ON mc.person_id = p.id
                LEFT JOIN movie_crew mcr ON m.id = mcr.movie_id
                LEFT JOIN persons d ON mcr.person_id = d.id AND mcr.job = 'Director'
                WHERE m.title LIKE %s OR p.name LIKE %s OR d.name LIKE %s
                ORDER BY m.popularity DESC
                LIMIT %s OFFSET %s
            '''
            
            offset = (page - 1) * page_size
            cursor.execute(search_sql, (search_pattern, search_pattern, search_pattern, page_size, offset))
            movies_raw = cursor.fetchall()
            
            movies_list = [format_movie_data(movie) for movie in movies_raw]
            
            return api_response(
                success=True,
                message='搜索成功',
                data={
                    'list': movies_list,
                    'total': total,
                    'page': page,
                    'pageSize': page_size,
                    'totalPages': total_pages
                }
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"搜索电影失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/<int:movie_id>/rating', methods=['POST'])
@login_required
def submit_rating(movie_id):
    """提交电影评分
    
    POST /api/movies/:id/rating
    Body: {
        "rating": 4.5,
        "comment": "很好看"
    }
    """
    try:
        # 检查是否是管理员
        if current_user.is_admin:
            return api_response(False, '管理员不能评分', code=403)
        
        data = request.get_json()
        if not data:
            return api_response(False, '请求数据格式错误', code=400)
        
        rating = data.get('rating')
        comment = data.get('comment', '').strip()
        
        # 验证评分
        if rating is None:
            return api_response(False, '评分不能为空', code=400)
        
        try:
            rating = float(rating)
        except ValueError:
            return api_response(False, '评分格式错误', code=400)
        
        if rating < 0 or rating > 10:
            return api_response(False, '评分必须在0-10之间', code=400)
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 检查电影是否存在
            cursor.execute('SELECT id FROM movies WHERE id = %s', (movie_id,))
            if not cursor.fetchone():
                return api_response(False, '电影不存在', code=404)
            
            # 检查用户是否已评分
            cursor.execute('''
                SELECT id FROM user_ratings 
                WHERE user_id = %s AND movie_id = %s
            ''', (current_user.id, movie_id))
            
            existing_rating = cursor.fetchone()
            
            if existing_rating:
                # 更新评分
                cursor.execute('''
                    UPDATE user_ratings
                    SET rating = %s, comment = %s, created_at = NOW()
                    WHERE id = %s
                ''', (rating, comment, existing_rating['id']))
                message = '评分更新成功'
            else:
                # 插入新评分
                cursor.execute('''
                    INSERT INTO user_ratings (user_id, movie_id, rating, comment, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                ''', (current_user.id, movie_id, rating, comment))
                message = '评分提交成功'
            
            # 更新电影的平均评分
            cursor.execute('''
                SELECT AVG(rating) as avg_rating, COUNT(*) as count
                FROM user_ratings
                WHERE movie_id = %s
            ''', (movie_id,))
            
            result = cursor.fetchone()
            if result and result['avg_rating']:
                avg_rating = round(float(result['avg_rating']), 1)
                count = int(result['count'])
                cursor.execute('''
                    UPDATE movies
                    SET vote_average = %s, vote_count = %s
                    WHERE id = %s
                ''', (avg_rating, count, movie_id))
            
            conn.commit()
            
            # 更新用户类型偏好
            try:
                from movies_recommend.user_preferences import update_user_genre_preferences
                update_user_genre_preferences(current_user.id)
            except Exception as e:
                logger.warning(f"更新用户偏好失败: {str(e)}")
            
            logger.info(f"用户 {current_user.id} 对电影 {movie_id} 评分: {rating}")
            
            return api_response(success=True, message=message)
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"提交评分失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/<int:movie_id>/ratings', methods=['GET'])
def get_movie_ratings(movie_id):
    """获取电影的评分列表
    
    GET /api/movies/:id/ratings?page=1&pageSize=10
    """
    try:
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)
        
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 50:
            page_size = 10
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取总评分数
            cursor.execute('''
                SELECT COUNT(*) as total
                FROM user_ratings
                WHERE movie_id = %s
            ''', (movie_id,))
            total = cursor.fetchone()['total']
            total_pages = math.ceil(total / page_size)
            
            if page > total_pages and total_pages > 0:
                page = total_pages
            
            # 获取评分列表
            offset = (page - 1) * page_size
            cursor.execute('''
                SELECT ur.id, ur.user_id as userId, ur.movie_id as movieId,
                       ur.rating, ur.comment, ur.created_at as createdAt,
                       u.username
                FROM user_ratings ur
                JOIN userinfo u ON ur.user_id = u.id
                WHERE ur.movie_id = %s
                ORDER BY ur.created_at DESC
                LIMIT %s OFFSET %s
            ''', (movie_id, page_size, offset))
            
            ratings = cursor.fetchall()
            
            # 格式化日期
            for rating in ratings:
                if rating['createdAt']:
                    rating['createdAt'] = rating['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
            
            return api_response(
                success=True,
                message='获取成功',
                data={
                    'list': ratings,
                    'total': total,
                    'page': page,
                    'pageSize': page_size,
                    'totalPages': total_pages
                }
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"获取评分列表失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)


@api_bp.route('/movies/<int:movie_id>/rating/<int:rating_id>', methods=['DELETE'])
@login_required
def delete_rating(movie_id, rating_id):
    """删除评分
    
    DELETE /api/movies/:movie_id/rating/:rating_id
    
    普通用户只能删除自己的评分，管理员可以删除任何评分
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 获取评分信息
            cursor.execute('''
                SELECT user_id, movie_id
                FROM user_ratings
                WHERE id = %s
            ''', (rating_id,))
            
            rating = cursor.fetchone()
            if not rating:
                return api_response(False, '评分不存在', code=404)
            
            # 权限检查
            if not current_user.is_admin and rating['user_id'] != current_user.id:
                return api_response(False, '无权删除他人的评分', code=403)
            
            # 删除评分
            cursor.execute('DELETE FROM user_ratings WHERE id = %s', (rating_id,))
            
            # 更新电影的平均评分
            cursor.execute('''
                SELECT AVG(rating) as avg_rating, COUNT(*) as count
                FROM user_ratings
                WHERE movie_id = %s
            ''', (movie_id,))
            
            result = cursor.fetchone()
            if result and result['avg_rating']:
                avg_rating = round(float(result['avg_rating']), 1)
                count = int(result['count'])
                cursor.execute('''
                    UPDATE movies
                    SET vote_average = %s, vote_count = %s
                    WHERE id = %s
                ''', (avg_rating, count, movie_id))
            else:
                # 如果没有评分了，重置为0
                cursor.execute('''
                    UPDATE movies
                    SET vote_count = 0
                    WHERE id = %s
                ''', (movie_id,))
            
            conn.commit()
            
            logger.info(f"用户 {current_user.id} 删除了评分 {rating_id}")
            
            return api_response(success=True, message='删除成功')
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"删除评分失败: {str(e)}")
        return api_response(False, f'服务器错误: {str(e)}', code=500)

