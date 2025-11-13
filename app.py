"""
电影推荐系统应用主模块
"""
import os
import sys
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import datetime
import warnings
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify

# 禁用所有警告
warnings.filterwarnings('ignore')

# 导入配置
from movies_recommend.config import config
from movies_recommend.logger import get_logger
from movies_recommend.db_utils import test_db_connection

# 获取日志记录器
logger = get_logger('app')

def create_app(config_name='development'):
    """创建Flask应用实例

    Args:
        config_name (str, optional): 配置名称. 默认为 'development'.

    Returns:
        Flask: Flask应用实例
    """
    # 创建Flask应用，使用仓库内的静态资源和模板目录（static/ 和 templates/）
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
    templates_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
    app = Flask(__name__,
                static_folder=static_dir,
                static_url_path='/static',
                template_folder=templates_dir)

    # 加载配置
    app_config = config[config_name]
    app.config.from_object(app_config)
    
    # 添加APScheduler配置
    app.config['SCHEDULER_API_ENABLED'] = True
    app.config['SCHEDULER_TIMEZONE'] = 'Asia/Shanghai'

    # 初始化扩展
    from movies_recommend.extensions import init_db_pool, login_manager, scheduler
    init_db_pool(app)
    login_manager.init_app(app)

    # 只在开发模式或主进程中初始化调度器
    if config_name == 'development' or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            scheduler.init_app(app)
            # 启动定时任务
            if not scheduler.running:
                scheduler.start()
                logger.info("定时任务调度器已启动")
        except Exception as e:
            logger.warning(f"初始化调度器失败（可能已在运行）: {e}")
    
    # 配置CORS（跨域资源共享）
    # 注意：在生产环境中，由于Vue前端已集成到Flask中，CORS配置主要用于开发环境
    # 如果您使用独立的开发服务器（npm run dev），需要保持CORS配置
    from flask_cors import CORS
    if config_name == 'development':
        # 开发环境：允许Vue开发服务器跨域访问
        CORS(app,
             origins=['http://localhost:5173', 'http://127.0.0.1:5173'],  # Vue开发服务器
             supports_credentials=True,  # 支持cookies
             allow_headers=['Content-Type', 'Authorization'],
             methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
    # 生产环境不需要CORS，因为前后端同源

    # 添加定时任务（如果调度器已初始化）
    if scheduler.running:
        from movies_recommend.tasks import clear_expired_mutes, update_movie_popularity

        # 定义任务：每小时执行一次清理过期禁言的任务
        @scheduler.task('interval', id='clear_expired_mutes', hours=1, misfire_grace_time=900)
        def scheduled_clear_mutes():
            """定时清理过期禁言状态的任务"""
            app.logger.info("执行定时任务: 清理过期的用户禁言")
            success = clear_expired_mutes()
            if success:
                app.logger.info("定时清理过期禁言成功完成")
            else:
                app.logger.error("定时清理过期禁言失败")

        # 定义任务：每天凌晨2点执行一次电影热度更新任务
        @scheduler.task('cron', id='update_movie_popularity', hour=2, minute=0, misfire_grace_time=3600)
        def scheduled_update_popularity():
            """定时更新电影热度的任务"""
            app.logger.info("执行定时任务: 更新电影热度")
            success = update_movie_popularity()
            if success:
                app.logger.info("定时更新电影热度成功完成")
            else:
                app.logger.error("定时更新电影热度失败")

    # 自定义未授权处理函数
    @login_manager.unauthorized_handler
    def unauthorized():
        flash('请先登录', 'info')
        return render_template('errors/not_authenticated.html'), 401

    # 添加全局上下文处理器
    @app.context_processor
    def inject_now():
        return {'now': datetime.datetime.now}

    # 添加API请求日志中间件
    @app.before_request
    def log_api_request():
        """记录API请求信息，确保不记录敏感信息如密码"""
        if request.path.startswith('/auth'):
            app.logger.info(f"请求路径: {request.method} {request.path}")
            if 'User-Agent' in request.headers:
                app.logger.info(f"User-Agent: {request.headers.get('User-Agent')}")
            if request.method == 'POST':
                # 创建表单数据的安全副本，移除密码字段
                safe_form_data = dict(request.form)
                if 'password' in safe_form_data:
                    safe_form_data['password'] = '******'  # 替换为星号
                app.logger.info(f"表单数据(安全): {safe_form_data}")

    # 注册自定义过滤器
    @app.template_filter('intersect')
    def intersect_filter(list1, list2):
        """返回两个列表的交集

        Args:
            list1: 第一个列表
            list2: 第二个列表

        Returns:
            list: 两个列表的交集
        """
        if not list1 or not list2:
            return []
        return [item for item in list1 if item in list2]

    @app.template_filter('safe_comment')
    def safe_comment_filter(text):
        """安全渲染用户评论/回复内容：
        1. 统一转义 HTML
        2. 删除潜在危险的事件属性 / <script> 标签
        3. 保留换行 -> <br>
        Args:
            text (str|None): 原始用户输入
        Returns:
            Markup: 安全的 HTML 片段
        """
        from markupsafe import Markup, escape
        import re
        if not text:
            return Markup('')
        # 先统一换行标准化
        normalized = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = normalized.split('\n')
        cleaned_lines = []
        danger_patterns = [re.compile(r'onerror\s*=', re.IGNORECASE),
                           re.compile(r'javascript\s*:', re.IGNORECASE)]
        for line in lines:
            # 如果整行包含危险关键字则直接丢弃该行
            if any(p.search(line) for p in danger_patterns):
                continue
            cleaned_lines.append(line)
        cleaned_text = '\n'.join(cleaned_lines)
        # 转义后再把换行变为 <br>
        escaped = escape(cleaned_text)
        escaped = escaped.replace('\n', '<br>')
        return Markup(escaped)

    # 注册蓝图（启用传统模板渲染的蓝图以及API蓝图）
    from movies_recommend.blueprints.auth import auth_bp
    from movies_recommend.blueprints.main import main_bp
    from movies_recommend.blueprints.movies import movies_bp
    from movies_recommend.blueprints.admin import admin_bp
    from movies_recommend.blueprints.api import api_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)
    app.register_blueprint(movies_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)  # API蓝图已经在__init__.py中设置了url_prefix='/api'

    # 错误处理器：对于 API 返回 JSON，对于 UI 渲染错误模板
    @app.errorhandler(404)
    def page_not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500

    return app

