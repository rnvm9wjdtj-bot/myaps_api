# gunicorn.conf.py
import os
import multiprocessing

# 进程数
workers = min(multiprocessing.cpu_count(), 4)
worker_class = "uvicorn.workers.UvicornWorker"
bind = "127.0.0.1:8000"
timeout = 30

# 日志配置
accesslog = "logs/access.log"
errorlog = "logs/error.log"
loglevel = "info"

# 确保日志目录存在
if not os.path.exists("logs"):
    os.makedirs("logs")