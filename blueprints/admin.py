#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
管理员控制面板蓝图
处理所有管理员相关的路由和功能
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from movies_recommend.extensions import get_db_connection  # 导入数据库连接函数
import pymysql  # MySQL数据库驱动
import logging

# 从logger模块获取日志记录器
from movies_recommend.logger import get_logger
logger = get_logger('admin')

# 导入电影热度更新任务
from movies_recommend.tasks import update_movie_popularity

# 创建管理员蓝图，设置URL前缀为/admin，所有管理员路由都将以/admin开头
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# 管理员权限检查装饰器
def admin_required(f):
    """检查用户是否为管理员的装饰器

    这个装饰器用于保护管理员路由，确保只有管理员用户才能访问这些路由。
    它首先检查用户是否已登录，然后检查用户是否具有管理员权限。
    如果不满足条件，将重定向到首页并显示错误消息。

    Args:
        f (function): 被装饰的视图函数

    Returns:
        function: 包装后的函数，会先检查管理员权限
    """
    def decorated_function(*args, **kwargs):
        # 检查用户是否已登录且是管理员
        if not current_user.is_authenticated or not current_user.is_admin:
            # 如果不是管理员，显示错误消息并重定向到首页
            flash('您没有权限访问此页面', 'error')
            return redirect(url_for('main.index'))
        # 如果是管理员，则执行原始视图函数
        return f(*args, **kwargs)
    # 保留原始函数名，这对于Flask的路由系统很重要
    decorated_function.__name__ = f.__name__
    # 组合login_required装饰器，确保用户已登录
    return login_required(decorated_function)

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """管理员仪表盘页面

    显示系统概览信息，包括用户数量、电影数量、评分数量等统计数据。
    这是管理员登录后的首页，提供系统整体状态的快照视图。

    Returns:
        Response: 渲染后的仪表盘页面
    """
    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 查询普通用户数量（存储在userinfo表中）
        cursor.execute("SELECT COUNT(*) FROM userinfo")
        normal_users = cursor.fetchone()[0]

        # 查询管理员用户数量（存储在admininfo表中）
        cursor.execute("SELECT COUNT(*) FROM admininfo")
        admin_users = cursor.fetchone()[0]

        # 计算总用户数（普通用户 + 管理员）
        total_users = normal_users + admin_users

        # 查询系统中的电影总数
        cursor.execute("SELECT COUNT(*) FROM movies")
        total_movies = cursor.fetchone()[0]

        # 查询用户评分总数
        cursor.execute("SELECT COUNT(*) FROM user_ratings")
        total_ratings = cursor.fetchone()[0]



    except Exception as e:
        # 如果查询过程中出现任何错误，将所有统计数据设为0
        total_users, total_movies, total_ratings = 0, 0, 0
        # 显示错误消息
        flash(f'获取统计数据失败: {e}', 'error')
    finally:
        # 确保无论如何都关闭数据库连接
        cursor.close()
        conn.close()

    # 渲染仪表盘模板，传入统计数据
    return render_template('admin/dashboard.html',
                           total_users=total_users,
                           total_movies=total_movies,
                           total_ratings=total_ratings)

@admin_bp.route('/reviews')
@admin_bp.route('/reviews/<int:page>')
@admin_required
def reviews(page=1):
    """管理员评论审核页面

    显示所有用户评论的列表，支持分页。管理员可以在此页面查看、删除评论，
    以及回复用户评论。评论按创建时间倒序排列，每页显示固定数量的评论。
    
    支持按电影名称、用户名、评论内容关键词和评分进行筛选。

    Args:
        page (int, optional): 当前页码，默认为1

    Returns:
        Response: 渲染后的评论管理页面
    """
    # 设置每页显示的评论数量
    per_page = 10
    
    # 获取筛选参数
    movie_filter = request.args.get('movie', '').strip()
    user_filter = request.args.get('user', '').strip()
    keyword_filter = request.args.get('keyword', '').strip()
    rating_filter = request.args.get('rating', '').strip()

    # 获取数据库连接，使用字典游标便于处理结果
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    try:
        # 构建查询条件
        where_clauses = []
        query_params = []
        
        # 电影名称筛选
        if movie_filter:
            where_clauses.append("m.title LIKE %s")
            query_params.append(f"%{movie_filter}%")
        
        # 用户名筛选
        if user_filter:
            where_clauses.append("u.username LIKE %s")
            query_params.append(f"%{user_filter}%")
        
        # 评论内容关键词筛选
        if keyword_filter:
            where_clauses.append("ur.comment LIKE %s")
            query_params.append(f"%{keyword_filter}%")
        
        # 评分筛选
        if rating_filter and rating_filter.isdigit():
            where_clauses.append("ur.rating = %s")
            query_params.append(int(rating_filter))
        
        # 组装WHERE子句
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # 查询评论总数，用于计算分页
        count_query = f"""
            SELECT COUNT(*) as total 
            FROM user_ratings ur
            JOIN userinfo u ON ur.user_id = u.id
            JOIN movies m ON ur.movie_id = m.id
            WHERE {where_clause}
        """
        cursor.execute(count_query, query_params)
        total_count = cursor.fetchone()['total']

        # 计算总页数（向上取整）
        import math
        total_pages = math.ceil(total_count / per_page)

        # 验证页码有效性，确保在合理范围内
        if page < 1:
            page = 1  # 如果页码小于1，设为第1页
        elif page > total_pages and total_pages > 0:
            page = total_pages  # 如果页码超过总页数，设为最后一页

        # 计算SQL查询的OFFSET值
        offset = (page - 1) * per_page

        # 查询当前页的评论数据，包括用户名和电影标题
        data_query = f"""
            SELECT ur.id, ur.rating, ur.comment, ur.created_at,
                   u.username, m.title as movie_title, m.id as movie_id
            FROM user_ratings ur
            JOIN userinfo u ON ur.user_id = u.id
            JOIN movies m ON ur.movie_id = m.id
            WHERE {where_clause}
            ORDER BY ur.created_at DESC
            LIMIT %s OFFSET %s
        """
        # 添加分页参数
        all_params = query_params + [per_page, offset]
        cursor.execute(data_query, all_params)
        reviews_raw = cursor.fetchall()

        # 为每条评论获取相关的回复信息
        reviews = []
        for review in reviews_raw:
            # 查询该评论下的所有回复
            cursor.execute("""
                SELECT cr.id, cr.content, cr.created_at, u.username, u.id as user_id
                FROM comment_replies cr
                JOIN userinfo u ON cr.user_id = u.id
                WHERE cr.rating_id = %s
                ORDER BY cr.created_at ASC
            """, (review['id'],))
            replies = cursor.fetchall()

            # 将回复数据添加到评论对象中
            review['replies'] = replies
            reviews.append(review)

    except Exception as e:
        # 如果查询过程中出现错误，设置空数据并显示错误消息
        reviews = []
        total_pages = 0
        flash(f'获取评论失败: {e}', 'error')
    finally:
        # 确保关闭数据库连接
        cursor.close()
        conn.close()

    # 渲染评论管理页面，传入评论数据和分页信息
    return render_template('admin/reviews.html', reviews=reviews, page=page, total_pages=total_pages)

