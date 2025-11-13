"""API蓝图模块"""
from flask import Blueprint

# 创建API蓝图
api_bp = Blueprint('api', __name__, url_prefix='/api')

# 导入子模块以注册路由（这会自动注册装饰器定义的路由）
from . import api_auth, api_movies, api_user