def init_recommender():
    """初始化推荐系统"""
    try:
        from movies_recommend.recommender import _recommender
        # 使用非详细模式加载数据，减少日志输出
        _recommender.load_data(verbose=False)
        logger.info("推荐系统初始化完成")
        return True
    except Exception as e:
        logger.error(f"初始化推荐系统失败: {e}")
        return False

# 应用实例
app = create_app()


if __name__ == '__main__':
    # 测试数据库连接
    if not test_db_connection(app.config['DB_CONFIG']):
        logger.error("数据库连接失败，应用程序无法启动")
        logger.error("请修改DB_CONFIG中的配置信息，确保与您的MySQL设置一致")
        sys.exit(1)

    # 只在主进程中初始化推荐系统，避免重复输出
    import os
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    # 第一次启动或者是主进程时初始化推荐系统
    if is_reloader_process:
        logger.info("正在初始化推荐系统...")
        init_recommender()
        
        # 启动时立即执行一次清理过期禁言的操作
        from movies_recommend.tasks import clear_expired_mutes
        logger.info("启动时执行清理过期禁言...")
        success = clear_expired_mutes()
        if success:
            logger.info("启动时清理过期禁言完成")
        else:
            logger.error("启动时清理过期禁言失败")
    
    # 启动应用
    app.run(debug=True, use_reloader=True)
