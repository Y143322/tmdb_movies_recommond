# 电影评分推荐系统

## 项目概述

这是一个基于Python和Flask的电影评分推荐系统，结合了协同过滤和基于内容的推荐算法，为用户提供个性化电影推荐服务。该系统使用TMDB（The Movie Database）API获取电影数据，通过分析用户的观影历史和评分记录，推荐用户可能感兴趣的电影。

### 技术栈

- **后端**: Python 3.12, Flask, Blueprint
- **数据库**: MySQL 8.0 (生产环境), SQLite (开发环境)
- **前端**: HTML, CSS, JavaScript, Bootstrap
- **数据分析**: NumPy, Pandas, Scikit-learn
- **爬虫**: TMDB API, Requests
- **部署**: Docker (可选)

## 环境要求

- Python 3.12 或更高版本
- MySQL 8.0 或更高版本
- pip (Python包管理器)
- 现代浏览器 (Chrome, Firefox, Edge等)

## 快速开始

### 1. 克隆仓库(已经改为私有)

```bash
git clone https://github.com/your-username/movies-recommend.git 
cd movies-recommend
```

### 2. 安装依赖

```bash
pip install -r requirements_tmdb.txt
```

### 3. 配置数据库

修改`config.py`文件中的数据库配置：

```python
DB_CONFIG = {
    'host': 'localhost',
    'user': '你的数据库用户名',
    'password': '你的数据库密码',
    'database': 'movies_recommend',
    'charset': 'utf8mb4'
}
```

### 4. 创建数据库表

使用提供的SQL脚本创建数据库表：

```bash
# 登录MySQL
mysql -u root -p

# 创建数据库
CREATE DATABASE movies_recommend CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 使用数据库
USE movies_recommend;

# 退出MySQL
exit

# 导入表结构
mysql -u root -p movies_recommend < doc/create_tables.sql
```

### 5. 抓取电影数据

运行爬虫脚本获取电影数据：

```bash
python run_scraper.py
```

### 6. 启动应用

```bash
python app.py
```

访问 http://localhost:5000 查看应用。

## 项目结构

```
movies_recommend/
├── app.py                    # Flask应用主入口
├── config.py                 # 配置文件
├── db_utils.py               # 数据库工具函数
├── recommender.py            # 推荐算法实现
├── tmdb_scraper.py           # TMDB API爬虫
├── run_scraper.py            # 爬虫启动脚本
├── models.py                 # 数据模型定义
├── extensions.py             # Flask扩展初始化
├── utils.py                  # 通用工具函数
├── logger.py                 # 日志配置
├── doc/                      # 项目文档目录
│   ├── README.md             # 项目说明文档
│   ├── create_tables.sql     # 数据库表创建SQL
│   ├── ER.sql                # 数据库ER关系
│   ├── 技术栈文档.md         # 技术栈分析
│   ├── 推荐系统分析报告.md   # 推荐系统分析
│   └── requirements.txt      # 项目文档模块的依赖包
├── requirements_tmdb.txt     # 依赖库清单
├── .gitignore                # Git忽略配置
├── blueprints/               # Flask蓝图
│   ├── __init__.py           # 蓝图包初始化
│   ├── auth.py               # 认证蓝图
│   ├── main.py               # 主页蓝图
│   ├── movies.py             # 电影蓝图
│   └── admin.py              # 管理员蓝图
├── templates/                # HTML模板
│   ├── base.html             # 基础模板
│   ├── index.html            # 首页模板
│   ├── login.html            # 登录页模板
│   ├── register.html         # 注册页模板
│   ├── movie_detail.html     # 电影详情页模板
│   ├── movies.html           # 电影列表页模板
│   ├── profile.html          # 用户资料页模板
│   ├── user_ratings.html     # 用户评分页模板
│   ├── watch_history.html    # 观影历史页模板
│   ├── change_password.html  # 修改密码页模板
│   └── errors/               # 错误页面
│       ├── 404.html          # 404错误页面
│       └── 500.html          # 500错误页面
└── static/                   # 静态资源
    ├── css/                  # CSS样式文件
    ├── js/                   # JavaScript文件
    └── images/               # 图片资源
```

