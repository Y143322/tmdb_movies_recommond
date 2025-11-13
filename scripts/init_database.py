#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
数据库初始化脚本
自动创建数据库和表结构
"""

import os
import sys
import pymysql
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def load_env_config():
    """从 .env 文件加载配置"""
    env_file = Path(__file__).parent.parent / '.env'
    config = {
        'host': 'localhost',
        'user': 'root',
        'password': 'root',
        'database': 'movies_recommend'
    }
    
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key == 'DB_HOST':
                        config['host'] = value
                    elif key == 'DB_USER':
                        config['user'] = value
                    elif key == 'DB_PASSWORD':
                        config['password'] = value
                    elif key == 'DB_NAME':
                        config['database'] = value
    
    return config

def test_connection(host, user, password):
    """测试 MySQL 连接"""
    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            charset='utf8mb4'
        )
        conn.close()
        print("✓ MySQL 连接成功")
        return True
    except Exception as e:
        print(f"✗ MySQL 连接失败: {e}")
        print("\n请检查:")
        print("1. MySQL 服务是否已启动")
        print("2. 用户名和密码是否正确")
        print("3. .env 文件配置是否正确")
        return False

def create_database(host, user, password, database):
    """创建数据库"""
    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # 创建数据库
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"✓ 数据库 '{database}' 已创建")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 创建数据库失败: {e}")
        return False

def execute_sql_file(host, user, password, database, sql_file):
    """执行 SQL 文件"""
    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        # 读取 SQL 文件
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割并执行 SQL 语句
        statements = sql_content.split(';')
        success_count = 0
        
        for statement in statements:
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                    success_count += 1
                except Exception as e:
                    # 忽略表已存在等警告
                    if 'already exists' not in str(e):
                        print(f"警告: {e}")
        
        conn.commit()
        print(f"✓ 成功执行 {success_count} 条 SQL 语句")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"✗ 执行 SQL 文件失败: {e}")
        return False

def verify_tables(host, user, password, database):
    """验证表是否创建成功"""
    try:
        conn = pymysql.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        cursor = conn.cursor()
        
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        if tables:
            print(f"\n✓ 成功创建 {len(tables)} 张表:")
            for table in tables:
                print(f"  - {table[0]}")
        else:
            print("\n✗ 未找到任何表")
        
        cursor.close()
        conn.close()
        return len(tables) > 0
    except Exception as e:
        print(f"✗ 验证表失败: {e}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("电影推荐系统 - 数据库初始化脚本")
    print("=" * 60)
    print()
    
    # 加载配置
    config = load_env_config()
    print(f"数据库配置:")
    print(f"  主机: {config['host']}")
    print(f"  用户: {config['user']}")
    print(f"  数据库: {config['database']}")
    print()
    
    # 测试连接
    print("步骤 1/4: 测试 MySQL 连接...")
    if not test_connection(config['host'], config['user'], config['password']):
        return
    print()
    
    # 创建数据库
    print("步骤 2/4: 创建数据库...")
    if not create_database(config['host'], config['user'], config['password'], config['database']):
        return
    print()
    
    # 执行 SQL 文件
    print("步骤 3/4: 创建数据表...")
    sql_file = Path(__file__).parent.parent / 'doc' / 'create_tables.sql'
    
    if not sql_file.exists():
        print(f"✗ SQL 文件不存在: {sql_file}")
        return
    
    if not execute_sql_file(config['host'], config['user'], config['password'], config['database'], sql_file):
        return
    print()
    
    # 验证表
    print("步骤 4/4: 验证表结构...")
    if not verify_tables(config['host'], config['user'], config['password'], config['database']):
        return
    
    print()
    print("=" * 60)
    print("✓ 数据库初始化完成!")
    print("=" * 60)
    print()
    print("下一步:")
    print("1. 运行应用: python app.py")
    print("2. 访问: http://localhost:5000")
    print("3. 注册账号开始使用")
    print()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
    except Exception as e:
        print(f"\n\n发生错误: {e}")
        import traceback
        traceback.print_exc()
