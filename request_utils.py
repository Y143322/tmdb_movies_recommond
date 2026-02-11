"""
请求相关工具函数。
"""
from flask import request as flask_request


def is_api_request(req=None):
    """判断当前请求是否期望 JSON 响应。"""
    current_request = req or flask_request
    accept_header_value = current_request.headers.get('Accept')
    accept_header = accept_header_value.lower() if isinstance(accept_header_value, str) else ''
    return (
        current_request.path.startswith('/api/') or
        current_request.is_json or
        'application/json' in accept_header or
        current_request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        current_request.args.get('format') == 'json'
    )


def normalize_id_list(raw_ids):
    """将外部传入 ID 列表规范为正整数列表。"""
    normalized = []
    if not isinstance(raw_ids, list):
        return normalized

    for item in raw_ids:
        try:
            value = int(item)
            if value > 0:
                normalized.append(value)
        except (TypeError, ValueError):
            continue

    return normalized
