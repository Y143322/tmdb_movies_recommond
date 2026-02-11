"""
用户API模块 - 提供用户相关接口（观看历史、我的评分、偏好设置等）
"""
from flask import request, jsonify
from flask_login import login_required, current_user
from movies_recommend.blueprints.api import api_bp
from movies_recommend.logger import get_logger
from movies_recommend.extensions import get_db_connection
import pymysql

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


@api_bp.route('/users/me/summary', methods=['GET'])
@login_required
def get_user_summary():
    """获取当前登录用户摘要信息。"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        try:
            cursor.execute(
                '''
                SELECT
                    (SELECT COUNT(*) FROM user_ratings WHERE user_id = %s) AS ratings,
                    (SELECT COUNT(*) FROM user_watch_history WHERE user_id = %s) AS watch_history,
                    (SELECT COUNT(*) FROM user_genre_preferences WHERE user_id = %s) AS preferences
                ''',
                (current_user.id, current_user.id, current_user.id)
            )
            stat_row = cursor.fetchone() or {}
            total_ratings = int(stat_row.get('ratings', 0) or 0)
            total_history = int(stat_row.get('watch_history', 0) or 0)
            total_preferences = int(stat_row.get('preferences', 0) or 0)

            return api_response(
                success=True,
                message='获取成功',
                data={
                    'userId': current_user.id,
                    'username': current_user.username,
                    'isAdmin': bool(current_user.is_admin),
                    'stats': {
                        'ratings': total_ratings,
                        'watchHistory': total_history,
                        'preferences': total_preferences,
                    },
                },
            )
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f'获取用户摘要失败: {e}')
        return api_response(False, '服务器内部错误', code=500)

