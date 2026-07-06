# gunicorn.conf.py
import os
import multiprocessing

# 设置工作目录
# Docker环境下使用/app，否则基于脚本位置计算
# 配置文件路径: scripts/deploy/gunicorn.conf.py → 项目根目录需上3层
if os.path.exists('/app/main.py'):
    chdir = '/app'
else:
    chdir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 进程数：从环境变量读取，限制不超过CPU核心数，默认为1
cpu_count = multiprocessing.cpu_count()
env_workers = os.getenv("GUNICORN_WORKERS", "1")
try:
    workers = min(int(env_workers), cpu_count)
    if workers < 1:
        workers = 1
except ValueError:
    workers = 1
worker_class = "uvicorn.workers.UvicornWorker"
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")
timeout = int(os.getenv("GUNICORN_TIMEOUT", "360"))  # 默认360秒，可通过环境变量配置

# 日志配置
accesslog = os.path.join(chdir, "logs", "access.log")
errorlog = os.path.join(chdir, "logs", "error.log")
loglevel = "info"

# 确保日志目录存在
log_dir = os.path.join(chdir, "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# === Binlog 监听器控制 ===
# Gunicorn 对子进程无直接暴露 worker_id 给 FastAPI lifespan 的方法，
# 通过 post_fork 注入环境变量，供 lifespan.py 判断当前进程是否为 Gunicorn 环境。
# 
# Binlog 监听器的启动/停止由 lifespan 中的文件锁机制管理（见 core/lifespan.py），
# 而非 Gunicorn 钩子。这样做更加可靠，避免了对 UvicornWorker 与 Gunicorn 钩子
# 兼容性的依赖。

def on_starting(server):
    """Master 进程启动时设置标记"""
    os.environ['GUNICORN_MASTER_PID'] = str(os.getpid())

def post_fork(server, worker):
    """Worker fork 后立即注入进程标识，供应用代码感知 Gunicorn 环境"""
    os.environ['GUNICORN_RUNNING'] = 'true'
    os.environ['GUNICORN_WORKER_ID'] = str(worker.pid)
    os.environ['GUNICORN_WORKER_PID'] = str(os.getpid())
