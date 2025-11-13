"""
用户API模块 - 提供用户相关接口（观看历史、我的评分、偏好设置等）
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from flask import request, jsonify
from flask_login import login_required, current_user
from movies_recommend.blueprints.api import api_bp
from movies_recommend.logger import get_logger

logger = get_logger('api_user')


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


# TODO: 实现用户相关的API接口
# - 观看历史
# - 我的评分
# - 用户偏好设置
# - 等等

# 这些接口将在核心功能完成后实现

