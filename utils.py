"""
工具函数模块，包含各种辅助函数
"""
import threading
import importlib
from movies_recommend.logger import get_logger

# 获取日志记录器
logger = get_logger('app')

# 全局变量，存储爬虫线程对象
scraper_thread = None

def load_scraper():
    """延迟加载爬虫模块

    Returns:
        module: 爬虫模块
    """
    return importlib.import_module('movies_recommend.tmdb_scraper')

def reset_scraper_state():
    """手动重置爬虫状态，清除可能卡住的爬虫进程信息
    
    Returns:
        bool: 是否成功重置
    """
    global scraper_thread
    
    try:
        # 重置线程对象
        scraper_thread = None
        
        # 重置爬虫进度
        scraper_module = load_scraper()
        scraper_module.reset_progress()
        
        logger.info("已手动重置爬虫状态")
        return True
    except Exception as e:
        logger.error(f"重置爬虫状态失败: {e}")
        return False

def run_scraper_async():
    """异步执行爬虫任务，确保状态正确更新

    Returns:
        bool: 是否成功启动爬虫
    """
    global scraper_thread

    # 检查是否有线程正在运行
    if scraper_thread and scraper_thread.is_alive():
        logger.info("爬虫线程已在运行中，不再启动新线程")
        return False  # 如果线程正在运行，则返回False

    try:
        # 导入爬虫模块（只导入一次）
        scraper_module = load_scraper()

        # 获取爬虫当前状态
        progress = scraper_module.get_progress()
        logger.info(f"当前爬虫状态: {progress['status']}, 进度: {progress['current']}%, 处理电影数: {progress['processed_movies']}")
        
        # 如果状态为running，检查线程是否实际运行
        if progress["status"] == "running":
            # 可能之前的爬虫异常退出，但状态未更新
            # 如果scraper_thread为None或不活跃，重置状态
            if scraper_thread is None or not scraper_thread.is_alive():
                logger.info("检测到爬虫状态为运行中，但爬虫线程已停止，重置状态")
                scraper_module.update_progress(status="idle", message="爬虫状态已重置")
            else:
                logger.info("爬虫状态为运行中且线程活跃，不再启动新线程")
                return False

        def task():
            try:
                # 确保爬虫状态被正确设置为running
                logger.info("启动爬虫任务，设置初始状态")
                
                # 更新状态，确保开始进度为0
                scraper_module.update_progress(
                    current=0,
                    status="running", 
                    message="爬虫任务已启动，正在获取电影数据", 
                    processed_movies=progress["processed_movies"]
                )
                
                # 启动爬虫
                logger.info("开始异步爬取电影数据")
                # 如果已有进度，则继续使用该进度
                scraper_module.fetch_and_save_top_rated_movies(
                    pages=500, 
                    target_movies=50000,
                    resume=True
                )
                logger.info("异步爬取电影数据完成")
            except Exception as e:
                logger.error(f"爬虫执行过程中出错: {e}")
                # 确保更新爬虫状态为错误
                scraper_module.update_progress(status="error", message=f"爬虫出错: {e}")

        # 创建并启动线程
        scraper_thread = threading.Thread(target=task)
        scraper_thread.daemon = True  # 设置为守护线程，这样主线程结束时它也会结束
        scraper_thread.start()
        logger.info("爬虫线程已启动")
        return True
    except Exception as e:
        logger.error(f"启动爬虫失败: {e}")
        return False

