"""
Windows 生产环境启动脚本
使用 waitress WSGI 服务器
"""
from waitress import serve
from app import create_app
import os

def main():
    # 创建应用实例
    app = create_app('production')
    
    # 从环境变量读取配置，或使用默认值
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', 5000))
    threads = int(os.getenv('THREADS', 8))
    
    print("=" * 60)
    print("电影推荐系统 - 生产服务器")
    print("=" * 60)
    print(f"服务器地址: http://{host}:{port}")
    print(f"线程数: {threads}")
    print(f"环境: {app.config.get('ENV', 'production')}")
    print("=" * 60)
    print("按 Ctrl+C 停止服务器")
    print()
    
    # 启动服务器
    serve(
        app,
        host=host,
        port=port,
        threads=threads,
        channel_timeout=120,
        cleanup_interval=30,
        connection_limit=1000,
        asyncore_use_poll=True
    )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n服务器已停止")
    except Exception as e:
        print(f"\n\n启动失败: {e}")
        import traceback
        traceback.print_exc()
