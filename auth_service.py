"""
认证领域服务：集中封装注册/登录核心数据库逻辑。
"""
from __future__ import annotations

import re
import threading
from typing import Any, Dict, Optional, Tuple

from werkzeug.security import check_password_hash, generate_password_hash


_next_user_id_proc_available = None
_next_user_id_proc_lock = threading.Lock()


def _first_cell(row: Any, key: Optional[str] = None) -> Any:
    """兼容 DictCursor / 普通游标的首字段读取。"""
    if isinstance(row, dict):
        if key:
            return row.get(key)
        return next(iter(row.values()), None)
    if isinstance(row, (list, tuple)):
        return row[0] if row else None
    return None


def validate_email(email: str) -> bool:
    """校验邮箱格式。"""
    if not email:
        return True
    return re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email) is not None


def validate_username(username: str) -> bool:
    """校验用户名字符集。"""
    return re.match(r'^[a-zA-Z0-9_]+$', username or '') is not None


def username_exists(cursor, username: str) -> bool:
    """判断用户名是否存在于管理员/普通用户任一表。"""
    cursor.execute('SELECT id FROM userinfo WHERE username = %s', (username,))
    if cursor.fetchone():
        return True

    cursor.execute('SELECT id FROM admininfo WHERE username = %s', (username,))
    return cursor.fetchone() is not None


def _is_user_id_occupied(cursor, user_id: int) -> bool:
    """检查候选用户 ID 是否已被 userinfo/admininfo 占用。"""
    cursor.execute(
        '''
        SELECT 1 FROM userinfo WHERE id = %s
        UNION ALL
        SELECT 1 FROM admininfo WHERE id = %s
        LIMIT 1
        ''',
        (user_id, user_id)
    )
    return cursor.fetchone() is not None


def find_user_by_username(cursor, username: str) -> Tuple[Optional[Dict[str, Any]], bool]:
    """按用户名查找用户，优先管理员表。"""
    cursor.execute('SELECT * FROM admininfo WHERE username = %s', (username,))
    admin_data = cursor.fetchone()
    if admin_data:
        return admin_data, True

    cursor.execute('SELECT * FROM userinfo WHERE username = %s', (username,))
    user_data = cursor.fetchone()
    if user_data:
        return user_data, False

    return None, False


def allocate_next_user_id(cursor, user_type: str, logger) -> int:
    """分配下一用户ID：优先存储过程，失败时使用数据库命名锁回退。"""
    global _next_user_id_proc_available

    should_try_procedure = _next_user_id_proc_available is not False
    if should_try_procedure:
        try:
            if user_type == 'admin':
                cursor.execute("CALL get_next_user_id(@next_id, 'admin')")
            else:
                cursor.execute("CALL get_next_user_id(@next_id, 'user')")

            cursor.execute('SELECT @next_id')
            row = cursor.fetchone()
            next_id = _first_cell(row)
            if next_id is not None:
                candidate_id = int(next_id)
                if not _is_user_id_occupied(cursor, candidate_id):
                    _next_user_id_proc_available = True
                    return candidate_id

                with _next_user_id_proc_lock:
                    _next_user_id_proc_available = False
                logger.warning('get_next_user_id 返回了已占用 ID，切换到命名锁回退策略')
        except Exception as error:
            with _next_user_id_proc_lock:
                first_failure = _next_user_id_proc_available is None
                _next_user_id_proc_available = False
            if first_failure:
                logger.warning(f"get_next_user_id 不可用，使用命名锁回退ID策略: {error}")

    lock_name = 'movies_recommend_next_user_id_lock'
    cursor.execute('SELECT GET_LOCK(%s, 5)', (lock_name,))
    lock_row = cursor.fetchone()
    lock_acquired = int(_first_cell(lock_row) or 0) == 1
    if not lock_acquired:
        raise RuntimeError('无法获取用户ID分配锁，请稍后重试')

    try:
        cursor.execute('''
            SELECT GREATEST(
                COALESCE((SELECT MAX(id) FROM userinfo), 0),
                COALESCE((SELECT MAX(id) FROM admininfo), 0)
            ) + 1 AS next_id
        ''')
        fallback_row = cursor.fetchone()
        fallback_id = _first_cell(fallback_row, 'next_id')
        if fallback_id is None:
            raise RuntimeError('无法生成新用户ID')
        return int(fallback_id)
    finally:
        try:
            cursor.execute('SELECT RELEASE_LOCK(%s)', (lock_name,))
        except Exception:
            pass


def create_user_record(cursor, username: str, password: str, email: str, user_type: str, logger) -> Tuple[int, bool]:
    """创建用户记录并返回 (user_id, is_admin)。"""
    normalized_user_type = 'admin' if user_type == 'admin' else 'normal'
    next_id = allocate_next_user_id(cursor, normalized_user_type, logger)
    hashed_password = generate_password_hash(password)

    if normalized_user_type == 'admin':
        cursor.execute(
            'INSERT INTO admininfo (id, username, password, email) VALUES (%s, %s, %s, %s)',
            (next_id, username, hashed_password, email)
        )
        return next_id, True

    cursor.execute(
        'INSERT INTO userinfo (id, username, password, email) VALUES (%s, %s, %s, %s)',
        (next_id, username, hashed_password, email)
    )
    return next_id, False


def verify_user_credentials(cursor, username: str, password: str) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    """验证用户名密码，返回 (user_data, is_admin, error_code)。"""
    user_data, is_admin = find_user_by_username(cursor, username)
    if not user_data:
        return None, False, 'invalid_credentials'

    stored_password = user_data.get('password') if isinstance(user_data, dict) else None
    if not isinstance(stored_password, str) or not check_password_hash(stored_password, password):
        return None, False, 'invalid_credentials'

    if not is_admin:
        status = user_data.get('status', 'active')
        if status == 'deleted':
            return None, False, 'deleted'
        if status == 'banned':
            return None, False, 'banned'

    return user_data, is_admin, None
