"""
RESTful API蓝图，为Vue前端提供数据接口
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import math

from movies_recommend.extensions import get_db_connection
from movies_recommend.logger import get_logger

# 创建蓝图
api_bp = Blueprint('api', __name__, url_prefix='/api')
logger = get_logger('api')

# ============ 认证相关API ============

@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    """API登录接口"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 先检查管理员
        cursor.execute('SELECT * FROM admininfo WHERE username = %s', (username,))
        user_data = cursor.fetchone()
        is_admin = True
        
        # 如果不是管理员，检查普通用户
        if not user_data:
            cursor.execute('SELECT * FROM userinfo WHERE username = %s', (username,))
            user_data = cursor.fetchone()
            is_admin = False
        
        if user_data and check_password_hash(user_data['password'], password):
            # 创建JWT token
            token = create_access_token(identity={'id': user_data['id'], 'is_admin': is_admin})
            
            return jsonify({
                'success': True,
                'data': {
                    'token': token,
                    'user': {
                        'id': user_data['id'],
                        'username': user_data['username'],
                        'email': user_data.get('email'),
                        'is_admin': is_admin
                    }
                },
                'message': '登录成功'
            })
        else:
            return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
            
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({'success': False, 'message': f'登录失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@api_bp.route('/auth/register', methods=['POST'])
def api_register():
    """API注册接口"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    email = data.get('email', '')
    user_type = data.get('user_type', 'normal')
    
    # 输入验证
    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
    
    if len(username) < 3 or len(username) > 20:
        return jsonify({'success': False, 'message': '用户名长度需在3-20个字符之间'}), 400
    
    if len(password) < 8:
        return jsonify({'success': False, 'message': '密码长度至少需要8个字符'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查用户名是否已存在
        cursor.execute('SELECT id FROM userinfo WHERE username = %s', (username,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '用户名已存在'}), 400
        
        cursor.execute('SELECT id FROM admininfo WHERE username = %s', (username,))
        if cursor.fetchone():
            return jsonify({'success': False, 'message': '用户名已存在'}), 400
        
        # 哈希密码
        hashed_password = generate_password_hash(password)
        
        # 获取下一个用户ID
        is_admin = (user_type == 'admin')
        cursor.execute("CALL get_next_user_id(@next_id, %s)", ('admin' if is_admin else 'user',))
        cursor.execute("SELECT @next_id")
        next_id = cursor.fetchone()[0]
        
        # 插入用户
        if is_admin:
            cursor.execute(
                'INSERT INTO admininfo (id, username, password, email) VALUES (%s, %s, %s, %s)',
                (next_id, username, hashed_password, email)
            )
        else:
            cursor.execute(
                'INSERT INTO userinfo (id, username, password, email) VALUES (%s, %s, %s, %s)',
                (next_id, username, hashed_password, email)
            )
        
        conn.commit()
        
        # 创建JWT token
        token = create_access_token(identity={'id': next_id, 'is_admin': is_admin})
        
        return jsonify({
            'success': True,
            'data': {
                'token': token,
                'user': {
                    'id': next_id,
                    'username': username,
                    'email': email,
                    'is_admin': is_admin
                }
            },
            'message': '注册成功'
        })
        
    except Exception as e:
        conn.rollback()
        logger.error(f"注册失败: {e}")
        return jsonify({'success': False, 'message': f'注册失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@api_bp.route('/auth/profile', methods=['GET'])
@jwt_required()
def api_get_profile():
    """获取用户信息"""
    current_user = get_jwt_identity()
    user_id = current_user['id']
    is_admin = current_user.get('is_admin', False)
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        if is_admin:
            cursor.execute('SELECT * FROM admininfo WHERE id = %s', (user_id,))
        else:
            cursor.execute('SELECT * FROM userinfo WHERE id = %s', (user_id,))
        
        user_data = cursor.fetchone()
        
        if user_data:
            return jsonify({
                'success': True,
                'data': {
                    'id': user_data['id'],
                    'username': user_data['username'],
                    'email': user_data.get('email'),
                    'is_admin': is_admin,
                    'created_at': str(user_data.get('created_at', ''))
                }
            })
        else:
            return jsonify({'success': False, 'message': '用户不存在'}), 404
            
    except Exception as e:
        logger.error(f"获取用户信息失败: {e}")
        return jsonify({'success': False, 'message': f'获取用户信息失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

# ============ 电影相关API ============

@api_bp.route('/movies', methods=['GET'])
def api_get_movies():
    """获取电影列表"""
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort', 'hot')
    per_page = 9
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 获取总数
        cursor.execute('SELECT COUNT(*) as count FROM movies')
        total_count = cursor.fetchone()['count']
        total_pages = math.ceil(total_count / per_page)
        
        # 构建查询
        order_by = {
            'hot': 'popularity DESC',
            'time': 'release_date DESC',
            'rating': 'vote_average DESC, vote_count DESC'
        }.get(sort_by, 'popularity DESC')
        
        query = f"""
            SELECT id, title, poster_path, release_date, vote_average, 
                   genres, popularity
            FROM movies
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        cursor.execute(query, (per_page, (page - 1) * per_page))
        movies = cursor.fetchall()
        
        # 处理电影数据
        for movie in movies:
            if movie['poster_path'] and not movie['poster_path'].startswith('http'):
                movie['poster_path'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            if movie['genres']:
                movie['genres'] = [g.strip() for g in movie['genres'].split(',')]
            else:
                movie['genres'] = []
        
        return jsonify({
            'success': True,
            'data': {
                'movies': movies,
                'page': page,
                'total_pages': total_pages
            }
        })
        
    except Exception as e:
        logger.error(f"获取电影列表失败: {e}")
        return jsonify({'success': False, 'message': f'获取电影列表失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@api_bp.route('/movies/<int:movie_id>', methods=['GET'])
def api_get_movie_detail(movie_id):
    """获取电影详情"""
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 获取电影基本信息
        cursor.execute("""
            SELECT id, title, original_title, poster_path, backdrop_path, 
                   overview, release_date, vote_average, vote_count, 
                   popularity, genres, original_language
            FROM movies WHERE id = %s
        """, (movie_id,))
        
        movie = cursor.fetchone()
        if not movie:
            return jsonify({'success': False, 'message': '电影不存在'}), 404
        
        # 处理图片路径
        if movie['poster_path'] and not movie['poster_path'].startswith('http'):
            movie['poster_path'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
        if movie['backdrop_path'] and not movie['backdrop_path'].startswith('http'):
            movie['backdrop_path'] = f"https://image.tmdb.org/t/p/original{movie['backdrop_path']}"
        
        # 处理类型
        if movie['genres']:
            movie['genres'] = [g.strip() for g in movie['genres'].split(',')]
        else:
            movie['genres'] = []
        
        # 获取导演
        cursor.execute("""
            SELECT p.id, p.name
            FROM movie_crew mc
            JOIN persons p ON mc.person_id = p.id
            WHERE mc.movie_id = %s AND mc.job = 'Director'
            LIMIT 3
        """, (movie_id,))
        movie['directors'] = [{'id': d['id'], 'name': d['name']} for d in cursor.fetchall()]
        
        # 获取演员
        cursor.execute("""
            SELECT p.id, p.name, mc.role_name as character
            FROM movie_cast mc
            JOIN persons p ON mc.person_id = p.id
            WHERE mc.movie_id = %s
            ORDER BY mc.cast_order
            LIMIT 8
        """, (movie_id,))
        movie['cast'] = list(cursor.fetchall())
        
        return jsonify({'success': True, 'data': movie})
        
    except Exception as e:
        logger.error(f"获取电影详情失败: {e}")
        return jsonify({'success': False, 'message': f'获取电影详情失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@api_bp.route('/recommendations', methods=['POST'])
@jwt_required()
def api_get_recommendations():
    """获取个性化推荐"""
    current_user = get_jwt_identity()
    user_id = current_user['id']
    data = request.get_json() or {}
    exclude_ids = data.get('current_movies', [])
    
    try:
        from movies_recommend.recommender import get_recommendations_for_user
        recommended_ids = get_recommendations_for_user(user_id, n=10, exclude_ids=exclude_ids)
        
        if not recommended_ids:
            # 返回随机电影
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT id, title, poster_path, vote_average as score, release_date
                FROM movies
                ORDER BY RAND()
                LIMIT 5
            """)
            movies = cursor.fetchall()
            cursor.close()
            conn.close()
        else:
            # 获取推荐电影详情
            conn = get_db_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            placeholders = ','.join(['%s'] * len(recommended_ids))
            cursor.execute(f"""
                SELECT id, title, poster_path, vote_average as score, release_date
                FROM movies
                WHERE id IN ({placeholders})
            """, recommended_ids)
            movies = cursor.fetchall()
            cursor.close()
            conn.close()
        
        # 处理图片路径
        for movie in movies:
            if movie['poster_path'] and not movie['poster_path'].startswith('http'):
                movie['poster_path'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
        
        return jsonify({'success': True, 'data': {'movies': movies}})
        
    except Exception as e:
        logger.error(f"获取推荐失败: {e}")
        return jsonify({'success': False, 'message': f'获取推荐失败: {str(e)}'}), 500

@api_bp.route('/movies/<int:movie_id>/rating', methods=['POST'])
@jwt_required()
def api_submit_rating(movie_id):
    """提交电影评分"""
    current_user = get_jwt_identity()
    user_id = current_user['id']
    
    data = request.get_json()
    rating = data.get('rating')
    comment = data.get('comment', '').strip()
    
    if not rating or rating < 0.5 or rating > 10:
        return jsonify({'success': False, 'message': '评分必须在0.5-10之间'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 检查是否已评分
        cursor.execute(
            'SELECT id FROM user_ratings WHERE user_id = %s AND movie_id = %s',
            (user_id, movie_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute(
                'UPDATE user_ratings SET rating = %s, comment = %s WHERE user_id = %s AND movie_id = %s',
                (rating, comment, user_id, movie_id)
            )
        else:
            cursor.execute(
                'INSERT INTO user_ratings (user_id, movie_id, rating, comment) VALUES (%s, %s, %s, %s)',
                (user_id, movie_id, rating, comment)
            )
        
        conn.commit()
        
        return jsonify({'success': True, 'message': '评分成功'})
        
    except Exception as e:
        conn.rollback()
        logger.error(f"提交评分失败: {e}")
        return jsonify({'success': False, 'message': f'提交评分失败: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

