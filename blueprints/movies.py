"""电影蓝图，当前仅保留搜索页面路由。"""

import math
import logging
from datetime import datetime

from flask import Blueprint, render_template, request, url_for, jsonify

from movies_recommend.extensions import get_db_connection
from movies_recommend.request_utils import is_api_request as is_json_request
from movies_recommend.tasks import update_movie_popularity_realtime


movies_bp = Blueprint('movies', __name__)
logger = logging.getLogger(__name__)


@movies_bp.route('/search')
def search_movies():
    """搜索电影，支持按标题、演员、导演模糊匹配。"""
    keyword = (request.args.get('keyword') or '').strip()
    sort_by = request.args.get('sort', 'hot')
    page = request.args.get('page', type=int) or 1
    per_page = 9
    conn = get_db_connection()
    movies_list = []
    total_pages = 1

    if keyword:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM movies
                    WHERE title LIKE %s
                    LIMIT 20
                    """,
                    (f'%{keyword}%',)
                )
                search_movie_ids = [row[0] for row in cursor.fetchall()]

                for movie_id in search_movie_ids:
                    update_movie_popularity_realtime(movie_id, action_type='search', action_weight=1.0)

                logger.info(f"已为 {len(search_movie_ids)} 部与关键词 '{keyword}' 匹配的电影更新搜索热度")
        except Exception as error:
            logger.error(f"更新搜索热度失败: {error}")

    try:
        with conn.cursor() as cursor:
            if not keyword:
                cursor.execute('SELECT COUNT(*) FROM movies')
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
                like_kw = f'%{keyword}%'
                cursor.execute(
                    '''
                    SELECT COUNT(*)
                    FROM movies
                    WHERE title LIKE %s OR original_title LIKE %s
                    ''',
                    (like_kw, like_kw)
                )
                title_count = cursor.fetchone()[0]

                cursor.execute(
                    '''
                    SELECT COUNT(DISTINCT m.id)
                    FROM movie_cast mc
                    JOIN persons p ON mc.person_id = p.id
                    JOIN movies m ON mc.movie_id = m.id
                    WHERE p.name LIKE %s
                    ''',
                    (like_kw,)
                )
                actor_count = cursor.fetchone()[0]

                cursor.execute(
                    '''
                    SELECT COUNT(DISTINCT m.id)
                    FROM movie_crew mw
                    JOIN persons p ON mw.person_id = p.id
                    JOIN movies m ON mw.movie_id = m.id
                    WHERE mw.job = 'Director' AND p.name LIKE %s
                    ''',
                    (like_kw,)
                )
                director_count = cursor.fetchone()[0]

                total_movies = title_count + actor_count + director_count
                total_pages = math.ceil(total_movies / per_page)

                movie_ids = set()

                cursor.execute(
                    '''
                    SELECT id
                    FROM movies
                    WHERE title LIKE %s OR original_title LIKE %s
                    ''',
                    (like_kw, like_kw)
                )
                movie_ids.update([row[0] for row in cursor.fetchall()])

                cursor.execute(
                    '''
                    SELECT DISTINCT mc.movie_id
                    FROM movie_cast mc
                    JOIN persons p ON mc.person_id = p.id
                    WHERE p.name LIKE %s
                    ''',
                    (like_kw,)
                )
                movie_ids.update([row[0] for row in cursor.fetchall()])

                cursor.execute(
                    '''
                    SELECT DISTINCT mw.movie_id
                    FROM movie_crew mw
                    JOIN persons p ON mw.person_id = p.id
                    WHERE mw.job = 'Director' AND p.name LIKE %s
                    ''',
                    (like_kw,)
                )
                movie_ids.update([row[0] for row in cursor.fetchall()])

                movie_ids = list(movie_ids)

                if not movie_ids:
                    movies = []
                else:
                    placeholders = ','.join(['%s'] * len(movie_ids))
                    base_sql = f'''
                        SELECT id, title, poster_path, release_date, vote_average, genres, popularity
                        FROM movies
                        WHERE id IN ({placeholders})
                    '''

                    if sort_by == 'hot':
                        base_sql += ' ORDER BY popularity DESC, vote_average DESC'
                    elif sort_by == 'rating':
                        base_sql += ' ORDER BY vote_average DESC, vote_count DESC'
                    elif sort_by == 'time':
                        base_sql += ' ORDER BY release_date DESC'
                    else:
                        base_sql += ' ORDER BY popularity DESC'

                    cursor.execute(base_sql, movie_ids)
                    all_movies = cursor.fetchall()

                    start_idx = (page - 1) * per_page
                    end_idx = start_idx + per_page
                    movies = all_movies[start_idx:end_idx] if start_idx < len(all_movies) else []

            for movie in movies:
                vote_avg = round(float(movie[4]), 1) if movie[4] is not None else 0
                formatted_vote = f"{vote_avg:.1f}" if movie[4] is not None else "N/A"

                try:
                    cursor.execute(
                        '''
                        SELECT p.name
                        FROM movie_cast mc
                        JOIN persons p ON mc.person_id = p.id
                        WHERE mc.movie_id = %s
                        ORDER BY mc.cast_order
                        LIMIT 3
                        ''',
                        (movie[0],)
                    )
                    actors_raw = cursor.fetchall()
                    actors = ', '.join([actor[0] for actor in actors_raw]) if actors_raw else '未知'
                except Exception as error:
                    logger.warning(f"获取电影 {movie[0]} 的演员信息失败: {error}")
                    actors = '未知'

                poster_path = movie[2]
                if poster_path and not poster_path.startswith(('http://', 'https://')):
                    poster_path = f"https://image.tmdb.org/t/p/w500{poster_path}"
                elif not poster_path:
                    poster_path = url_for('static', filename='img/default-movie-placeholder.png')

                if movie[3]:
                    if isinstance(movie[3], datetime):
                        release_date = movie[3].strftime('%Y-%m-%d')
                    else:
                        release_date = str(movie[3])
                else:
                    release_date = '未知'

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
    except Exception as error:
        logger.error(f"搜索电影时发生错误: {error}")
        movies_list = []
        total_pages = 1
    finally:
        conn.close()

    if is_json_request(request):
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
