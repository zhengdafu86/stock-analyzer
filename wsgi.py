"""
PythonAnywhere WSGI 入口文件
"""
import sys
import os

# 项目路径（部署时按实际路径修改）
project_home = '/home/你的用户名/stock-analyzer'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['AI_PROVIDER'] = 'none'

from app import app as application
