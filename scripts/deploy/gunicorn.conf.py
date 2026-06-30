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

# === Binlog 监听器控制 ===
# Gunicorn 对子进程无直接暴露 worker_id 给 FastAPI lifespan 的方法，
# 因此通过 post_fork 注入环境变量，供 lifespan.py 判断当前进程是否为 Gunicorn 环境。
# 
# 新版 Gunicorn 的 UvicornWorker 没有 wid 属性，改用文件锁协调
# 哪个 Worker 负责 Binlog 监听，确保全局只有一个实例。

_BINLOG_LOCK_FILE = "/tmp/.myaps_binlog_lock"

def post_fork(server, worker):
    """Worker fork 后立即注入进程标识，供应用代码感知 Gunicorn 环境"""
    os.environ['GUNICORN_RUNNING'] = 'true'
    os.environ['GUNICORN_WORKER_ID'] = str(worker.pid)

def post_worker_init(worker):
    """Worker 初始化完成后执行：通过文件锁确保只有一个 Worker 启动 Binlog 监听"""
    try:
        fd = os.open(_BINLOG_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, 'w') as f:
            f.write(str(os.getpid()))
        from apps.data_opt.utils.binlog_listener import binlog_listener
        binlog_listener.start_monitoring()
    except FileExistsError:
        pass  # 其他 Worker 已启动 Binlog 监听

def worker_exit(server, worker):
    """Worker 退出时执行：持有锁的 Worker 退出时停止 Binlog 监听"""
    if not os.path.exists(_BINLOG_LOCK_FILE):
        return
    try:
        with open(_BINLOG_LOCK_FILE, 'r') as f:
            started_pid = f.read().strip()
    except (FileNotFoundError, OSError):
        return
    if started_pid == str(os.getpid()):
        from apps.data_opt.utils.binlog_listener import binlog_listener
        binlog_listener.stop_monitoring()
        try:
            os.unlink(_BINLOG_LOCK_FILE)
        except FileNotFoundError:
            pass