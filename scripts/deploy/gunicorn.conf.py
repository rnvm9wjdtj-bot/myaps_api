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

# 日志配置 - 使用 logconfig_dict 配置 TimedRotatingFileHandler 实现按天轮转和自动清理
# 注意：gunicorn 的 accesslog/errorlog 仅接受文件路径字符串（validator 为 validate_string），
# 传 Handler 实例会导致启动时 TypeError，因此必须通过 logconfig_dict 配置自定义 handler。
log_dir = os.path.join(chdir, "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

_log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "7"))

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    # gunicorn 浅合并 CONFIG_DEFAULTS 后，root 默认引用 console handler，
    # 此处显式覆盖 root 为空 handler，避免引用不存在的 handler
    "root": {"level": "INFO", "handlers": []},
    "formatters": {
        # access 日志：gunicorn 已将 atoms 解析进 message，formatter 只需输出 message
        "access": {"()": "logging.Formatter", "fmt": "%(message)s"},
        "error": {"()": "logging.Formatter", "fmt": "[%(asctime)s] [%(levelname)s] %(message)s"},
    },
    "handlers": {
        "access_file": {
            "()": "logging.handlers.TimedRotatingFileHandler",
            "filename": os.path.join(log_dir, "access.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": _log_retention_days,
            "encoding": "utf-8",
            "formatter": "access",
        },
        "error_file": {
            "()": "logging.handlers.TimedRotatingFileHandler",
            "filename": os.path.join(log_dir, "error.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": _log_retention_days,
            "encoding": "utf-8",
            "formatter": "error",
        },
    },
    "loggers": {
        "gunicorn.access": {"handlers": ["access_file"], "level": "INFO", "propagate": False},
        "gunicorn.error": {"handlers": ["error_file"], "level": "INFO", "propagate": False},
    },
}

logconfig_dict = LOGGING_CONFIG

loglevel = "info"

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
