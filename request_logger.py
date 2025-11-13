"""
API 请求日志记录工具，帮助调试
"""
from flask import request, current_app
import json

def log_api_request():
    """记录API请求到日志，保护敏感信息"""
    if request.path.startswith('/auth'):
        try:
            current_app.logger.info(f"请求路径: {request.method} {request.path}")
            current_app.logger.info(f"请求头: {dict(request.headers)}")
            
            if request.method == 'POST':
                if request.is_json:
                    try:
                        # 获取JSON数据并创建安全副本
                        json_data = request.get_json()
                        if isinstance(json_data, dict):
                            safe_json = json_data.copy()
                            if 'password' in safe_json:
                                safe_json['password'] = '******'  # 替换密码
                            current_app.logger.info(f"JSON数据(安全): {safe_json}")
                        else:
                            current_app.logger.info(f"JSON数据: [非字典数据]")
                    except Exception as e:
                        current_app.logger.error(f"处理JSON数据时出错: {e}")
                else:
                    # 创建表单数据的安全副本
                    safe_form_data = dict(request.form)
                    if 'password' in safe_form_data:
                        safe_form_data['password'] = '******'  # 替换密码
                    current_app.logger.info(f"表单数据(安全): {safe_form_data}")
                
                try:
                    # 对原始请求体进行脱敏处理
                    body = request.get_data().decode('utf-8')
                    # 简单的密码脱敏，实际生产环境可能需要更复杂的正则替换
                    if 'password' in body.lower():
                        body = "[包含敏感信息，已脱敏]"
                    elif len(body) > 1000:
                        body = body[:997] + "..."  # 避免太长的请求体
                    current_app.logger.info(f"原始请求体(安全): {body}")
                except Exception as e:
                    current_app.logger.error(f"处理请求体时出错: {e}")
        except Exception as e:
            current_app.logger.error(f"记录API请求时出错: {e}")