@admin_bp.route('/delete_review/<int:review_id>', methods=['POST'])
@admin_required
def delete_review(review_id):
    """删除用户评论

    管理员可以删除任何用户的评论。删除评论时，相关的回复也会被级联删除
    （如果数据库设置了外键约束）。

    Args:
        review_id (int): 要删除的评论ID

    Returns:
        Response: 重定向到评论管理页面
    """
    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 执行删除操作
        cursor.execute("DELETE FROM user_ratings WHERE id = %s", (review_id,))
        # 提交事务
        conn.commit()
        # 显示成功消息
        flash('评论已删除', 'success')
    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        # 显示错误消息
        flash(f'删除评论失败: {e}', 'error')
    finally:
        # 确保关闭数据库连接
        cursor.close()
        conn.close()

    # 重定向回评论管理页面
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/delete_reply/<int:reply_id>', methods=['POST'])
@admin_required
def delete_reply(reply_id):
    """删除评论回复

    管理员可以删除任何评论下的回复，包括用户的回复和管理员自己的回复。

    Args:
        reply_id (int): 要删除的回复ID

    Returns:
        Response: 重定向到评论管理页面
    """
    # 获取数据库连接
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 执行删除操作
        cursor.execute("DELETE FROM comment_replies WHERE id = %s", (reply_id,))
        # 提交事务
        conn.commit()
        # 显示成功消息
        flash('回复已删除', 'success')
    except Exception as e:
        # 如果发生错误，回滚事务
        conn.rollback()
        # 显示错误消息
        flash(f'删除回复失败: {e}', 'error')
    finally:
        # 确保关闭数据库连接
        cursor.close()
        conn.close()

    # 重定向回评论管理页面
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/reply_comment/<int:rating_id>', methods=['POST'])
@admin_required
def admin_reply_comment(rating_id):
    """管理员回复评论

    管理员不应直接参与评论，此函数仅返回提示信息。

    Args:
        rating_id (int): 要回复的评论ID

    Returns:
        Response: 重定向到评论管理页面并显示提示消息
    """
    # 显示提示消息
    flash('管理员不参与评论', 'info')
    
    # 重定向回评论管理页面
    return redirect(url_for('admin.reviews'))

@admin_bp.route('/update_status')
@admin_required
def update_status():
    """显示电影数据更新状态和控制页面

    提供电影数据更新的管理界面，管理员可以在此页面触发电影数据的爬取和更新操作。
    该页面包含更新按钮和更新状态显示，以及最近一次更新的时间和结果。
    实际的爬虫状态检查和启动操作由前端JavaScript通过AJAX请求完成。

    Returns:
        Response: 渲染后的更新状态页面
    """
    # 此路由仅渲染模板，实际的状态检查和启动由前端JS完成
    return render_template('admin/update_status.html')

