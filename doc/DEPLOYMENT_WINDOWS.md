# Windows 部署指南

本文档介绍如何在 Windows 系统上部署电影推荐系统。

## 📋 目录

- [系统要求](#系统要求)
- [环境准备](#环境准备)
- [安装步骤](#安装步骤)
- [配置说明](#配置说明)
- [启动应用](#启动应用)
- [开机自启动](#开机自启动)
- [性能优化](#性能优化)
- [故障排查](#故障排查)
- [更新部署](#更新部署)

---

## 系统要求

### 硬件要求
- **CPU**: 双核或更多
- **内存**: 4GB 或更多（推荐 8GB）
- **磁盘**: 10GB 可用空间
- **操作系统**: Windows 10/11 或 Windows Server 2016+

### 软件要求
- **Python**: 3.8 或更高版本
- **MySQL**: 8.0 或更高版本
- **浏览器**: Chrome、Edge、Firefox 等现代浏览器

---

## 环境准备

### 1. 安装 Python

#### 方式一：从官网下载

1. 访问 [Python 官网](https://www.python.org/downloads/)
2. 下载 Python 3.10 或更高版本
3. 运行安装程序，**重要**：勾选 "Add Python to PATH"
4. 验证安装：

```powershell
python --version
# 输出: Python 3.10.x
```

#### 方式二：使用 Microsoft Store

1. 打开 Microsoft Store
2. 搜索 "Python 3.10"
3. 点击安装
4. 验证安装

### 2. 安装 MySQL

#### 下载安装

1. 访问 [MySQL 官网](https://dev.mysql.com/downloads/installer/)
2. 下载 MySQL Installer for Windows
3. 运行安装程序，选择 "Developer Default"
4. 设置 root 密码（请记住此密码）
5. 完成安装

#### 启动 MySQL 服务

```powershell
# 检查 MySQL 服务状态
Get-Service -Name MySQL80

# 启动 MySQL 服务
Start-Service -Name MySQL80

# 设置开机自启动
Set-Service -Name MySQL80 -StartupType Automatic
```

#### 验证安装

```powershell
# 登录 MySQL
mysql -u root -p
# 输入密码后应该能成功登录
```

### 3. 安装 Git（可选，用于克隆项目）

1. 访问 [Git 官网](https://git-scm.com/download/win)
2. 下载并安装 Git for Windows
3. 验证安装：

```powershell
git --version
```

---

## 安装步骤

### 1. 获取项目代码

#### 方式一：使用 Git 克隆

```powershell
# 克隆项目到指定目录
cd D:\Projects
git clone https://github.com/yourusername/movies-recommend.git
cd movies-recommend
```

#### 方式二：下载 ZIP 文件

1. 访问项目 GitHub 页面
2. 点击 "Code" -> "Download ZIP"
3. 解压到目标目录，例如 `D:\Projects\movies-recommend`

### 2. 创建虚拟环境

```powershell
# 进入项目目录
cd D:\Projects\movies-recommend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate

# 激活后，命令提示符前会显示 (venv)
```

### 3. 安装 Python 依赖

```powershell
# 确保虚拟环境已激活
pip install --upgrade pip

# 安装项目依赖
pip install -r requirements.txt

# 验证安装
pip list
```

**常见问题**：
- 如果遇到网络问题，可以使用国内镜像源：
  ```powershell
  pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  ```

### 4. 配置环境变量

```powershell
# 复制环境变量模板
copy .env.example .env

# 使用记事本编辑 .env 文件
notepad .env
```

修改 `.env` 文件中的配置：

```env
# Flask 配置
FLASK_ENV=production
SECRET_KEY=your-secret-key-change-this
DEBUG=False

# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=movies_recommend

# JWT 配置
JWT_SECRET_KEY=your-jwt-secret-key

# 管理员验证码
ADMIN_VERIFICATION_CODE=your-admin-code
```

**生成随机密钥**：
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. 初始化数据库

```powershell
# 运行数据库初始化脚本
python scripts\init_database.py
```

如果成功，会看到：
```
✓ MySQL 连接成功
✓ 数据库 'movies_recommend' 已创建
✓ 成功执行 XX 条 SQL 语句
✓ 成功创建 23 张表
✓ 数据库初始化完成!
```

### 6. 测试运行

```powershell
# 运行应用（开发模式）
python app.py
```

访问 http://localhost:5000 测试是否正常运行。

按 `Ctrl+C` 停止应用。

---

## 配置说明

### 修改运行端口

编辑 `app.py` 文件，找到最后的启动代码：

```python
if __name__ == '__main__':
    app = create_app('production')
    app.run(host='0.0.0.0', port=5000)  # 修改这里的端口号
```

### 配置防火墙

如果需要外部访问，需要开放端口：

```powershell
# 以管理员身份运行 PowerShell
# 添加防火墙规则允许 5000 端口
New-NetFirewallRule -DisplayName "Movie Recommend System" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

### MySQL 性能优化

编辑 MySQL 配置文件 `my.ini`（通常在 `C:\ProgramData\MySQL\MySQL Server 8.0\` 目录）：

```ini
[mysqld]
# 基本配置
max_connections = 200
max_allowed_packet = 64M

# InnoDB 配置
innodb_buffer_pool_size = 1G
innodb_log_file_size = 256M

# 字符集
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
```

重启 MySQL 服务：
```powershell
Restart-Service -Name MySQL80
```

---

## 启动应用

### 方式一：使用 Python 直接运行（开发/测试）

```powershell
# 激活虚拟环境
cd D:\Projects\movies-recommend
.\venv\Scripts\activate

# 运行应用
python app.py
```

### 方式二：使用 waitress 生产服务器

安装 waitress：
```powershell
pip install waitress
```

创建启动脚本 `start_server.py`：

```python
from waitress import serve
from app import create_app

if __name__ == '__main__':
    app = create_app('production')
    print("启动服务器在 http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=5000, threads=4)
```

运行：
```powershell
python start_server.py
```

### 方式三：创建批处理文件

创建 `start.bat` 文件：

```batch
@echo off
echo 启动电影推荐系统...
cd /d D:\Projects\movies-recommend
call venv\Scripts\activate.bat
python start_server.py
pause
```

双击 `start.bat` 即可启动应用。

---

## 开机自启动

### 方式一：使用任务计划程序

1. 打开"任务计划程序"（按 `Win+R`，输入 `taskschd.msc`）
2. 点击右侧"创建基本任务"
3. 名称：`电影推荐系统`
4. 触发器：选择"当计算机启动时"
5. 操作：选择"启动程序"
6. 程序：`D:\Projects\movies-recommend\venv\Scripts\python.exe`
7. 参数：`D:\Projects\movies-recommend\start_server.py`
8. 起始于：`D:\Projects\movies-recommend`
9. 完成

### 方式二：使用 NSSM（推荐）

NSSM 是一个可以将应用程序注册为 Windows 服务的工具。

#### 下载 NSSM

1. 访问 [NSSM 官网](https://nssm.cc/download)
2. 下载并解压
3. 将 `nssm.exe` 复制到 `C:\Windows\System32\`

#### 安装服务

```powershell
# 以管理员身份运行 PowerShell
cd C:\Windows\System32

# 安装服务
nssm install MoviesRecommend

# 会弹出配置窗口，填写：
# Path: D:\Projects\movies-recommend\venv\Scripts\python.exe
# Startup directory: D:\Projects\movies-recommend
# Arguments: start_server.py
```

#### 管理服务

```powershell
# 启动服务
nssm start MoviesRecommend

# 停止服务
nssm stop MoviesRecommend

# 重启服务
nssm restart MoviesRecommend

# 查看状态
nssm status MoviesRecommend

# 删除服务
nssm remove MoviesRecommend confirm
```

### 方式三：使用启动文件夹

1. 按 `Win+R`，输入 `shell:startup`
2. 将 `start.bat` 的快捷方式复制到打开的文件夹
3. 重启电脑测试

---

## 性能优化

### 1. 启用生产模式

确保 `.env` 文件中：
```env
FLASK_ENV=production
DEBUG=False
```

### 2. 配置 Waitress 多线程

编辑 `start_server.py`：

```python
serve(app, 
      host='0.0.0.0', 
      port=5000, 
      threads=8,           # 增加线程数
      channel_timeout=120,
      cleanup_interval=30,
      connection_limit=1000)
```

### 3. 定期清理日志

创建 `cleanup_logs.bat`：

```batch
@echo off
echo 清理旧日志文件...
cd /d D:\Projects\movies-recommend\logs
forfiles /p . /s /m *.log /d -7 /c "cmd /c del @path"
echo 清理完成
```

添加到任务计划程序，每周执行一次。

### 4. 数据库定期备份

创建 `backup_database.bat`：

```batch
@echo off
set BACKUP_DIR=D:\Backups\movies_recommend
set DATE=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set DATE=%DATE: =0%

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

mysqldump -u root -p你的密码 movies_recommend > "%BACKUP_DIR%\backup_%DATE%.sql"

echo 备份完成: %BACKUP_DIR%\backup_%DATE%.sql

REM 删除 7 天前的备份
forfiles /p "%BACKUP_DIR%" /s /m *.sql /d -7 /c "cmd /c del @path"
```

添加到任务计划程序，每天执行。

---

## 故障排查

### 问题 1: 应用无法启动

**检查项**：
```powershell
# 1. 检查 Python 是否正确安装
python --version

# 2. 检查虚拟环境是否激活
# 命令提示符应该显示 (venv)

# 3. 检查依赖是否安装
pip list | findstr Flask

# 4. 查看错误日志
type logs\app.log
```

### 问题 2: 数据库连接失败

**检查项**：
```powershell
# 1. 检查 MySQL 服务是否运行
Get-Service -Name MySQL80

# 2. 测试数据库连接
mysql -u root -p -e "SELECT 1"

# 3. 检查 .env 配置
type .env | findstr DB_

# 4. 检查防火墙
Test-NetConnection -ComputerName localhost -Port 3306
```

### 问题 3: 端口被占用

```powershell
# 查看 5000 端口占用情况
netstat -ano | findstr :5000

# 如果被占用，找到 PID 后结束进程
taskkill /PID <进程ID> /F

# 或者修改应用端口
```

### 问题 4: 虚拟环境激活失败

如果遇到执行策略限制：

```powershell
# 以管理员身份运行 PowerShell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 然后重新激活虚拟环境
.\venv\Scripts\activate
```

### 问题 5: 依赖包安装失败

```powershell
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 如果特定包失败，单独安装
pip install 包名 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 更新部署

### 更新代码

```powershell
# 停止应用
# 如果使用 NSSM
nssm stop MoviesRecommend

# 备份数据库
mysqldump -u root -p密码 movies_recommend > backup_before_update.sql

# 进入项目目录
cd D:\Projects\movies-recommend

# 拉取最新代码（如果使用 Git）
git pull origin main

# 激活虚拟环境
.\venv\Scripts\activate

# 更新依赖
pip install -r requirements.txt --upgrade

# 重启应用
nssm start MoviesRecommend
```

### 数据库迁移

如果有数据库结构变更：

```powershell
# 备份当前数据库
mysqldump -u root -p movies_recommend > backup.sql

# 运行新的 SQL 脚本（如果有）
mysql -u root -p movies_recommend < doc\update.sql
```

---

## 访问应用

### 本地访问
```
http://localhost:5000
```

### 局域网访问
```
http://你的电脑IP:5000
```

查看本机 IP：
```powershell
ipconfig | findstr IPv4
```

### 外网访问

如需外网访问，建议：
1. 配置路由器端口转发
2. 使用内网穿透工具（如 ngrok、frp）
3. 部署到云服务器

---

## 监控和日志

### 查看应用日志

```powershell
# 实时查看日志（需要安装 tail）
Get-Content logs\app.log -Wait

# 或使用记事本打开
notepad logs\app.log
```

### 监控系统资源

```powershell
# 查看 Python 进程资源占用
Get-Process python | Select-Object Name, CPU, WorkingSet

# 查看 MySQL 资源占用
Get-Process mysqld | Select-Object Name, CPU, WorkingSet
```

### 性能监控

使用 Windows 性能监视器：
1. 按 `Win+R`，输入 `perfmon`
2. 添加计数器监控 CPU、内存、磁盘、网络

---

## 安全建议

### 1. 修改默认密码
- 修改 MySQL root 密码
- 修改 `.env` 中的所有密钥
- 修改管理员验证码

### 2. 限制访问
```powershell
# 只允许特定 IP 访问（防火墙规则）
New-NetFirewallRule -DisplayName "Movie Recommend - Specific IP" `
    -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow `
    -RemoteAddress "192.168.1.0/24"
```

### 3. 定期更新
- 定期更新 Python 和依赖包
- 定期更新 MySQL
- 定期更新 Windows 系统

### 4. 启用 HTTPS（进阶）
使用自签名证书或 Let's Encrypt（需要域名）

---

## 常用命令速查

```powershell
# 启动应用
cd D:\Projects\movies-recommend
.\venv\Scripts\activate
python start_server.py

# 停止应用（按 Ctrl+C）

# 查看日志
Get-Content logs\app.log -Tail 50

# 备份数据库
mysqldump -u root -p movies_recommend > backup.sql

# 恢复数据库
mysql -u root -p movies_recommend < backup.sql

# 查看端口占用
netstat -ano | findstr :5000

# 重启 MySQL
Restart-Service MySQL80

# 检查 Python 版本
python --version

# 检查依赖
pip list
```

---

## 技术支持

如遇到问题：
1. 查看项目 [Issues](https://github.com/yourusername/movies-recommend/issues)
2. 查看 [FAQ](doc/FAQ.md)
3. 联系项目维护者

---

**祝您部署顺利！** 🎉

如有问题，欢迎反馈。