def run_custom_scraper(params):
    """根据自定义条件异步执行爬虫任务
    
    Args:
        params (dict): 自定义抓取参数
            - keyword (str): 搜索关键词
            - director (str): 导演名称
            - actor (str): 演员名称
            - language (str): 语言代码
            - region (str): 地区代码
            - min_rating (str): 最低评分
            - genre (str): 电影类型ID
            - year (str): 发行年份
            - page_count (int): 爬取的页数
    
    Returns:
        bool: 是否成功启动爬虫
    """
    global scraper_thread
    
    # 检查是否有线程正在运行
    if scraper_thread and scraper_thread.is_alive():
        logger.info("爬虫线程已在运行中，无法启动自定义抓取")
        return False  # 如果线程正在运行，则返回False
    
    try:
        # 导入爬虫模块
        scraper_module = load_scraper()
        
        # 获取爬虫当前状态
        progress = scraper_module.get_progress()
        
        # 如果状态为running，检查线程是否实际运行
        if progress["status"] == "running":
            if scraper_thread is None or not scraper_thread.is_alive():
                logger.info("检测到爬虫状态为运行中，但爬虫线程已停止，重置状态")
                scraper_module.update_progress(status="idle", message="爬虫状态已重置")
            else:
                logger.info("爬虫状态为运行中且线程活跃，无法启动自定义抓取")
                return False
        
        # 记录自定义抓取参数
        logger.info(f"准备执行自定义抓取，参数: {params}")
        
        def task():
            try:
                # 更新状态为running
                scraper_module.update_progress(
                    current=0,
                    status="running",
                    message="自定义抓取任务已启动，正在准备查询参数",
                    processed_movies=progress["processed_movies"]
                )
                
                # 提取参数
                keyword = params.get('keyword', '')
                director = params.get('director', '')
                actor = params.get('actor', '')
                language = params.get('language', '')
                region = params.get('region', '')
                min_rating = params.get('min_rating', '')
                genre = params.get('genre', '')
                year = params.get('year', '')
                page_count = int(params.get('page_count', 1))
                
                # 构建搜索条件
                search_params = {}
                
                # 添加关键词搜索
                if keyword:
                    search_params['query'] = keyword
                
                # 添加语言筛选
                if language:
                    search_params['with_original_language'] = language
                
                # 添加地区筛选
                if region:
                    search_params['region'] = region
                
                # 添加最低评分筛选
                if min_rating and min_rating.replace('.', '', 1).isdigit():
                    search_params['vote_average.gte'] = float(min_rating)
                
                # 添加类型筛选
                if genre:
                    search_params['with_genres'] = genre
                
                # 添加年份筛选
                if year and year.isdigit():
                    search_params['primary_release_year'] = year
                
                # 判断是按关键词搜索还是按高级条件搜索
                if keyword:
                    logger.info(f"执行关键词搜索，关键词: {keyword}, 页数: {page_count}")
                    scraper_module.update_progress(message=f"执行关键词搜索: {keyword}")
                    
                    # 使用关键词搜索
                    scraper_module.fetch_movies_by_search(
                        query=keyword,
                        pages=page_count
                    )
                elif director or actor:
                    # 需要先搜索人物ID
                    person_name = director or actor
                    person_type = "导演" if director else "演员"
                    
                    logger.info(f"搜索{person_type}: {person_name}")
                    scraper_module.update_progress(message=f"正在搜索{person_type}: {person_name}")
                    
                    # 搜索人物
                    person_id = scraper_module.search_person(person_name)
                    
                    if person_id:
                        logger.info(f"找到{person_type} ID: {person_id}，开始获取相关电影")
                        scraper_module.update_progress(message=f"找到{person_type} ID: {person_id}，正在获取相关电影")
                        
                        # 使用人物ID搜索电影
                        scraper_module.fetch_movies_by_person(
                            person_id=person_id, 
                            is_director=(person_type == "导演")
                        )
                    else:
                        logger.warning(f"未找到{person_type}: {person_name}")
                        scraper_module.update_progress(
                            status="error", 
                            message=f"未找到{person_type}: {person_name}"
                        )
                else:
                    # 使用高级搜索
                    logger.info(f"执行高级条件搜索，条件: {search_params}, 页数: {page_count}")
                    scraper_module.update_progress(message=f"执行高级条件搜索")
                    
                    # 使用发现API进行高级搜索
                    scraper_module.fetch_movies_by_discover(
                        params=search_params,
                        pages=page_count
                    )
                
                logger.info("自定义抓取任务完成")
                scraper_module.update_progress(
                    status="completed",
                    message="自定义抓取任务完成"
                )
            except Exception as e:
                logger.error(f"自定义抓取任务执行过程中出错: {e}")
                scraper_module.update_progress(
                    status="error",
                    message=f"自定义抓取出错: {e}"
                )
        
        # 创建并启动线程
        scraper_thread = threading.Thread(target=task)
        scraper_thread.daemon = True
        scraper_thread.start()
        logger.info("自定义抓取线程已启动")
        return True
    except Exception as e:
        logger.error(f"启动自定义抓取任务失败: {e}")
        return False