@admin_bp.route('/movies')
@admin_bp.route('/movies/<int:page>')
@admin_required
def movies(page=1):
    """管理员电影管理页面

    显示系统中所有电影的列表，支持分页、排序和搜索。管理员可以在此页面查看电影详情，
    编辑电影信息，或删除电影。支持按ID、评分、标题和发布日期排序，以便管理员
    根据不同需求查看电影数据。支持按标题、类型、评分范围等条件搜索。

    Args:
        page (int, optional): 当前页码，默认为1

    Query Parameters:
        sort (str): 排序字段，可选值为id、vote_average、title、release_date
        order (str): 排序方向，可选值为asc（升序）或desc（降序）
        title (str): 按电影标题搜索
        genre (str): 按电影类型搜索
        min_rating/max_rating (float): 按评分范围搜索

    Returns:
        Response: 渲染后的电影管理页面
    """
    # 设置每页显示的电影数量
    per_page = 10

    # 从URL查询参数中获取排序设置，默认按ID升序排列
    sort = request.args.get('sort', 'id')
    order = request.args.get('order', 'asc')
    
    # 从URL查询参数中获取搜索条件
    title = request.args.get('title', '').strip()
    genre = request.args.get('genre', '').strip()
    min_rating = request.args.get('min_rating', '').strip()
    max_rating = request.args.get('max_rating', '').strip()

    # 验证排序字段，防止SQL注入攻击
    # 只允许使用预定义的字段进行排序
    valid_sort_fields = {'id', 'vote_average', 'title', 'release_date'}
    if sort not in valid_sort_fields:
        sort = 'id'  # 如果不是有效字段，默认使用ID排序

    # 验证排序方向，只允许升序或降序
    if order not in ['asc', 'desc']:
        order = 'desc'  # 如果不是有效方向，默认使用降序

    try:
        # 获取数据库连接，使用字典游标便于处理结果
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 构建SQL查询条件
        where_clauses = []
        params = []
        
        # 按标题搜索
        if title:
            where_clauses.append('title LIKE %s')
            params.append(f'%{title}%')
        
        # 按电影类型搜索
        if genre:
            where_clauses.append('genres LIKE %s')
            params.append(f'%{genre}%')
            
        # 按评分范围搜索
        if min_rating and min_rating.replace('.', '', 1).isdigit():
            where_clauses.append('vote_average >= %s')
            params.append(float(min_rating))
        if max_rating and max_rating.replace('.', '', 1).isdigit():
            where_clauses.append('vote_average <= %s')
            params.append(float(max_rating))
            
        # 组合WHERE子句
        where_clause = ' AND '.join(where_clauses) if where_clauses else '1=1'
        
        # 构建SQL查询
        count_sql = f'SELECT COUNT(*) as total FROM movies WHERE {where_clause}'
        query_sql = f'SELECT * FROM movies WHERE {where_clause}'
        
        # 获取符合条件的电影总数
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()['total']
        
        # 计算总页数
        import math
        total_pages = math.ceil(total_count / per_page)

        # 确保页码有效
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # 添加排序和分页条件
        query_sql += f' ORDER BY {sort} {order} LIMIT %s OFFSET %s'
        params.extend([per_page, (page - 1) * per_page])
        
        # 执行查询
        cursor.execute(query_sql, params)
        movies = cursor.fetchall()

        # 处理电影海报路径和日期格式
        for movie in movies:
            if movie['poster_path'] and not movie['poster_path'].startswith(('http://', 'https://')):
                movie['poster_path'] = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            
            # 格式化日期，如果存在
            if movie['release_date'] and not isinstance(movie['release_date'], str):
                movie['release_date'] = movie['release_date'].strftime('%Y-%m-%d')
        
        cursor.close()
        conn.close()

        # 渲染模板，传递数据
        return render_template(
            'admin/movies.html', 
            movies=movies, 
            page=page, 
            total_pages=total_pages,
            sort=sort, 
            order=order, 
            per_page=per_page
        )
    except Exception as e:
        flash(f'获取电影列表失败: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/users')
