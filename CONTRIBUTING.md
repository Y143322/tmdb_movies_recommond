# 贡献指南 (Contributing Guide)

感谢您对电影推荐系统项目的关注！我们欢迎所有形式的贡献。

## 📋 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
- [开发流程](#开发流程)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [测试要求](#测试要求)
- [文档贡献](#文档贡献)

---

## 行为准则

### 我们的承诺

为了营造一个开放和友好的环境，我们承诺：

- ✅ 尊重不同的观点和经验
- ✅ 优雅地接受建设性批评
- ✅ 关注什么对社区最有利
- ✅ 对其他社区成员表现出同理心

### 不可接受的行为

- ❌ 使用性化的语言或图像
- ❌ 人身攻击或政治攻击
- ❌ 公开或私下骚扰
- ❌ 未经明确许可发布他人的私人信息

---

## 如何贡献

### 🐛 报告 Bug

如果您发现了 Bug，请：

1. **检查** [Issues](https://github.com/yourusername/movies-recommend/issues) 是否已有人报告
2. 如果没有，创建新 Issue，包含：
   - 清晰的标题
   - Bug 的详细描述
   - 复现步骤
   - 预期行为 vs 实际行为
   - 系统环境（操作系统、Python 版本等）
   - 相关截图或日志

**Bug 报告模板：**

```markdown
**Bug 描述**
简洁清晰的 Bug 描述

**复现步骤**
1. 访问 '...'
2. 点击 '....'
3. 滚动到 '....'
4. 看到错误

**预期行为**
应该发生什么

**截图**
如果适用，添加截图

**环境：**
 - OS: [e.g. Ubuntu 20.04]
 - Python: [e.g. 3.10]
 - 浏览器: [e.g. Chrome 90]
```

### 💡 提出新功能

如果您有新想法：

1. **搜索** 是否已有相关 Issue
2. 创建 Feature Request，说明：
   - 功能的动机和目的
   - 详细的功能描述
   - 可能的实现方案
   - 相关的参考资料

### 📝 改进文档

文档贡献同样重要！您可以：

- 修正错别字或语法错误
- 改进说明的清晰度
- 添加示例代码
- 翻译文档到其他语言

---

## 开发流程

### 1. Fork 项目

点击页面右上角的 "Fork" 按钮，将项目 fork 到您的账户。

### 2. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/movies-recommend.git
cd movies-recommend
```

### 3. 创建分支

```bash
# 从 main 分支创建功能分支
git checkout -b feature/your-feature-name

# 或创建 bug 修复分支
git checkout -b fix/bug-description
```

分支命名规范：
- `feature/功能名称` - 新功能
- `fix/bug描述` - Bug 修复
- `docs/文档主题` - 文档更新
- `refactor/重构描述` - 代码重构
- `test/测试描述` - 测试相关

### 4. 设置开发环境

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件
```

### 5. 进行开发

```bash
# 保持代码同步
git fetch upstream
git merge upstream/main

# 进行您的修改
# ...

# 运行测试
pytest tests/

# 检查代码风格
flake8 .
black --check .
```

### 6. 提交更改

```bash
# 添加修改的文件
git add .

# 提交（遵循提交规范）
git commit -m "feat: 添加电影推荐缓存功能"

# 推送到您的 fork
git push origin feature/your-feature-name
```

### 7. 创建 Pull Request

1. 访问您 fork 的仓库页面
2. 点击 "New Pull Request"
3. 填写 PR 描述：
   - 更改的内容
   - 相关的 Issue
   - 测试情况
   - 截图（如适用）

---

## 代码规范

### Python 代码风格

遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 规范：

```python
# 好的示例
def get_movie_recommendations(user_id, limit=10):
    """获取用户的电影推荐
    
    Args:
        user_id (int): 用户ID
        limit (int): 推荐数量限制，默认10
        
    Returns:
        list: 推荐的电影列表
    """
    if not user_id:
        raise ValueError("用户ID不能为空")
    
    recommendations = recommender.get_recommendations(user_id, limit)
    return recommendations


# 不好的示例
def GetMovieRecs(uid,lmt=10):
    if not uid: raise ValueError("用户ID不能为空")
    recs=recommender.get_recommendations(uid,lmt)
    return recs
```

### 代码格式化

使用 [Black](https://github.com/psf/black) 自动格式化：

```bash
# 格式化所有文件
black .

# 检查但不修改
black --check .
```

### 代码检查

使用 [Flake8](https://flake8.pycqa.org/)：

```bash
flake8 . --max-line-length=100 --exclude=venv,__pycache__
```

### 文档字符串

使用 Google 风格的 docstring：

```python
def calculate_similarity(movie1_id, movie2_id):
    """计算两部电影的相似度
    
    基于多个维度（导演、演员、类型等）计算电影之间的相似度分数。
    
    Args:
        movie1_id (int): 第一部电影的ID
        movie2_id (int): 第二部电影的ID
        
    Returns:
        float: 相似度分数，范围 0-1
        
    Raises:
        ValueError: 如果电影ID不存在
        
    Example:
        >>> similarity = calculate_similarity(123, 456)
        >>> print(f"相似度: {similarity:.2f}")
        相似度: 0.85
    """
    pass
```

---

## 提交规范

### Commit Message 格式

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

```
<类型>(<范围>): <描述>

[可选的正文]

[可选的脚注]
```

### 类型 (Type)

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 仅文档更改
- `style`: 不影响代码含义的更改（空格、格式化等）
- `refactor`: 既不修复 bug 也不添加功能的代码更改
- `perf`: 提高性能的代码更改
- `test`: 添加缺失的测试或更正现有测试
- `build`: 影响构建系统或外部依赖的更改
- `ci`: CI 配置文件和脚本的更改
- `chore`: 其他不修改 src 或测试文件的更改

### 示例

```bash
# 添加新功能
git commit -m "feat(recommender): 添加基于协同过滤的推荐算法"

# 修复 Bug
git commit -m "fix(auth): 修复用户登录时的密码验证问题"

# 更新文档
git commit -m "docs(readme): 更新安装说明和依赖列表"

# 性能优化
git commit -m "perf(database): 优化电影查询的数据库索引"

# 带正文的提交
git commit -m "feat(api): 添加电影搜索API

- 实现关键词搜索功能
- 支持分页和排序
- 添加搜索结果缓存

Closes #123"
```

---

## 测试要求

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_recommender.py

# 运行特定测试函数
pytest tests/test_recommender.py::test_get_recommendations

# 查看测试覆盖率
pytest --cov=movies_recommend tests/
```

### 编写测试

为新功能添加测试：

```python
# tests/test_recommender.py
import pytest
from movies_recommend.recommender import get_recommendations_for_user

def test_get_recommendations_returns_list():
    """测试推荐函数返回列表"""
    result = get_recommendations_for_user(user_id=1, n=5)
    assert isinstance(result, list)
    assert len(result) <= 5

def test_get_recommendations_with_invalid_user():
    """测试无效用户ID时的错误处理"""
    with pytest.raises(ValueError):
        get_recommendations_for_user(user_id=-1)
```

---

## 文档贡献

### 文档结构

```
doc/
├── README.md           # 项目主文档
├── API.md              # API 文档
├── DEPLOYMENT.md       # 部署指南
├── DATABASE_STRUCTURE.md  # 数据库结构
└── CONTRIBUTING.md     # 本文件
```

### 文档风格

- 使用清晰的标题层级
- 添加代码示例
- 包含必要的截图
- 使用表格和列表提高可读性
- 保持语言简洁明了

---

## Pull Request 检查清单

在提交 PR 前，请确认：

- [ ] 代码遵循项目的代码规范
- [ ] 已添加必要的测试，且所有测试通过
- [ ] 已更新相关文档
- [ ] Commit message 遵循提交规范
- [ ] 没有不必要的调试代码或注释
- [ ] 没有合并冲突
- [ ] 已在本地测试过所有更改

---

## 代码审查

### 审查流程

1. 项目维护者会审查您的 PR
2. 可能会提出修改建议
3. 根据反馈进行调整
4. 审查通过后会合并到主分支

### 响应时间

- 我们会尽快审查 PR（通常 1-3 天）
- 如有疑问，可以在 PR 中评论

---

## 获取帮助

### 问题讨论

- 💬 [GitHub Discussions](https://github.com/yourusername/movies-recommend/discussions)
- 🐛 [GitHub Issues](https://github.com/yourusername/movies-recommend/issues)

### 联系方式

- 📧 Email: your.email@example.com
- 💬 WeChat: your-wechat-id

---

## 感谢

感谢所有为项目做出贡献的开发者！

[![Contributors](https://contrib.rocks/image?repo=yourusername/movies-recommend)](https://github.com/yourusername/movies-recommend/graphs/contributors)

---

## 许可证

通过贡献代码，您同意您的贡献将遵循本项目的 [MIT License](../LICENSE)。
