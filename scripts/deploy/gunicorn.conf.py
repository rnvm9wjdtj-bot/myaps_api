# gunicorn.conf.py
import os
import multiprocessing

# 设置工作目录
# Docker环境下使用/app，否则基于脚本位置计算
if os.path.exists('/app/main.py'):
    chdir = '/app'
else:
    chdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 进程数
workers = min(multiprocessing.cpu_count(), 4)
worker_class = "uvicorn.workers.UvicornWorker"
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")
timeout = 30

# 日志配置
accesslog = os.path.join(chdir, "logs", "access.log")
errorlog = os.path.join(chdir, "logs", "error.log")
loglevel = "info"

# 确保日志目录存在
log_dir = os.path.join(chdir, "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)