@admin_bp.route('/users/<int:page>')
@admin_required
def users(page=1):
    """管理员用户管理页面
    
    显示系统中所有用户的列表，支持分页和多条件搜索。管理员可以在此页面搜索、
    查看、编辑用户信息，管理用户状态(禁言等)，或删除用户。

    Args:
        page (int, optional): 当前页码，默认为1
    
    Query Parameters:
        username (str): 按用户名搜索
        email (str): 按邮箱地址搜索
        user_type (str): 按用户类型筛选(admin/normal)
        status (str): 按用户状态筛选(active/banned)

    Returns:
        Response: 渲染后的用户管理页面
    """
    # 每页显示的记录数
    per_page = 10
    
    # 从URL查询参数中获取搜索条件
    username = request.args.get('username', '').strip()
    email = request.args.get('email', '').strip()
    user_type = request.args.get('user_type', '').strip()
    status = request.args.get('status', '').strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        # 构建查询条件
        normal_where_clauses = []
        admin_where_clauses = []
        normal_params = []
        admin_params = []
        
        # 按用户名搜索
        if username:
            normal_where_clauses.append('username LIKE %s')
            admin_where_clauses.append('username LIKE %s')
            normal_params.append(f'%{username}%')
            admin_params.append(f'%{username}%')
            
        # 按邮箱搜索
        if email:
            normal_where_clauses.append('email LIKE %s')
            admin_where_clauses.append('email LIKE %s')
            normal_params.append(f'%{email}%')
            admin_params.append(f'%{email}%')
        
        # 按用户类型搜索
        if user_type:
            if user_type == 'normal':
                # 只查询普通用户，不包含管理员
                admin_where_clauses.append('0=1')  # 强制不返回管理员结果
            elif user_type == 'admin':
                # 只查询管理员，不包含普通用户
                normal_where_clauses.append('0=1')  # 强制不返回普通用户结果
        
        # 按状态搜索
        if status:
            if status == 'banned':
                normal_where_clauses.append('status = "banned"')
                admin_where_clauses.append('0=1')  # 管理员不会被禁言
            elif status == 'active':
                normal_where_clauses.append('status != "banned" OR status IS NULL')
                # 管理员都是活跃状态，不需要添加条件

        # 组合WHERE子句
        normal_where_clause = ' AND '.join(normal_where_clauses) if normal_where_clauses else '1=1'
        admin_where_clause = ' AND '.join(admin_where_clauses) if admin_where_clauses else '1=1'

        # 构建SQL查询
        normal_count_sql = f'SELECT COUNT(*) as total FROM userinfo WHERE {normal_where_clause}'
        admin_count_sql = f'SELECT COUNT(*) as total FROM admininfo WHERE {admin_where_clause}'
        normal_query_sql = f'SELECT id, username, email, status, mute_expires_at, 0 AS is_admin, 0 AS reset_password FROM userinfo WHERE {normal_where_clause}'
        admin_query_sql = f'SELECT id, username, email, "active" as status, NULL as mute_expires_at, 1 AS is_admin, 0 AS reset_password FROM admininfo WHERE {admin_where_clause}'

        logger.info(f"搜索用户，条件: 用户名={username}, 邮箱={email}, 类型={user_type}, 状态={status}")

        # 获取符合条件的普通用户总数
        cursor.execute(normal_count_sql, normal_params)
        normal_count = cursor.fetchone()['total']

        # 获取符合条件的管理员总数
        cursor.execute(admin_count_sql, admin_params)
        admin_count = cursor.fetchone()['total']

        # 总用户数
        total_count = normal_count + admin_count
        logger.info(f"搜索到 {total_count} 个用户")

        # 计算总页数
        import math
        total_pages = math.ceil(total_count / per_page)

        # 确保页码有效
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages

        # 计算偏移量和每页查询数量
        offset = (page - 1) * per_page
        
        # 确定是否需要查询普通用户和管理员
        all_users = []
        
        if offset < normal_count:
            # 还在普通用户范围内
            normal_limit = min(per_page, normal_count - offset)
            normal_query_sql += ' LIMIT %s OFFSET %s'
            cursor.execute(normal_query_sql, normal_params + [normal_limit, offset])
            all_users = list(cursor.fetchall())
            
            # 如果还有剩余空间并且有管理员可以显示
            if len(all_users) < per_page and admin_count > 0:
                admin_limit = per_page - len(all_users)
                admin_offset = 0  # 从管理员表的开始查询
                admin_query_sql += ' LIMIT %s OFFSET %s'
                cursor.execute(admin_query_sql, admin_params + [admin_limit, admin_offset])
                all_users.extend(cursor.fetchall())
        else:
            # 超过了普通用户范围，只查询管理员
            admin_offset = offset - normal_count
            admin_query_sql += ' LIMIT %s OFFSET %s'
            cursor.execute(admin_query_sql, admin_params + [per_page, admin_offset])
            all_users = list(cursor.fetchall())

        # 如果 reset_password 字段存在于 userinfo 或 admininfo 表中，则更新数据
        try:
            cursor.execute("SHOW COLUMNS FROM userinfo LIKE 'reset_password'")
            if cursor.fetchone():
                cursor.execute("SELECT id, reset_password FROM userinfo")
                reset_status_normal = {row['id']: row['reset_password'] for row in cursor.fetchall()}
                for user in all_users:
                    if not user['is_admin'] and user['id'] in reset_status_normal:
                        user['reset_password'] = reset_status_normal[user['id']]

            cursor.execute("SHOW COLUMNS FROM admininfo LIKE 'reset_password'")
            if cursor.fetchone():
                cursor.execute("SELECT id, reset_password FROM admininfo")
                reset_status_admin = {row['id']: row['reset_password'] for row in cursor.fetchall()}
                for user in all_users:
                    if user['is_admin'] and user['id'] in reset_status_admin:
                        user['reset_password'] = reset_status_admin[user['id']]
        except:
            # 如果查询失败，忽略错误继续执行
            pass

        cursor.close()
        conn.close()

        return render_template(
            'admin/users.html', 
            users=all_users,
            page=page,
            total_pages=total_pages,
            per_page=per_page
        )

    except Exception as e:
        logger.error(f"获取用户列表失败: {str(e)}")
        flash(f'获取用户列表失败: {str(e)}', 'error')
        return redirect(url_for('admin.dashboard'))

