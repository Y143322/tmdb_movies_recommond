"""
认证API模块 - 提供RESTful风格的认证接口
"""
import re
from typing import Any
from flask import request, jsonify, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
from rate_limiter import RateLimiter
from movies_recommend.models import User
from movies_recommend.extensions import get_db_connection
from movies_recommend.blueprints.api import api_bp
from movies_recommend.logger import get_logger
from movies_recommend.auth_service import (
    create_user_record,
    username_exists,
    verify_user_credentials,
    validate_email,
    validate_username,
)

logger = get_logger('api_auth')
auth_write_limiter = RateLimiter(requests_per_minute=1200, safety_factor=1.0)


def _password_min_length():
    """统一密码最小长度配置。"""
    return int(current_app.config.get('PASSWORD_MIN_LENGTH', 8))


def _server_error_response():
    """统一500错误响应，避免泄露内部异常细节。"""
    return api_response(False, '服务器内部错误', code=500)


def api_response(success=True, message='', data=None, code=200):
    """统一API响应格式
    
    Args:
        success: 是否成功
        message: 响应消息
        data: 响应数据
        code: HTTP状态码
        
    Returns:
        tuple: (响应体, 状态码)
    """
    response = {
        'code': code,
        'success': success,
        'message': message
    }
    if data is not None:
        response['data'] = data
    return jsonify(response), code


