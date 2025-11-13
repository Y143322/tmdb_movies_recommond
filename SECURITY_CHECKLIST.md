# 🔒 上传 GitHub 前的安全检查清单

## ⚠️ 必须完成的安全措施

### 1. 检查是否存在 `.env` 文件
```powershell
# 在项目根目录运行
Get-ChildItem -Filter ".env" -Recurse
```

如果存在 `.env` 文件：
- ✅ 确认它已在 `.gitignore` 中（已配置）
- ✅ 检查是否已被 Git 追踪：`git ls-files | Select-String ".env"`
- ⚠️ 如果已被追踪，需要移除：`git rm --cached .env`

### 2. 检查 Git 历史中是否有敏感信息
```powershell
# 搜索可能的敏感信息
git log --all --full-history --source --all -- .env
git log -S "TMDB_API_KEY" --all
git log -S "SECRET_KEY" --all
```

如果发现历史记录中有敏感信息：
```powershell
# 使用 BFG Repo-Cleaner 清理（推荐）
# 下载：https://rtyley.github.io/bfg-repo-cleaner/

java -jar bfg.jar --delete-files .env
java -jar bfg.jar --replace-text passwords.txt  # 创建包含要替换密码的文本文件
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 3. 创建并配置 `.env` 文件（本地使用）

**⚠️ 不要上传此文件到 GitHub！**

```bash
# 复制示例文件
copy .env.example .env

# 然后编辑 .env 文件，填入您的真实配置：
# - TMDB_API_KEY=你的真实API密钥
# - SECRET_KEY=你的真实密钥
# - DB_PASSWORD=你的真实数据库密码
# 等等...
```

### 4. 验证 `.gitignore` 配置

确认以下内容已在 `.gitignore` 中：
- ✅ `.env`
- ✅ `.env.local`
- ✅ `*.log`
- ✅ `__pycache__/`
- ✅ `instance/`
- ✅ `scheduler.db`

### 5. 代码安全检查

已完成的改进：
- ✅ `config.py` 已移除硬编码的敏感默认值
- ✅ 生产环境配置强制要求设置环境变量
- ✅ 开发环境配置使用明确标记的开发默认值
- ✅ TMDB API 密钥只从环境变量读取

### 6. 上传前最后检查

```powershell
# 查看即将提交的文件
git status

# 查看具体更改内容
git diff

# 搜索可能遗漏的敏感信息
Select-String -Pattern "api.*key|password|secret" -Path * -Exclude *.md,*.example -Recurse
```

### 7. 首次推送到 GitHub

```powershell
# 初始化 Git（如果未初始化）
git init

# 添加所有文件
git add .

# 提交
git commit -m "Initial commit: Movie recommendation system"

# 创建 GitHub 仓库后，添加远程仓库
git remote add origin https://github.com/YOUR_USERNAME/movies_recommend.git

# 推送到 GitHub
git branch -M main
git push -u origin main
```

## 📋 环境变量清单

### 必须设置的环境变量（生产环境）：
- `SECRET_KEY` - Flask 密钥
- `JWT_SECRET_KEY` - JWT 密钥  
- `DB_PASSWORD` - 数据库密码
- `ADMIN_VERIFICATION_CODE` - 管理员验证码

### 可选环境变量：
- `TMDB_API_KEY` - TMDB API 密钥（如需爬取电影数据）
- `DB_HOST` - 数据库主机（默认：localhost）
- `DB_USER` - 数据库用户（默认：root）
- `DB_NAME` - 数据库名称（默认：movies_recommend）
- `DEFAULT_PASSWORD` - 默认密码（开发环境）

## 🔐 生成安全的密钥

使用 Python 生成随机密钥：
```python
import secrets

# 生成 SECRET_KEY
print(f"SECRET_KEY={secrets.token_urlsafe(32)}")

# 生成 JWT_SECRET_KEY
print(f"JWT_SECRET_KEY={secrets.token_urlsafe(32)}")

# 生成管理员验证码
print(f"ADMIN_VERIFICATION_CODE={secrets.token_urlsafe(16)}")
```

## ⚠️ 重要提醒

1. **永远不要**将 `.env` 文件提交到 Git
2. **永远不要**在代码中硬编码密码、API 密钥等敏感信息
3. **定期更换**生产环境的密钥和密码
4. **使用不同的密钥**用于开发和生产环境
5. **备份**您的 `.env` 文件到安全的地方（不是 GitHub）

## 📚 参考文档

- `.env.example` - 环境变量配置示例
- `doc/DEPLOYMENT_WINDOWS.md` - Windows 部署指南（包含环境变量配置）
- `CONTRIBUTING.md` - 贡献指南

---

✅ **完成以上所有检查后，您的项目就可以安全地上传到 GitHub 了！**
