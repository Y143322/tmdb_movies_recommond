# 🎬 电影推荐系统 (Movie Recommendation System)

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/downloads/)
[![Flask Version](https://img.shields.io/badge/flask-2.0%2B-green)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-orange)](LICENSE)

一个功能完整的电影推荐系统，基于 Flask 开发，集成了多种推荐算法，包括协同过滤、基于内容的推荐和基于知识的推荐。

## ✨ 主要特性

### 🎯 推荐算法
- **基于用户的协同过滤** - 根据相似用户的喜好推荐电影
- **基于物品的协同过滤** - 推荐与用户喜欢的电影相似的作品
- **基于内容的推荐** - 分析电影的导演、演员、类型等特征
- **基于知识的推荐** - 处理冷启动问题，为新用户提供推荐

### 📱 核心功能
- ✅ 用户注册/登录/个人资料管理
- ✅ 电影浏览、搜索和详情展示
- ✅ 10分制评分系统
- ✅ 评论和回复功能
- ✅ 评论点赞功能
- ✅ 用户电影类型偏好分析
- ✅ 观影历史记录
- ✅ 管理员后台管理
- ✅ RESTful API 接口

### 🔥 技术亮点
- 🚀 使用稀疏矩阵优化大规模数据处理
- 🎨 响应式设计，支持移动端
- 🔐 完善的安全措施（密码哈希、XSS防护、SQL注入防护）
- ⚡ 数据库连接池提升性能
- 🕐 定时任务自动更新电影热度
- 📊 实时热度更新机制

## 📸 系统截图

> 🎯 **提示**: 将截图放在 `screenshots/` 目录下，并在这里引用

```
screenshots/
├── home.png          # 首页
├── movie_detail.png  # 电影详情页
├── profile.png       # 用户资料
└── admin.png         # 管理后台
```

## 🛠️ 技术栈

### 后端
- **Web框架**: Flask 2.x
- **数据库**: MySQL 8.0+
- **ORM**: PyMySQL + DBUtils (连接池)
- **认证**: Flask-Login + JWT
- **任务调度**: APScheduler
- **数据处理**: NumPy, Pandas
- **机器学习**: Scikit-learn

### 前端
- **模板引擎**: Jinja2
- **样式**: 原生 CSS
- **交互**: 原生 JavaScript (AJAX)
- **图标**: Font Awesome

## 📋 系统要求

- Python 3.8 或更高版本
- MySQL 8.0 或更高版本
- 2GB+ 内存
- 磁盘空间 500MB+（不含电影数据）

## 🚀 快速开始

### ⚠️ 安全提醒

**在开始之前，请务必阅读 [安全检查清单](SECURITY_CHECKLIST.md)**

- 🔒 不要将 `.env` 文件上传到 GitHub
- 🔒 不要在代码中硬编码敏感信息
- 🔒 生产环境必须设置所有必需的环境变量
- 🔒 使用强密码和随机生成的密钥

---

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/movies-recommend.git
cd movies-recommend
```

### 2. 创建虚拟环境

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量 🔐

**⚠️ 重要：此步骤涉及敏感信息，请勿将 `.env` 文件上传到 GitHub！**

复制 `.env.example` 为 `.env` 并修改配置：

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

编辑 `.env` 文件，**填入您的真实配置**：

```env
# 数据库配置
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=你的数据库密码  # ⚠️ 请修改为您的实际密码
DB_NAME=movies_recommend

# Flask 配置 - ⚠️ 生产环境必须修改！
SECRET_KEY=使用随机生成的强密钥  # 运行: python -c "import secrets; print(secrets.token_urlsafe(32))"
FLASK_ENV=development

# JWT 配置 - ⚠️ 生产环境必须修改！
JWT_SECRET_KEY=使用随机生成的强密钥  # 运行: python -c "import secrets; print(secrets.token_urlsafe(32))"

# 管理员验证码 - ⚠️ 请修改为复杂的验证码
ADMIN_VERIFICATION_CODE=你的管理员验证码

# TMDB API（可选，用于爬取电影数据）
# TMDB_API_KEY=你的TMDB_API密钥
```

**💡 生成安全密钥的方法：**

```bash
# 在 Python 环境中运行
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('ADMIN_VERIFICATION_CODE=' + secrets.token_urlsafe(16))"
```
JWT_SECRET_KEY=your-jwt-secret-key

# 管理员验证码
ADMIN_VERIFICATION_CODE=admin123456
```

### 5. 初始化数据库

```bash
# 方式一：使用 Python 脚本（推荐）
python scripts/init_database.py

# 方式二：手动导入 SQL
mysql -u root -p movies_recommend < doc/create_tables.sql
```

### 6. 运行项目

```bash
# 开发模式
python app.py

# 或使用 Flask 命令
flask run --host=0.0.0.0 --port=5000
```

访问 http://localhost:5000

### 7. 使用 Docker 部署（推荐）

如果您安装了 Docker 和 Docker Compose，可以一键启动所有服务：

```bash
# 1. 修改 docker-compose.yml 中的密码配置

# 2. 启动所有服务
docker-compose up -d

# 3. 查看日志
docker-compose logs -f

# 4. 停止服务
docker-compose down

# 5. 停止并删除数据
docker-compose down -v
```

访问 http://localhost 或 http://localhost:5000

### 8. 默认账号

**管理员账号**（注册时使用管理员验证码）:
- 用户名: `admin`
- 密码: `123456qwe`
- 验证码: 配置文件中的 `ADMIN_VERIFICATION_CODE`

**普通用户**:
- 自行注册即可

---

## 📖 部署指南

### 🪟 Windows 部署
**请查看** → [Windows 部署指南](doc/DEPLOYMENT_WINDOWS.md)

包含内容：
- ✅ 详细的 Windows 安装步骤
- ✅ 使用 waitress 生产服务器
- ✅ 开机自启动配置（NSSM）
- ✅ 批处理脚本（一键启动/停止）
- ✅ Windows 专用故障排查

---

## 📚 项目结构

```
movies_recommend/
├── app.py                          # 应用入口
├── config.py                       # 配置管理
├── models.py                       # 数据模型
├── extensions.py                   # 扩展初始化
├── recommender.py                  # 推荐算法引擎
├── knowledge_recommender.py        # 知识推荐
├── user_preferences.py             # 用户偏好分析
├── tasks.py                        # 定时任务
├── logger.py                       # 日志配置
├── requirements.txt                # 依赖包列表
├── .env.example                    # 环境变量示例
├── .gitignore                      # Git 忽略文件
├── LICENSE                         # 开源许可证
│
├── blueprints/                     # Flask 蓝图
│   ├── auth.py                     # 认证模块
│   ├── main.py                     # 主页面路由
│   ├── movies.py                   # 电影相关路由
│   ├── admin.py                    # 管理员功能
│   └── api/                        # RESTful API
│       ├── api_auth.py
│       ├── api_movies.py
│       └── api_user.py
│
├── templates/                      # HTML 模板
│   ├── base.html
│   ├── index.html
│   ├── movie_detail.html
│   ├── admin/
│   └── errors/
│
├── static/                         # 静态资源
│   ├── css/
│   ├── js/
│   └── img/
│
├── doc/                            # 文档
│   ├── README.md
│   ├── API.md                      # API 文档
│   ├── DEPLOYMENT.md               # 部署指南
│   ├── DATABASE_STRUCTURE.md       # 数据库结构
│   └── create_tables.sql           # 建表脚本
│
└── scripts/                        # 工具脚本
    ├── init_database.py            # 初始化数据库
    ├── add_realistic_ratings.py    # 生成测试数据
    └── clear_expired_mutes.py      # 清理过期禁言
```

## 🔌 API 使用

系统提供完整的 RESTful API，详细文档请查看 [API.md](doc/API.md)

### 快速示例

```bash
# 登录获取 Token
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "password123"}'

# 获取电影列表
curl http://localhost:5000/api/movies?page=1&pageSize=10

# 获取个性化推荐（需要认证）
curl http://localhost:5000/api/recommendations \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 🗄️ 数据库设计

系统包含 23 张数据表，主要包括：

- **用户相关**: `userinfo`, `admininfo`, `user_genre_preferences`
- **电影相关**: `movies`, `persons`, `movie_cast`, `movie_crew`
- **交互相关**: `user_ratings`, `comment_replies`, `comment_likes`
- **推荐相关**: `recommendations`, `user_watch_history`

详细结构请查看 [DATABASE_STRUCTURE.md](doc/DATABASE_STRUCTURE.md)

## 🎓 推荐算法说明

### 1. 基于用户的协同过滤 (User-Based CF)

- 使用 KNN 算法找到相似用户
- 基于相似用户的评分进行推荐
- 适合用户群体稳定的场景

### 2. 基于物品的协同过滤 (Item-Based CF)

- 计算电影之间的相似度
- 考虑多个维度：导演、演员、类型、年份
- 推荐与用户喜欢的电影相似的作品

### 3. 基于内容的推荐 (Content-Based)

- 使用 TF-IDF 向量化电影特征
- 计算余弦相似度
- 适合有丰富电影元数据的场景

### 4. 基于知识的推荐 (Knowledge-Based)

- 处理冷启动问题
- 基于用户的类型偏好
- 结合热度和评分综合推荐

## 🔧 配置说明

### 开发环境配置

```python
# config.py
class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
```

### 生产环境配置

```python
class ProductionConfig(Config):
    DEBUG = False
    # 从环境变量读取敏感配置
```

详细部署说明请查看 [DEPLOYMENT.md](doc/DEPLOYMENT.md)

## 🧪 测试

```bash
# 运行单元测试（待实现）
pytest tests/

# 生成测试数据
python scripts/add_realistic_ratings.py
```

## 🤝 贡献指南

欢迎贡献代码！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与项目开发。

### 贡献流程

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📝 开发路线图

- [x] 基础推荐算法实现
- [x] 用户认证和授权
- [x] 评论和点赞功能
- [x] 管理员后台
- [x] RESTful API
- [ ] 单元测试和集成测试
- [ ] Docker 容器化部署
- [ ] 推荐算法性能优化
- [ ] 实时推荐系统
- [ ] 前后端分离版本（Vue.js）
- [ ] 移动端 App

## 🐛 已知问题

- 大量用户同时访问时推荐系统响应较慢（建议添加缓存）
- 新电影冷启动推荐效果有待提升
- 部分页面在低版本浏览器兼容性问题

## 📄 开源许可

本项目采用 [MIT License](LICENSE) 开源许可证。

## 👥 作者

- **Your Name** - *Initial work* - [YourGitHub](https://github.com/yourusername)

## 🙏 致谢

- [TMDB](https://www.themoviedb.org/) - 提供电影数据 API
- [Flask](https://flask.palletsprojects.com/) - Web 框架
- [Scikit-learn](https://scikit-learn.org/) - 机器学习库

## 📞 联系方式

- 项目主页: https://github.com/yourusername/movies-recommend
- 问题反馈: https://github.com/yourusername/movies-recommend/issues
- 邮箱: your.email@example.com

## ⭐ Star History

如果这个项目对您有帮助，请给个 Star ⭐

[![Star History Chart](https://api.star-history.com/svg?repos=yourusername/movies-recommend&type=Date)](https://star-history.com/#yourusername/movies-recommend&Date)

---

**注意**: 这是一个开源学习项目，不建议直接用于生产环境，请根据实际需求进行安全加固和性能优化。
