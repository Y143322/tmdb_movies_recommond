"""
API 请求日志记录工具，帮助调试
"""
from flask import request, current_app


def _mask_sensitive_mapping(data):
    """对映射中的敏感键做脱敏处理。"""
    masked = {}
    for key, value in dict(data).items():
        key_lower = str(key).lower()
        if any(token in key_lower for token in ('password', 'token', 'secret', 'authorization', 'cookie')):
            masked[key] = '******'
        else:
            masked[key] = value
    return masked

def log_api_request():
    """记录API请求到日志，保护敏感信息"""
    is_auth_page = request.path.startswith('/auth')
    is_api_path = request.path.startswith('/api/')
    if is_auth_page or is_api_path:
        log_level = (current_app.config.get('REQUEST_LOG_LEVEL') or '').upper()
        debug_mode = bool(current_app.config.get('DEBUG', False))
        should_log_payload = debug_mode or log_level == 'DEBUG'

        try:
            current_app.logger.info(f"请求路径: {request.method} {request.path}")
            safe_headers = {
                'User-Agent': request.headers.get('User-Agent'),
                'Content-Type': request.headers.get('Content-Type'),
                'Accept': request.headers.get('Accept'),
                'X-Requested-With': request.headers.get('X-Requested-With')
            }
            if should_log_payload:
                current_app.logger.info(f"请求头(安全): {safe_headers}")
            else:
                current_app.logger.debug(f"请求头(安全): {safe_headers}")
            
            if request.method == 'POST':
                if request.is_json:
                    try:
                        # 获取JSON数据并创建安全副本
                        json_data = request.get_json(silent=True)
                        if isinstance(json_data, dict):
                            safe_json = _mask_sensitive_mapping(json_data)
                            if should_log_payload:
                                current_app.logger.info(f"JSON数据(安全): {safe_json}")
                            else:
                                current_app.logger.debug("JSON数据(安全): [已采样省略]")
                        else:
                            current_app.logger.debug(f"JSON数据: [非字典数据]")
                    except Exception as e:
                        current_app.logger.error(f"处理JSON数据时出错: {e}")
                else:
                    # 创建表单数据的安全副本
                    safe_form_data = _mask_sensitive_mapping(request.form)
                    if should_log_payload:
                        current_app.logger.info(f"表单数据(安全): {safe_form_data}")
                    else:
                        current_app.logger.debug("表单数据(安全): [已采样省略]")
                
                try:
                    # 对原始请求体进行脱敏处理
                    if should_log_payload:
                        body = request.get_data(cache=True, as_text=True)
                        # 简单的密码脱敏，实际生产环境可能需要更复杂的正则替换
                        if 'password' in body.lower():
                            body = "[包含敏感信息，已脱敏]"
                        elif len(body) > 1000:
                            body = body[:997] + "..."  # 避免太长的请求体
                        current_app.logger.info(f"原始请求体(安全): {body}")
                    else:
                        current_app.logger.debug("原始请求体(安全): [已采样省略]")
                except Exception as e:
                    current_app.logger.error(f"处理请求体时出错: {e}")
        except Exception as e:
            current_app.logger.error(f"记录API请求时出错: {e}")
