#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
生成安全的密钥和密码
用于配置环境变量
"""

import secrets
import string

def generate_secret_key(length=32):
    """生成 URL 安全的密钥"""
    return secrets.token_urlsafe(length)

def generate_password(length=16):
    """生成包含字母、数字和符号的强密码"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def main():
    print("=" * 60)
    print("🔐 生成安全配置")
    print("=" * 60)
    print()
    
    print("📋 将以下内容添加到您的 .env 文件中：")
    print()
    print("-" * 60)
    
    # Flask 密钥
    secret_key = generate_secret_key(32)
    print(f"# Flask 会话密钥")
    print(f"SECRET_KEY={secret_key}")
    print()
    
    # JWT 密钥
    jwt_secret = generate_secret_key(32)
    print(f"# JWT 认证密钥")
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print()
    
    # 管理员验证码
    admin_code = generate_secret_key(16)
    print(f"# 管理员验证码")
    print(f"ADMIN_VERIFICATION_CODE={admin_code}")
    print()
    
    # 数据库密码建议
    db_password = generate_password(16)
    print(f"# 数据库密码（建议）")
    print(f"DB_PASSWORD={db_password}")
    print()
    
    print("-" * 60)
    print()
    print("⚠️  重要提醒：")
    print("  1. 请将这些值保存到 .env 文件中")
    print("  2. 不要将 .env 文件上传到 GitHub")
    print("  3. 备份您的 .env 文件到安全的地方")
    print("  4. 生产环境和开发环境使用不同的密钥")
    print()
    print("=" * 60)

if __name__ == "__main__":
    main()
