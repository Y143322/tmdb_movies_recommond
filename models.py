import os
import sys
# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask_login import UserMixin
import datetime

class User(UserMixin):
    """用户模型，用于Flask-Login"""

    def __init__(self, id, username, email=None, is_admin=False, reset_password=False, 
                 mute_expires_at=None, status='active'):
        self.id = id
        self.username = username
        self.email = email
        self.is_admin = is_admin
        self.reset_password = reset_password
        self.mute_expires_at = mute_expires_at
        self.status = status

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.status != 'deleted'
        
    @property
    def is_banned(self):
        return self.status == 'banned'
        
    @property
    def is_currently_muted(self):
        """检查用户当前是否处于禁言状态"""
        if self.status != 'banned':
            return False
            
        # 如果没有设置禁言到期时间，则视为永久禁言
        if not self.mute_expires_at:
            return True
            
        # 判断禁言是否已过期
        return self.mute_expires_at > datetime.datetime.now()
        
    def get_mute_remaining_time(self):
        """获取禁言剩余时间"""
        if not self.is_currently_muted or not self.mute_expires_at:
            return None
            
        time_left = self.mute_expires_at - datetime.datetime.now()
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        
        return f"{hours}小时{minutes}分钟"