@api_bp.route('/auth/login', methods=['POST'])
def login():
    """用户登录API
    
    POST /api/auth/login
    Body: {
        "username": "用户名",
        "password": "密码"
    }
    
    Returns:
        {
            "code": 200,
            "success": true,
            "message": "登录成功",
            "data": {
                "token": "session_token",
                "user": {
                    "id": 1,
                    "username": "test",
                    "email": "test@example.com",
                    "isAdmin": false
                }
            }
        }
    """
    try:
        auth_write_limiter.acquire()

        # 获取请求数据
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_response(False, '请求数据格式错误', code=400)
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        # 验证必填字段
        if not username or not password:
            return api_response(False, '用户名和密码不能为空', code=400)
        
        # 数据库查询
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            user_data, is_admin, error_code = verify_user_credentials(cursor, username, password)

            if error_code == 'invalid_credentials':
                logger.warning(f"登录失败: 用户名 {username} 不存在")
                return api_response(False, '用户名或密码错误', code=401)

            if error_code == 'deleted':
                return api_response(False, '该账号已被删除', code=403)
            if error_code == 'banned':
                return api_response(False, '该账号已被禁言', code=403)
            
            # 创建用户对象
            user = User(
                id=user_data['id'],
                username=user_data['username'],
                email=user_data.get('email', ''),
                is_admin=is_admin
            )
            
            # 登录用户（设置session）
            login_user(user, remember=True)
            session.permanent = True
            
            logger.info(f"用户 {username} 登录成功 (is_admin={is_admin})")
            
            # 返回成功响应
            return api_response(
                success=True,
                message='登录成功',
                data={
                    'token': 'session',  # 使用session认证
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email or '',
                        'isAdmin': user.is_admin
                    }
                }
            )
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"登录API异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/register', methods=['POST'])
def register():
    """用户注册API
    
    POST /api/auth/register
    Body: {
        "username": "用户名",
        "password": "密码",
        "confirmPassword": "确认密码",
        "email": "邮箱(可选)",
        "userType": "normal/admin",
        "adminCode": "管理员验证码(注册管理员时需要)"
    }
    """
    try:
        auth_write_limiter.acquire()

        # 获取请求数据
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_response(False, '请求数据格式错误', code=400)
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        confirm_password = data.get('confirmPassword', '')
        email = data.get('email', '').strip()
        user_type = data.get('userType', 'normal')
        admin_code = data.get('adminCode', '')
        
        # 验证必填字段
        if not username or not password:
            return api_response(False, '用户名和密码不能为空', code=400)
        
        if password != confirm_password:
            return api_response(False, '两次输入的密码不一致', code=400)
        
        # 用户名格式验证
        if len(username) < 3 or len(username) > 20:
            return api_response(False, '用户名长度需在3-20个字符之间', code=400)
        
        if not validate_username(username):
            return api_response(False, '用户名只能包含字母、数字和下划线', code=400)
        
        # 密码强度验证
        min_length = _password_min_length()
        if len(password) < min_length:
            return api_response(False, f'密码长度至少需要{min_length}个字符', code=400)
        
        # 邮箱格式验证
        if email and not validate_email(email):
            return api_response(False, '邮箱格式不正确', code=400)
        
        # 管理员验证码验证
        if user_type == 'admin':
            ADMIN_VERIFICATION_CODE = current_app.config.get('ADMIN_VERIFICATION_CODE', 'admin123')
            
            if not admin_code:
                return api_response(False, '请输入管理员验证码', code=400)
            
            if admin_code != ADMIN_VERIFICATION_CODE:
                return api_response(False, '管理员验证码错误', code=403)
        
        # 数据库操作
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # 检查用户名是否已存在
            if username_exists(cursor, username):
                return api_response(False, '用户名已存在', code=409)

            next_id, is_admin = create_user_record(
                cursor=cursor,
                username=username,
                password=password,
                email=email,
                user_type=user_type,
                logger=logger,
            )
            
            conn.commit()
            
            # 创建用户对象并登录
            user = User(
                id=next_id,
                username=username,
                email=email,
                is_admin=is_admin
            )
            login_user(user, remember=True)
            session.permanent = True
            
            logger.info(f"新用户注册成功: {username} (is_admin={is_admin})")
            
            return api_response(
                success=True,
                message='注册成功',
                data={
                    'token': 'session',
                    'user': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email or '',
                        'isAdmin': user.is_admin
                    }
                }
            )
            
        except Exception as e:
            conn.rollback()
            logger.error(f"注册失败: {str(e)}")
            return _server_error_response()
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"注册API异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/logout', methods=['POST'])
@login_required
def logout():
    """用户登出API
    
    POST /api/auth/logout
    """
    try:
        username = current_user.username
        logout_user()
        # 不使用 session.clear()，避免清掉 Flask-Login 的 remember-cookie 清理标记
        session.pop('captcha', None)
        session.pop('_csrf_token', None)
        
        logger.info(f"用户 {username} 登出")
        return api_response(success=True, message='登出成功')
        
    except Exception as e:
        logger.error(f"登出API异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/profile', methods=['GET'])
@login_required
def get_profile():
    """获取当前用户信息
    
    GET /api/auth/profile
    """
    try:
        return api_response(
            success=True,
            message='获取成功',
            data={
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email or '',
                'isAdmin': current_user.is_admin
            }
        )
    except Exception as e:
        logger.error(f"获取用户信息异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/profile', methods=['PUT'])
@login_required
def update_profile():
    """更新用户信息
    
    PUT /api/auth/profile
    Body: {
        "email": "新邮箱"
    }
    """
    try:
        auth_write_limiter.acquire()

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_response(False, '请求数据格式错误', code=400)
        
        email = data.get('email', '').strip()
        
        # 邮箱格式验证
        if email and not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email):
            return api_response(False, '邮箱格式不正确', code=400)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            table_name = 'admininfo' if current_user.is_admin else 'userinfo'
            cursor.execute(
                f'UPDATE {table_name} SET email = %s WHERE id = %s',
                (email, current_user.id)
            )
            conn.commit()
            
            # 更新当前用户对象
            current_user.email = email
            
            logger.info(f"用户 {current_user.username} 更新了个人信息")
            return api_response(success=True, message='更新成功')
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"更新用户信息异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """修改密码
    
    POST /api/auth/change-password
    Body: {
        "currentPassword": "当前密码",
        "newPassword": "新密码",
        "confirmPassword": "确认新密码"
    }
    """
    try:
        auth_write_limiter.acquire()

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return api_response(False, '请求数据格式错误', code=400)
        
        current_password = data.get('currentPassword', '')
        new_password = data.get('newPassword', '')
        confirm_password = data.get('confirmPassword', '')
        
        # 验证必填字段
        if not all([current_password, new_password, confirm_password]):
            return api_response(False, '所有字段都必须填写', code=400)
        
        if new_password != confirm_password:
            return api_response(False, '新密码和确认密码不匹配', code=400)
        
        min_length = _password_min_length()
        if len(new_password) < min_length:
            return api_response(False, f'新密码长度至少需要{min_length}个字符', code=400)
        
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        try:
            table_name = 'admininfo' if current_user.is_admin else 'userinfo'
            
            # 验证当前密码
            cursor.execute(f'SELECT password FROM {table_name} WHERE id = %s', (current_user.id,))
            user = cursor.fetchone()
            
            if not user or not check_password_hash(user['password'], current_password):
                return api_response(False, '当前密码不正确', code=401)
            
            # 更新密码
            hashed_password = generate_password_hash(new_password)
            cursor.execute(
                f'UPDATE {table_name} SET password = %s WHERE id = %s',
                (hashed_password, current_user.id)
            )
            conn.commit()
            
            logger.info(f"用户 {current_user.username} 修改了密码")
            return api_response(success=True, message='密码修改成功')
            
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        logger.error(f"修改密码异常: {str(e)}")
        return _server_error_response()


@api_bp.route('/auth/captcha', methods=['GET'])
def get_captcha():
    """获取验证码（可选功能）
    
    GET /api/auth/captcha
    """
    try:
        import random
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64
        
        # 生成随机验证码
        captcha_text = ''.join(random.choices('0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        session['captcha'] = captcha_text.lower()
        
        # 创建验证码图片
        width, height = 120, 40
        image = Image.new('RGB', (width, height), color=255)
        draw = ImageDraw.Draw(image)
        
        # 尝试加载字体
        try:
            font = ImageFont.truetype("arial.ttf", 24)
        except IOError:
            font = ImageFont.load_default()
        
        # 绘制文本
        text_bbox = draw.textbbox((0, 0), captcha_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        x = (width - text_width) / 2
        y = (height - text_height) / 2
        draw.text((x, y), captcha_text, font=font, fill=(0, 0, 0))
        
        # 添加干扰线
        for i in range(5):
            start = (random.randint(0, width), random.randint(0, height))
            end = (random.randint(0, width), random.randint(0, height))
            draw.line([start, end], fill=(0, 0, 0))
        
        # 添加干扰点
        for i in range(30):
            point = (random.randint(0, width), random.randint(0, height))
            draw.point(point, fill=(0, 0, 0))
        
        # 转换为base64
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return api_response(
            success=True,
            message='验证码生成成功',
            data={
                'image': f'data:image/png;base64,{image_base64}'
            }
        )
        
    except Exception as e:
        logger.error(f"生成验证码异常: {str(e)}")
        return _server_error_response()