## 核心功能

### 1. 用户系统

- 用户注册与登录
- 用户资料管理
- 密码修改与重置
- 用户权限管理

### 2. 电影数据管理

- 电影基本信息展示
- 电影搜索与过滤
- 电影分类浏览
- 最新/最热/最高评分电影列表

### 3. 评分与评论

- 用户电影评分
- 评分历史记录
- 用户评论管理
- 观影历史记录

### 4. 推荐系统

- **协同过滤推荐**：基于相似用户的观影偏好
- **基于内容的推荐**：基于电影特征（类型、演员、导演等）
- **混合推荐策略**：结合两种算法优点
- **冷启动处理**：为新用户提供热门电影推荐

### 5. 管理后台

- 用户管理
- 电影数据管理
- 系统监控
- 数据分析统计

## 推荐算法详解

### 协同过滤算法

协同过滤算法基于用户的历史行为，通过分析用户之间的相似性来进行推荐：

1. 构建用户-电影评分矩阵
2. 使用KNN算法找到相似用户
3. 分析相似用户的评分记录
4. 推荐相似用户高评分但当前用户未看过的电影

### 基于内容的推荐

基于内容的推荐算法分析电影的特征（类型、演员、导演等），推荐具有相似特征的电影：

1. 提取电影特征（类型、演员、上映时间等）
2. 使用TF-IDF向量化电影特征
3. 计算电影之间的余弦相似度
4. 推荐与用户已评分电影相似的其他电影

## API文档

### 用户API

| 路径 | 方法 | 描述 | 参数 |
|------|------|------|------|
| `/api/register` | POST | 用户注册 | username, password, email |
| `/api/login` | POST | 用户登录 | username, password |
| `/api/user/profile` | GET | 获取用户资料 | token |
| `/api/user/ratings` | GET | 获取用户评分 | token |

### 电影API

| 路径 | 方法 | 描述 | 参数 |
|------|------|------|------|
| `/api/movies` | GET | 获取电影列表 | page, limit, sort |
| `/api/movies/<id>` | GET | 获取电影详情 | id |
| `/api/movies/search` | GET | 搜索电影 | query, page |
| `/api/movies/recommend` | GET | 获取推荐电影 | token |

### 评分API

| 路径 | 方法 | 描述 | 参数 |
|------|------|------|------|
| `/api/rate` | POST | 评分电影 | token, movie_id, rating, comment |
| `/api/rate/<id>` | PUT | 更新评分 | token, rating, comment |
| `/api/rate/<id>` | DELETE | 删除评分 | token |

## 性能优化

1. **数据库优化**：
   - 使用合适的索引提高查询性能
   - 连接池管理数据库连接
   - 优化SQL查询，减少不必要的连接

2. **缓存策略**：
   - 缓存推荐结果，减少重复计算
   - 定期更新推荐模型，平衡实时性和性能

3. **异步处理**：
   - 使用异步任务处理耗时操作
   - 数据爬取和更新在后台进行

## 安全措施

1. **用户认证与授权**：
   - 密码哈希存储
   - 会话管理和JWT认证
   - 权限控制

2. **输入验证**：
   - 表单验证
   - SQL参数化查询防注入
   - XSS防护

3. **数据保护**：
   - CSRF防护
   - 敏感数据加密
   - 请求限流防止暴力攻击

## 常见问题

**Q: 如何修改数据库配置?**  
A: 编辑`config.py`文件中的`DB_CONFIG`字典。

**Q: 如何获取TMDB API密钥?**  
A: 访问[TMDB官网](https://www.themoviedb.org/)注册账号，然后申请API密钥。

**Q: 推荐系统如何处理冷启动问题?**  
A: 对于新用户，系统会推荐热门电影；随着用户评分增加，逐步过渡到个性化推荐。

**Q: 如何添加新的推荐算法?**  
A: 在`recommender.py`中实现新的推荐方法，并在`get_recommendations`方法中集成。