@admin_bp.route('/delete_user/<int:user_id>/<user_type>', methods=['POST'])
@admin_required
def delete_user(user_id, user_type):
    """删除用户"""
    # 禁止删除当前登录的管理员自己
    if user_type == 'admin' and user_id == current_user.id:
        flash('不能删除当前登录的管理员账户')
        return redirect(url_for('admin.users'))

    table_name = 'admininfo' if user_type == 'admin' else 'userinfo'

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f'DELETE FROM {table_name} WHERE id = %s', (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash('用户删除成功')
    except Exception as e:
        flash(f'删除用户失败: {str(e)}')

    return redirect(url_for('admin.users'))

@admin_bp.route('/reset_password/<int:user_id>/<user_type>', methods=['POST'])
@admin_required
def reset_user_password(user_id, user_type):
    """重置用户密码"""
    table_name = 'admininfo' if user_type == 'admin' else 'userinfo'

    try:
        # 从配置中获取默认密码
        from flask import current_app
        default_password = current_app.config['DEFAULT_PASSWORD']
        hashed_password = generate_password_hash(default_password)

        conn = get_db_connection()
        cursor = conn.cursor()

        # 检查 reset_password 列是否存在，如果存在则更新，否则只更新密码
        update_reset_flag = False
        cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'reset_password'")
        if cursor.fetchone():
            update_reset_flag = True

        if update_reset_flag:
            cursor.execute(f'UPDATE {table_name} SET password = %s, reset_password = 1 WHERE id = %s',
                           (hashed_password, user_id))
        else:
            cursor.execute(f'UPDATE {table_name} SET password = %s WHERE id = %s',
                           (hashed_password, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        flash(f'用户密码已重置为 {default_password}' + ('，用户下次登录时将被要求修改密码' if update_reset_flag else ''))
    except Exception as e:
        flash(f'重置密码失败: {str(e)}')

    return redirect(url_for('admin.users'))

@admin_bp.route('/update_movies', methods=['POST'])
@admin_required
def update_movies():
    """触发更新电影数据爬虫，返回JSON响应"""
    try:
        # 检查是否需要强制重置
        force_reset = request.json.get('force_reset', False) if request.is_json else False

        # 检查爬虫模块是否可用
        try:
            # 导入必要的模块
            from movies_recommend.utils import run_scraper_async, reset_scraper_state
        except ImportError:
            return jsonify({"success": False, "message": "爬虫模块未加载，无法更新电影数据"}), 500

        # 如果请求强制重置，先重置爬虫状态
        if force_reset:
            reset_scraper_state()

        # 异步启动爬虫
        if run_scraper_async():
            return jsonify({"success": True, "message": "电影数据更新已启动"})
        else:
            return jsonify({"success": False, "message": "更新任务已在运行中，请等待完成"})

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f'启动更新任务失败: {str(e)}')
        return jsonify({"success": False, "message": f'启动更新任务失败: {str(e)}'}), 500

@admin_bp.route('/reset_scraper', methods=['POST'])
@admin_required
def reset_scraper():
    """重置爬虫状态，解决爬虫卡住的问题"""
    try:
        # 导入重置函数
        try:
            from movies_recommend.utils import reset_scraper_state
        except ImportError:
            return jsonify({"success": False, "message": "爬虫模块未加载，无法重置状态"}), 500

        # 执行重置
        if reset_scraper_state():
            return jsonify({"success": True, "message": "爬虫状态重置成功，可以重新启动更新"})
        else:
            return jsonify({"success": False, "message": "爬虫状态重置失败，请检查日志"})

    except Exception as e:
        from flask import current_app
        current_app.logger.error(f'重置爬虫状态失败: {str(e)}')
        return jsonify({"success": False, "message": f'重置爬虫状态失败: {str(e)}'}), 500

@admin_bp.route('/stop_scraper', methods=['POST'])
@admin_required
def stop_scraper():
    """停止当前正在运行的爬虫任务"""
    try:
        from movies_recommend.tmdb_scraper import stop_scraper_execution
        if stop_scraper_execution():
            current_app.logger.info("爬虫停止信号已发送")
            return jsonify({"success": True, "message": "停止爬虫信号已发送，爬虫将在下一个检查点停止。"})
        else:
            # 理论上 stop_scraper_execution 总是返回 True，除非将来逻辑改变
            current_app.logger.warning("发送停止爬虫信号失败 (stop_scraper_execution 返回 False)")
            return jsonify({"success": False, "message": "发送停止爬虫信号失败。"}), 500
    except ImportError:
        current_app.logger.error("无法导入 stop_scraper_execution 函数")
        return jsonify({"success": False, "message": "无法加载爬虫模块以发送停止信号。"}), 500
    except Exception as e:
        current_app.logger.error(f'停止爬虫任务失败: {str(e)}')
        return jsonify({"success": False, "message": f'停止爬虫任务失败: {str(e)}'}), 500

@admin_bp.route('/scraper_progress')
@admin_required
def scraper_progress():
    """获取爬虫进度的API接口，返回完整的进度信息"""
    try:
        # 使用缓存的爬虫模块实例，避免重复导入
        scraper_module = None
        try:
            # 尝试从utils中获取已加载的模块
            from movies_recommend.utils import load_scraper
            scraper_module = load_scraper()
        except ImportError:
            # 如果失败，直接导入
            from movies_recommend.tmdb_scraper import get_progress
            progress = get_progress()
            # 日志记录返回的进度信息
            logger.info(f"获取爬虫进度: 状态={progress.get('status')}, 进度={progress.get('current')}%, 消息={progress.get('message')}")
            return jsonify(progress)

        # 使用加载的模块获取进度
        if scraper_module:
            progress = scraper_module.get_progress()
            # 日志记录返回的进度信息
            logger.info(f"获取爬虫进度: 状态={progress.get('status')}, 进度={progress.get('current')}%, 已处理={progress.get('processed_movies')}/{progress.get('target_movies')} 部电影")
            return jsonify(progress)
        else:
            raise ImportError("无法加载爬虫模块")
    except Exception as e:
        logger.error(f"获取爬虫进度失败: {e}")
        return jsonify({
            "status": "error",
            "message": f"获取进度失败: {str(e)}",
            "current": 0,
            "total": 100
        })

@admin_bp.route('/mute_user/<int:user_id>', methods=['POST'])
@admin_required
def mute_user(user_id):
    """禁言用户
    
    管理员可以禁止用户发表评论一定时间。
    禁言期间用户不能对电影或其他用户的评论进行评论。
    
    Args:
        user_id (int): 要禁言的用户ID
        
    POST Parameters:
        duration (int): 禁言时长(小时)，如果为0则立即解除禁言
        
    Returns:
        Response: 重定向到用户管理页面
    """
    # 禁止禁言管理员
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 检查用户是否是管理员
        cursor.execute('SELECT id FROM admininfo WHERE id = %s', (user_id,))
        if cursor.fetchone():
            flash('不能禁言管理员账户', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin.users'))
        
        # 获取禁言时长（小时）
        duration = request.form.get('duration', type=int)
        
        if duration is None:
            flash('请提供有效的禁言时长', 'error')
            cursor.close() 
            conn.close()
            return redirect(url_for('admin.users'))
            
        if duration <= 0:
            # 解除禁言
            cursor.execute(
                'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s',
                (user_id,)
            )
            message = '用户禁言已解除'
        else:
            # 设置禁言
            import datetime
            expire_time = datetime.datetime.now() + datetime.timedelta(hours=duration)
            
            cursor.execute(
                'UPDATE userinfo SET status = "banned", mute_expires_at = %s WHERE id = %s',
                (expire_time, user_id)
            )
            message = f'用户已被禁言 {duration} 小时'
        
        conn.commit()
        cursor.close()
        conn.close()
        flash(message, 'success')
    except Exception as e:
        flash(f'禁言用户操作失败: {str(e)}', 'error')
    
    return redirect(url_for('admin.users'))
    
@admin_bp.route('/check_mute_status/<int:user_id>', methods=['GET'])
@admin_required
def check_mute_status(user_id):
    """检查用户禁言状态
    
    获取指定用户的禁言状态和剩余时间
    
    Args:
        user_id (int): 用户ID
        
    Returns:
        JSON: 包含禁言状态的JSON响应
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute(
            'SELECT status, mute_expires_at, username FROM userinfo WHERE id = %s',
            (user_id,)
        )
        user = cursor.fetchone()
        
        if not user:
            cursor.close()
            conn.close()
            return jsonify({
                'error': '用户不存在'
            }), 404
            
        import datetime
        now = datetime.datetime.now()
        is_muted = (user['status'] == 'banned')
        expires_at = user['mute_expires_at']
        
        # 如果禁言已过期，自动解除禁言
        if is_muted and expires_at and expires_at < now:
            cursor.execute(
                'UPDATE userinfo SET status = "active", mute_expires_at = NULL WHERE id = %s',
                (user_id,)
            )
            conn.commit()
            is_muted = False
            expires_at = None
            
        result = {
            'username': user['username'],
            'is_muted': is_muted,
            'mute_expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S') if expires_at else None
        }
        
        # 如果禁言中，计算剩余时间
        if is_muted and expires_at:
            time_left = expires_at - now
            hours = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            result['remaining_time'] = f'{hours}小时{minutes}分钟'
            
        cursor.close()
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'error': f'获取禁言状态失败: {str(e)}'
        }), 500

@admin_bp.route('/delete_movie/<int:movie_id>', methods=['POST'])
@admin_required
def delete_movie(movie_id):
    """删除电影
    
    管理员可以从系统中删除电影。删除电影时，相关的评分、评论等也会被级联删除
    （如果数据库设置了外键约束）。
    
    Args:
        movie_id (int): 要删除的电影ID
        
    Returns:
        Response: 重定向到电影管理页面
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 获取电影标题，用于反馈消息
        cursor.execute('SELECT title FROM movies WHERE id = %s', (movie_id,))
        movie = cursor.fetchone()
        
        if not movie:
            flash('电影不存在', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('admin.movies'))
            
        movie_title = movie['title']
        
        # 执行删除操作
        cursor.execute('DELETE FROM movies WHERE id = %s', (movie_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        flash(f'电影《{movie_title}》已成功删除', 'success')
    except Exception as e:
        flash(f'删除电影失败: {str(e)}', 'error')
        
    # 返回到来源页面或电影列表页
    return redirect(url_for('admin.movies'))

@admin_bp.route('/movie_data_management')
@admin_required
def movie_data_management():
    """电影数据管理页面
    
    提供电影数据管理相关功能的界面，包括抓取新电影、更新电影数据等。

    Returns:
        Response: 渲染后的电影数据管理页面
    """
    return render_template('admin/movie_data_management.html')

@admin_bp.route('/update_movie_popularity', methods=['POST'])
@admin_required
def trigger_update_movie_popularity():
    """手动触发电影热度更新
    
    管理员可以通过此接口手动触发电影热度更新任务，
    系统会立即开始计算并更新所有电影的热度值。

    Returns:
        Response: JSON格式的操作结果
    """
    try:
        logger.info(f"管理员 {current_user.username} 手动触发电影热度更新")
        
        # 执行热度更新任务
        success = update_movie_popularity()
        
        if success:
            logger.info("手动更新电影热度成功完成")
            return jsonify({
                'status': 'success',
                'message': '电影热度更新成功'
            })
        else:
            logger.error("手动更新电影热度失败")
            return jsonify({
                'status': 'error',
                'message': '电影热度更新失败，请查看日志了解详情'
            }), 500
            
    except Exception as e:
        logger.error(f"手动更新电影热度时发生错误: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'更新过程中发生错误: {str(e)}'
        }), 500

@admin_bp.route('/custom_fetch', methods=['POST'])
@admin_required
def custom_fetch():
    """自定义抓取电影数据
    
    根据管理员提供的参数，自定义抓取电影数据。
    可以指定抓取的页数、类型和数量。

    Returns:
        Response: JSON格式的操作结果
    """
    try:
        # 获取请求数据
        data = request.json if request.is_json else {}
        
        # 记录请求信息
        logger.info(f"收到自定义抓取请求: {data}")
        
        # 检查爬虫模块是否可用
        try:
            # 导入必要的模块
            from movies_recommend.utils import run_custom_scraper
        except ImportError:
            return jsonify({"success": False, "message": "爬虫模块未加载，无法执行自定义抓取"}), 500
            
        # 提取参数
        params = {
            'keyword': data.get('keyword', ''),
            'director': data.get('director', ''),
            'actor': data.get('actor', ''),
            'language': data.get('language', ''),
            'region': data.get('region', ''),
            'min_rating': data.get('min_rating', ''),
            'genre': data.get('genre', ''),
            'year': data.get('year', ''),
            'page_count': data.get('page_count', 1)
        }
        
        # 确保page_count是整数
        try:
            params['page_count'] = int(params['page_count'])
            if params['page_count'] < 1:
                params['page_count'] = 1
            elif params['page_count'] > 5:  # 限制最大页数
                params['page_count'] = 5
        except (ValueError, TypeError):
            params['page_count'] = 1
            
        # 启动自定义抓取
        success = run_custom_scraper(params)
        
        if success:
            return jsonify({"success": True, "message": "自定义抓取任务已启动，请在批量更新标签页查看进度"})
        else:
            return jsonify({"success": False, "message": "已有爬虫任务正在进行，请等待完成后再试"})
            
    except Exception as e:
        logger.error(f"启动自定义抓取任务失败: {str(e)}")
        return jsonify({"success": False, "message": f"启动自定义抓取任务失败: {str(e)}"}), 500

@admin_bp.route('/api/movie_genres_distribution')
@admin_required
def movie_genres_distribution():
    """获取电影类型分布数据

    返回系统中各类型电影的数量统计，用于环形图展示。
    会对电影类型进行去重处理，确保每部电影只计算一次。

    Returns:
        Response: JSON格式的电影类型分布数据
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 首先检查genres字段的格式，取样几条数据
        cursor.execute("SELECT id, genres FROM movies LIMIT 5")
        sample_data = cursor.fetchall()
        logger.info(f"电影类型样本数据: {sample_data}")
        
        # 查询电影类型分布
        # genres字段存储的是JSON格式的类型数组，需要提取并统计
        sql_query = """
            SELECT 
                TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(t.genres, ',', n.n), ',', -1)) AS genre,
                COUNT(DISTINCT t.id) AS count
            FROM 
                (SELECT id, genres FROM movies) t
            JOIN 
                (SELECT 1 AS n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 
                 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9 UNION SELECT 10) n
            ON 
                LENGTH(t.genres) - LENGTH(REPLACE(t.genres, ',', '')) >= n.n - 1
            WHERE 
                TRIM(SUBSTRING_INDEX(SUBSTRING_INDEX(t.genres, ',', n.n), ',', -1)) != ''
            GROUP BY 
                genre
            ORDER BY 
                count DESC
            LIMIT 10
        """
        logger.info(f"执行电影类型分布SQL: {sql_query}")
        cursor.execute(sql_query)
        genres_data = cursor.fetchall()
        
        logger.info(f"获取到的电影类型数据: {genres_data}")
        
        # 如果没有获取到数据，尝试不同的查询方式
        if not genres_data:
            logger.warning("未能使用分割字符串方式获取类型数据，尝试备用查询")
            # 备用查询：直接按原始genres字段分组
            cursor.execute("""
                SELECT 
                    IFNULL(genres, '未分类') AS genre,
                    COUNT(*) AS count
                FROM 
                    movies
                GROUP BY 
                    genres
                ORDER BY 
                    count DESC
                LIMIT 10
            """)
            genres_data = cursor.fetchall()
            logger.info(f"备用查询获取到的电影类型数据: {genres_data}")
        
        # 转换为前端图表所需的数据格式
        labels = [item['genre'] for item in genres_data]
        data = [item['count'] for item in genres_data]
        
        result = {
            'labels': labels,
            'data': data
        }
        logger.info(f"返回的电影类型分布数据: {result}")
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"获取电影类型分布数据失败: {e}")
        return jsonify({
            'error': f"获取数据失败: {e}"
        }), 500
    
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/api/movie_ratings_distribution')
@admin_required
def movie_ratings_distribution():
    """获取电影评分分布数据

    返回系统中电影评分的分布情况，按评分区间统计，用于饼图展示。
    使用user_ratings表中的用户真实评分，而非movies表中的平均评分。

    Returns:
        Response: JSON格式的电影评分分布数据
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 查询用户评分分布，按评分区间统计
        cursor.execute("""
            SELECT
                CASE
                    WHEN rating BETWEEN 0 AND 2 THEN '0-2分'
                    WHEN rating BETWEEN 2 AND 4 THEN '2-4分'
                    WHEN rating BETWEEN 4 AND 6 THEN '4-6分'
                    WHEN rating BETWEEN 6 AND 8 THEN '6-8分'
                    WHEN rating BETWEEN 8 AND 10 THEN '8-10分'
                    ELSE '未评分'
                END AS rating_range,
                COUNT(*) AS count
            FROM
                user_ratings
            GROUP BY
                rating_range
            ORDER BY
                CASE rating_range
                    WHEN '0-2分' THEN 1
                    WHEN '2-4分' THEN 2
                    WHEN '4-6分' THEN 3
                    WHEN '6-8分' THEN 4
                    WHEN '8-10分' THEN 5
                    ELSE 6
                END
        """)
        ratings_data = cursor.fetchall()
        
        # 确保所有评分区间都存在，即使没有数据
        expected_ranges = ['0-2分', '2-4分', '4-6分', '6-8分', '8-10分']
        existing_ranges = [item['rating_range'] for item in ratings_data]
        
        # 补充缺失的评分区间
        for range_name in expected_ranges:
            if range_name not in existing_ranges:
                ratings_data.append({'rating_range': range_name, 'count': 0})
        
        # 按评分区间排序
        ratings_data = sorted(ratings_data, key=lambda x: expected_ranges.index(x['rating_range']) if x['rating_range'] in expected_ranges else len(expected_ranges))
        
        # 转换为前端图表所需的数据格式
        labels = [item['rating_range'] for item in ratings_data]
        data = [item['count'] for item in ratings_data]
        
        result = {
            'labels': labels,
            'data': data
        }
        logger.info(f"返回的电影评分分布数据: {result}")
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"获取电影评分分布数据失败: {e}")
        return jsonify({
            'error': f"获取数据失败: {e}"
        }), 500
    
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/api/popular_movies')
@admin_required
def popular_movies():
    """获取热门电影排行数据

    返回系统中最受欢迎的电影列表，基于评分和评论数量，用于横向柱状图展示。

    Returns:
        Response: JSON格式的热门电影排行数据
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 查询热门电影排行，基于评分和评论数量
        cursor.execute("""
            SELECT
                m.title,
                m.vote_average,
                COUNT(ur.id) AS rating_count
            FROM
                movies m
            LEFT JOIN
                user_ratings ur ON m.id = ur.movie_id
            GROUP BY
                m.id
            ORDER BY
                (m.vote_average * 0.6) + (COUNT(ur.id) * 0.4) DESC
            LIMIT 10
        """)
        movies_data = cursor.fetchall()
        
        # 转换为前端图表所需的数据格式
        labels = [item['title'] for item in movies_data]
        ratings = [float(item['vote_average']) for item in movies_data]
        counts = [int(item['rating_count']) for item in movies_data]
        
        return jsonify({
            'labels': labels,
            'ratings': ratings,
            'counts': counts
        })
    
    except Exception as e:
        logger.error(f"获取热门电影排行数据失败: {e}")
        return jsonify({
            'error': f"获取数据失败: {e}"
        }), 500
    
    finally:
        cursor.close()
        conn.close()

@admin_bp.route('/api/user_growth')
@admin_required
def user_growth():
    """获取用户增长趋势数据

    返回系统中用户注册的时间分布，按月份统计，用于折线图展示。

    Returns:
        Response: JSON格式的用户增长趋势数据
    """
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 查询用户增长趋势，按月份统计
        cursor.execute("""
            SELECT
                DATE_FORMAT(created_at, '%Y-%m') AS month,
                COUNT(*) AS count
            FROM
                userinfo
            WHERE
                created_at >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
            GROUP BY
                month
            ORDER BY
                month
        """)
        user_data = cursor.fetchall()
        
        # 转换为前端图表所需的数据格式
        labels = [item['month'] for item in user_data]
        data = [item['count'] for item in user_data]
        
        return jsonify({
            'labels': labels,
            'data': data
        })
    
    except Exception as e:
        logger.error(f"获取用户增长趋势数据失败: {e}")
        return jsonify({
            'error': f"获取数据失败: {e}"
        }), 500
    
    finally:
        cursor.close()
        conn.close()


