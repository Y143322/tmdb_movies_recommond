"""
认证蓝图，处理用户登录、注册、登出等功能
"""
import os
import re
import secrets
from typing import Any
from urllib.parse import urljoin, urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from rate_limiter import RateLimiter
from movies_recommend.models import User
from movies_recommend.extensions import get_db_connection
from movies_recommend.request_utils import is_api_request as is_json_request
from movies_recommend.auth_service import (
    create_user_record,
    username_exists,
    verify_user_credentials,
    validate_email,
    validate_username,
)
import pymysql
from functools import wraps

# 创建蓝图
auth_bp = Blueprint('auth', __name__)
auth_write_limiter = RateLimiter(requests_per_minute=1200, safety_factor=1.0)


def _mask_sensitive_fields(form_data):
    """对日志中的敏感字段做脱敏处理。"""
    masked_data = {}
    for key, value in form_data.items():
        key_lower = str(key).lower()
        if any(token in key_lower for token in ('password', 'token', 'secret')):
            masked_data[key] = '******'
        else:
            masked_data[key] = value
    return masked_data


def _is_safe_redirect_url(target):
    """校验重定向URL是否同源，避免开放重定向。"""
    if not target:
        return False
    host_url = request.host_url
    ref_url = urlparse(host_url)
    test_url = urlparse(urljoin(host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def _is_test_login_api_enabled():
    """仅在开发环境并显式开启时启用测试登录接口。"""
    return current_app.config.get('DEBUG', False) and os.environ.get('ENABLE_TEST_LOGIN_API', '').lower() in ('1', 'true', 'yes')


def _password_min_length():
    """统一密码最小长度配置。"""
    return int(current_app.config.get('PASSWORD_MIN_LENGTH', 8))


def _is_valid_csrf_form():
    """校验表单 CSRF Token。"""
    token = request.form.get('csrf_token')
    session_token = session.get('_csrf_token')
    if not token or not session_token:
        return False
    try:
        return secrets.compare_digest(str(token), str(session_token))
    except Exception:
        return False

# 添加装饰器，用于检测API响应
def api_response_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 为以下情况设置 API 响应标志
        # 1. 明确的API请求路径
        # 2. Postman或API测试工具发出的请求
        # 3. 请求头中明确要求JSON响应
        # 4. 测试模式
        is_api = is_json_request(request)
        
        # 记录是否来自 Postman（仅用于调试标识，不影响安全判断）
        user_agent = request.headers.get('User-Agent') or ''
        is_postman = ('Postman' in user_agent) or ('PostmanRuntime' in user_agent)

        setattr(request, 'is_api_request', is_api)
        setattr(request, 'is_postman_test', is_postman)
            
        return f(*args, **kwargs)
    return decorated_function

# 应用装饰器到所有路由
@auth_bp.before_request
@api_response_required
def before_request():
    """通过装饰器统一标记请求类型。"""
    return None

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    # 如果用户已经登录，直接重定向到首页
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        auth_write_limiter.acquire()

        if not _is_valid_csrf_form():
            flash('请求校验失败，请刷新页面后重试', 'error')
            return render_template('register.html')

        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        email = request.form.get('email', '')
        user_type = request.form.get('user_type', 'normal')
        admin_code = request.form.get('admin_code', '')
        captcha = str(request.form.get('captcha') or '').lower()

        # 验证码验证
        if not captcha or captcha != session.get('captcha', ''):
            flash('验证码错误', 'error')
            return render_template('register.html')

        # 输入验证
        if not username or not password:
            flash('用户名和密码不能为空', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('两次输入的密码不一致', 'error')
            return render_template('register.html')

        # 用户名和密码格式验证
        if len(username) < 3 or len(username) > 20:
            flash('用户名长度需在3-20个字符之间', 'error')
            return render_template('register.html')

        if not validate_username(username):
            flash('用户名只能包含字母、数字和下划线', 'error')
            return render_template('register.html')

        min_length = _password_min_length()
        if len(password) < min_length:
            flash(f'密码长度至少需要{min_length}个字符', 'error')
            return render_template('register.html')

        # 检查邮箱格式
        if email and not validate_email(email):
            flash('邮箱格式不正确', 'error')
            return render_template('register.html')

        # 管理员验证码验证
        if user_type == 'admin':
            # 从配置中获取管理员验证码
            from flask import current_app
            ADMIN_VERIFICATION_CODE = current_app.config['ADMIN_VERIFICATION_CODE']

            if not admin_code:
                flash('请输入管理员验证码', 'error')
                return render_template('register.html')

            if admin_code != ADMIN_VERIFICATION_CODE:
                flash('管理员验证码错误', 'error')
                return render_template('register.html')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            # 检查用户名是否已存在
            if username_exists(cursor, username):
                flash('用户名已存在', 'error')
                return render_template('register.html')

            next_id, is_admin = create_user_record(
                cursor=cursor,
                username=username,
                password=password,
                email=email,
                user_type=user_type,
                logger=current_app.logger,
            )
            conn.commit()

            # 获取新用户ID并登录
            user_obj = User(
                id=next_id,
                username=username,
                email=email,
                is_admin=is_admin
            )
            login_user(user_obj)

            if is_admin:
                flash('管理员注册成功并已登录', 'success')
            else:
                flash('注册成功并已登录', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            conn.rollback()
            flash('注册失败，请稍后重试', 'error')
        finally:
            cursor.close()
            conn.close()

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录
    
    处理两种类型的请求:
    1. 浏览器请求: 返回HTML页面或重定向
    2. API请求: 返回JSON响应
    """
    # 从装饰器中获取API请求标志
    is_api_request = getattr(request, 'is_api_request', False)
    is_postman_test = getattr(request, 'is_postman_test', False)
    
    # 记录请求类型，帮助调试
    from flask import current_app
    current_app.logger.info(f"登录请求类型: API={is_api_request}, Postman={is_postman_test}")
    
    # 如果用户已登录且是浏览器请求，直接重定向到首页
    if current_user.is_authenticated and not is_api_request:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        auth_write_limiter.acquire()

        # 记录详细的请求信息，帮助调试
        safe_headers = {
            'User-Agent': request.headers.get('User-Agent'),
            'Content-Type': request.headers.get('Content-Type'),
            'Accept': request.headers.get('Accept'),
            'X-Requested-With': request.headers.get('X-Requested-With')
        }
        current_app.logger.info(f"登录POST请求: 头部(安全)={safe_headers}")
        
        # 从多种可能的来源获取凭据
        if request.is_json:
            data = request.get_json(silent=True) or {}
            if not isinstance(data, dict):
                data = {}
            username = data.get('username')
            password = data.get('password')
            captcha = str(data.get('captcha') or '').lower()
        else:
            username = request.form.get('username')
            password = request.form.get('password')
            captcha = str(request.form.get('captcha') or '').lower()
            
        current_app.logger.info(f"登录凭据: username={username}, captcha提供={(captcha is not None)}")

        if not is_api_request and not _is_valid_csrf_form():
            flash('请求校验失败，请刷新页面后重试', 'error')
            return render_template('login.html')

        # 验证码验证（浏览器登录必须校验）
        if not is_api_request and (not captcha or captcha != session.get('captcha', '')):
            flash('验证码错误', 'error')
            return render_template('login.html')

        if not username or not password:
            if is_api_request:
                # API请求参数错误返回400状态码
                return jsonify({
                    'success': False, 
                    'message': '用户名和密码不能为空',
                    'error': 'missing_credentials'
                }), 400
            flash('用户名和密码不能为空', 'error')
            return render_template('login.html')

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        try:
            user_data, is_admin, error_code = verify_user_credentials(cursor, username, password)

            if error_code is None and user_data:
                user = User(
                    id=user_data['id'],
                    username=user_data['username'],
                    email=user_data.get('email'),
                    is_admin=is_admin
                )

                # 检查重置密码字段是否存在，并设置到用户对象
                try:
                    reset_table = 'admininfo' if is_admin else 'userinfo'
                    cursor.execute(f'SHOW COLUMNS FROM {reset_table} LIKE "reset_password"')
                    if cursor.fetchone():
                        cursor.execute(f'SELECT reset_password FROM {reset_table} WHERE id = %s', (user.id,))
                        reset_data = cursor.fetchone()
                        if reset_data and reset_data.get('reset_password'):
                            user.reset_password = True
                except Exception as e:
                    current_app.logger.warning(f"检查重置密码状态时出错: {e}")
                    
                # 登录用户
                login_user(user, remember=True)
                session.permanent = True
                
                # 记录登录成功
                from flask import current_app
                current_app.logger.info(f"用户 {username} 登录成功，是否API请求: {is_api_request}")
                
                # 如果是API请求，返回JSON响应
                if is_api_request:
                    # 构建API响应
                    response_data = {
                        'success': True, 
                        'message': '登录成功',
                        'user_id': user.id,
                        'username': user.username,
                        'is_admin': user.is_admin
                    }
                    
                    # 创建JSON响应
                    response = jsonify(response_data)
                    response.status_code = 200
                    
                    return response
                
                # 如果用户需要重置密码，重定向到修改密码页面
                if getattr(user, 'reset_password', False):
                    flash('您的密码已被重置，请立即修改密码')
                    return redirect(url_for('auth.change_password'))

                flash('登录成功！', 'success')
                next_page = request.args.get('next')
                if next_page and _is_safe_redirect_url(next_page):
                    return redirect(next_page)
                return redirect(url_for('main.index'))
            else:
                # 登录失败 - 密码错误或用户不存在
                from flask import current_app
                if error_code == 'deleted':
                    if is_api_request:
                        return jsonify({'success': False, 'message': '该账号已被删除', 'error': 'account_deleted'}), 403
                    flash('该账号已被删除', 'error')
                    return render_template('login.html')

                if error_code == 'banned':
                    if is_api_request:
                        return jsonify({'success': False, 'message': '该账号已被禁言', 'error': 'account_banned'}), 403
                    flash('该账号已被禁言', 'error')
                    return render_template('login.html')

                current_app.logger.info(f"用户 {username} 登录失败：密码错误或用户不存在")
                
                if is_api_request:
                    response = jsonify({
                        'success': False, 
                        'message': '用户名或密码错误',
                        'error': 'invalid_credentials'
                    })
                    response.status_code = 401
                    return response
                
                # 浏览器请求 - 显示错误消息
                flash('用户名或密码错误！', 'error')
        except Exception as e:
            # 处理异常情况
            from flask import current_app
            current_app.logger.error(f"登录过程中发生错误: {str(e)}")
            
            if is_api_request:
                response = jsonify({
                    'success': False, 
                    'message': '服务器内部错误',
                    'error': 'server_error'
                })
                response.status_code = 500
                return response
            
            # 浏览器请求 - 显示错误消息
            flash('登录时发生错误，请稍后重试', 'error')
        finally:
            # 确保关闭数据库连接
            cursor.close()
            conn.close()

    # 处理GET请求或其他方法
    if is_api_request:
        # API请求只支持POST方法
        return jsonify({
            'success': False, 
            'message': '登录API只支持POST请求'
        }), 405
    
    # 浏览器请求 - 显示登录页面
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """用户登出"""
    logout_user()
    flash('您已成功退出登录！', 'success')
    return redirect(url_for('main.index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """用户个人资料页面"""
    if request.method == 'POST':
        if not _is_valid_csrf_form():
            flash('请求校验失败，请刷新页面后重试', 'error')
            return redirect(url_for('auth.profile'))

        # 处理表单提交
        if 'email' in request.form and request.form['email']:
            # 更新邮箱
            email = request.form['email']

            # 验证邮箱格式
            if not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
                flash('邮箱格式不正确', 'error')
                return render_template('profile.html', user=current_user)

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # 根据用户类型确定操作的表名
                table_name = 'admininfo' if current_user.is_admin else 'userinfo'

                cursor.execute(
                    f'UPDATE {table_name} SET email = %s WHERE id = %s',
                    (email, current_user.id)
                )
                conn.commit()

                # 更新current_user对象的email
                current_user.email = email

                flash('邮箱更新成功', 'success')
            except Exception as e:
                conn.rollback()
                flash('邮箱更新失败，请稍后重试', 'error')
            finally:
                cursor.close()
                conn.close()

        elif 'old_password' in request.form and 'new_password' in request.form:
            # 更新密码
            old_password = request.form['old_password']
            new_password = request.form['new_password']

            if not old_password or not new_password:
                flash('请输入旧密码和新密码', 'error')
                return render_template('profile.html', user=current_user)

            # 验证新密码长度
            min_length = _password_min_length()
            if len(new_password) < min_length:
                flash(f'新密码长度至少需要{min_length}个字符', 'error')
                return render_template('profile.html', user=current_user)

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # 根据用户类型确定操作的表名
                table_name = 'admininfo' if current_user.is_admin else 'userinfo'

                # 验证旧密码
                cursor.execute(f'SELECT password FROM {table_name} WHERE id = %s', (current_user.id,))
                password_row = cursor.fetchone()
                stored_password = password_row[0] if password_row else None

                if not isinstance(stored_password, str):
                    flash('账户状态异常，请重新登录后重试', 'error')
                    return render_template('profile.html', user=current_user)

                password_correct = check_password_hash(stored_password, old_password)

                if not password_correct:
                    flash('旧密码不正确', 'error')
                    cursor.close()
                    conn.close()
                    return render_template('profile.html', user=current_user)

                # 更新密码
                hashed_password = generate_password_hash(new_password)
                cursor.execute(
                    f'UPDATE {table_name} SET password = %s WHERE id = %s',
                    (hashed_password, current_user.id)
                )
                conn.commit()

                flash('密码更新成功', 'success')
            except Exception as e:
                conn.rollback()
                flash('密码更新失败，请稍后重试', 'error')
            finally:
                cursor.close()
                conn.close()

    # 获取用户类型偏好数据
    user_genres = None
    
    # 管理员账户不显示类型偏好
    if not current_user.is_admin:
        try:
            # 导入用户偏好模块
            from movies_recommend.user_preferences import get_user_top_genres
            
            # 获取用户的类型偏好
            top_genres = get_user_top_genres(current_user.id, n=10)
            
            if top_genres:
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
        except Exception as e:
            # 处理异常，将错误记录到日志
            from flask import current_app
            current_app.logger.error(f"获取用户类型偏好失败: {e}")
            # 不显示错误消息，保持页面其他部分正常显示
    
    return render_template('profile.html', user=current_user, user_genres=user_genres)

@auth_bp.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码页面"""
    if request.method == 'POST':
        auth_write_limiter.acquire()

        if not _is_valid_csrf_form():
            flash('请求校验失败，请刷新页面后重试', 'error')
            return render_template('change_password.html')

        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not all([current_password, new_password, confirm_password]):
            flash('所有字段都必须填写')
            return render_template('change_password.html')

        if new_password != confirm_password:
            flash('新密码和确认密码不匹配')
            return render_template('change_password.html')

        min_length = _password_min_length()
        if len(new_password) < min_length:
            flash(f'新密码长度至少需要{min_length}个字符')
            return render_template('change_password.html')

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        table_name = 'admininfo' if current_user.is_admin else 'userinfo'

        try:
            # 检查当前密码是否正确
            cursor.execute(f'SELECT password FROM {table_name} WHERE id = %s', (current_user.id,))
            user = cursor.fetchone()
            user_password: Any = user.get('password') if isinstance(user, dict) else None

            if not isinstance(user_password, str) or not check_password_hash(user_password, current_password):
                flash('当前密码不正确')
                cursor.close()
                conn.close()
                return render_template('change_password.html')

            # 更新密码
            hashed_password = generate_password_hash(new_password)

            # 检查 reset_password 列是否存在，如果存在则更新，否则只更新密码
            update_reset_flag = False
            cursor.execute(f"SHOW COLUMNS FROM {table_name} LIKE 'reset_password'")
            if cursor.fetchone():
                update_reset_flag = True

            if update_reset_flag:
                cursor.execute(f'UPDATE {table_name} SET password = %s, reset_password = 0 WHERE id = %s',
                             (hashed_password, current_user.id))
            else:
                cursor.execute(f'UPDATE {table_name} SET password = %s WHERE id = %s',
                             (hashed_password, current_user.id))

            conn.commit()
            flash('密码已成功更新')
            return redirect(url_for('main.index'))
        except Exception as e:
            conn.rollback()
            flash('更新密码时出错，请稍后重试', 'error')
            return render_template('change_password.html')
        finally:
            cursor.close()
            conn.close()

    return render_template('change_password.html')

@auth_bp.route('/captcha')
def get_captcha():
    """生成验证码图片"""
    import random
    from PIL import Image, ImageDraw, ImageFont
    import io
    import base64

    # 生成随机验证码
    captcha_text = ''.join(random.choices('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
    # 将验证码存储在session中
    session['captcha'] = captcha_text.lower()

    # 使用PIL创建验证码图片
    width, height = 120, 40
    image = Image.new('RGB', (width, height), color=255)
    draw = ImageDraw.Draw(image)

    # 尝试加载字体，如果失败则使用默认字体
    try:
        font = ImageFont.truetype("arial.ttf", 24)
    except IOError:
        font = ImageFont.load_default()

    # 绘制文本
    text_width, text_height = draw.textbbox((0, 0), captcha_text, font=font)[2:4]
    x = (width - text_width) / 2
    y = (height - text_height) / 2
    draw.text((x, y), captcha_text, font=font, fill=(0, 0, 0))

    # 添加干扰线
    for i in range(5):
        start_point = (random.randint(0, width), random.randint(0, height))
        end_point = (random.randint(0, width), random.randint(0, height))
        draw.line([start_point, end_point], fill=(0, 0, 0))

    # 添加干扰点
    for i in range(30):
        point = (random.randint(0, width), random.randint(0, height))
        draw.point(point, fill=(0, 0, 0))

    # 将图片转换为base64
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return jsonify({'image': image_base64})

@auth_bp.route('/api/test-login', methods=['POST'])
def test_login_api():
    """用于测试的API登录端点"""
    if not _is_test_login_api_enabled():
        return jsonify({'success': False, 'message': 'Not Found'}), 404

    if request.method == 'POST':
        # 从多种可能的来源获取凭据
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            # 先检查是否是管理员
            cursor.execute('SELECT * FROM admininfo WHERE username = %s', (username,))
            user_data = cursor.fetchone()
            is_admin = True
            
            # 如果不是管理员，检查普通用户
            if not user_data:
                cursor.execute('SELECT * FROM userinfo WHERE username = %s', (username,))
                user_data = cursor.fetchone()
                is_admin = False
                
            if user_data and check_password_hash(user_data['password'], password):
                user = User(
                    id=user_data['id'],
                    username=user_data['username'],
                    email=user_data.get('email'),
                    is_admin=is_admin
                )
                
                login_user(user, remember=True)
                session.permanent = True
                
                # 构建成功响应
                response = jsonify({
                    'success': True, 
                    'message': '登录成功',
                    'user_id': user.id,
                    'username': user.username,
                    'is_admin': user.is_admin
                })
                # 设置状态码
                response.status_code = 200
                
                return response
            else:
                response = jsonify({
                    'success': False, 
                    'message': '用户名或密码错误',
                    'error': 'invalid_credentials'
                })
                response.status_code = 401
                return response
        except Exception as e:
            response = jsonify({
                'success': False, 
                'message': '服务器内部错误',
                'error': 'server_error'
            })
            response.status_code = 500
            return response
        finally:
            cursor.close()
            conn.close()
            
    return jsonify({'success': False, 'message': '只支持POST请求'}), 405

def init_test_user():
    """测试用户初始化函数存根
    
    注意：此函数已不再执行初始化，因为数据库中已存在测试用户。
    保留此函数是为了避免导入错误。
    """
    from flask import current_app
    current_app.logger.info("跳过测试用户初始化：数据库中已存在测试用户")
