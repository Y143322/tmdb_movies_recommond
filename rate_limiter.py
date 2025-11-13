#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TMDB API 速率限制器
用于控制API请求频率，避免超过TMDB的速率限制（50次请求/分钟）
"""

import time
import threading
from collections import deque
import logging

# 获取日志记录器
logger = logging.getLogger('tmdb_rate_limiter')

class RateLimiter:
    """
    速率限制器类
    实现令牌桶算法控制请求频率
    """
    
    def __init__(self, requests_per_minute=50, safety_factor=0.9):
        """
        初始化速率限制器
        
        Args:
            requests_per_minute: 每分钟允许的请求数量
            safety_factor: 安全系数，实际使用的速率将乘以此系数，防止超限
        """
        self.max_requests = requests_per_minute
        self.safety_factor = safety_factor
        self.effective_rate = requests_per_minute * safety_factor
        
        # 计算平均请求间隔时间（秒）
        self.interval = 60.0 / self.effective_rate
        
        # 用于存储最近请求时间的队列
        self.request_times = deque(maxlen=int(self.max_requests))
        
        # 线程锁，确保线程安全
        self.lock = threading.Lock()
        
        logger.info(f"初始化速率限制器: {self.effective_rate:.2f} 请求/分钟, 间隔: {self.interval:.4f} 秒")
    
    def acquire(self):
        """
        获取请求许可，必要时等待
        """
        with self.lock:
            current_time = time.time()
            
            # 如果请求队列已满，检查第一个请求是否已过期
            if len(self.request_times) >= self.max_requests:
                oldest_request = self.request_times[0]
                time_since_oldest = current_time - oldest_request
                
                # 如果最早的请求不到一分钟，需要等待
                if time_since_oldest < 60:
                    # 计算需要等待的时间
                    wait_time = max(0, 60 - time_since_oldest)
                    logger.debug(f"达到速率限制，等待 {wait_time:.2f} 秒")
                    time.sleep(wait_time)
                    # 重新获取当前时间
                    current_time = time.time()
            
            # 即使队列未满，也要保证最小间隔
            if self.request_times and current_time - self.request_times[-1] < self.interval:
                wait_time = self.interval - (current_time - self.request_times[-1])
                logger.debug(f"保持间隔，等待 {wait_time:.4f} 秒")
                time.sleep(wait_time)
                current_time = time.time()
            
            # 添加当前请求时间到队列
            self.request_times.append(current_time)
            
            # 如果队列已满，移除最早的请求（虽然deque设置了maxlen，但为了逻辑清晰，显式处理）
            if len(self.request_times) > self.max_requests:
                self.request_times.popleft()
    
    def get_current_status(self):
        """
        获取当前速率限制状态
        
        Returns:
            dict: 包含当前状态信息的字典
        """
        with self.lock:
            current_time = time.time()
            queue_size = len(self.request_times)
            
            # 计算一分钟内的请求数
            requests_in_last_minute = sum(1 for t in self.request_times if current_time - t < 60)
            
            # 计算可用请求数
            available_requests = self.max_requests - requests_in_last_minute
            
            return {
                "total_limit": self.max_requests,
                "effective_rate": self.effective_rate,
                "queue_size": queue_size,
                "requests_in_last_minute": requests_in_last_minute,
                "available_requests": available_requests,
                "interval": self.interval
            }


# 创建全局速率限制器实例
tmdb_limiter = RateLimiter(requests_per_minute=50, safety_factor=0.9)

def acquire_api_request():
    """
    在发送API请求前调用此函数，控制请求速率
    """
    tmdb_limiter.acquire()

def get_rate_limit_status():
    """
    获取当前速率限制状态
    
    Returns:
        dict: 当前状态信息
    """
    return tmdb_limiter.get_current_status()
