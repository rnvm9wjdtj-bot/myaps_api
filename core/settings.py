# from tortoise import Tortoise

import os
from pathlib import Path
from dotenv import load_dotenv

# 先加载环境变量，确保 USE_LOGURU 在 logger 导入前就已设置
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env')), override=False)

from globalobjects.json_manager import JSONManager
from globalobjects import logger as log_config


logger = log_config.get_logger(__name__)



# 时区，默认东八区
TIMEZONE = os.getenv("TIMEZONE", "+8")

def get_timezone_name(offset_str):
    """
    将时区偏移量字符串（如 +8, -5）转换为时区名称（如 Asia/Shanghai）
    
    Args:
        offset_str: 时区偏移量字符串，格式为 "+8" 或 "-5"
    
    Returns:
        时区名称，如 "Asia/Shanghai"
    """
    offset_map = {
        "-12": "Etc/GMT+12",
        "-11": "Etc/GMT+11",
        "-10": "Pacific/Honolulu",
        "-9": "America/Anchorage",
        "-8": "America/Los_Angeles",
        "-7": "America/Denver",
        "-6": "America/Chicago",
        "-5": "America/New_York",
        "-4": "America/Halifax",
        "-3": "America/Argentina/Buenos_Aires",
        "-2": "Atlantic/South_Georgia",
        "-1": "Atlantic/Azores",
        "+0": "Europe/London",
        "+1": "Europe/Paris",
        "+2": "Europe/Helsinki",
        "+3": "Europe/Moscow",
        "+4": "Asia/Dubai",
        "+5": "Asia/Karachi",
        "+5.5": "Asia/Kolkata",
        "+6": "Asia/Dhaka",
        "+7": "Asia/Bangkok",
        "+8": "Asia/Shanghai",
        "+9": "Asia/Tokyo",
        "+9.5": "Australia/Adelaide",
        "+10": "Australia/Sydney",
        "+11": "Pacific/Auckland",
        "+12": "Pacific/Fiji",
    }
    
    return offset_map.get(offset_str, "Asia/Shanghai")

TIMEZONE_NAME = get_timezone_name(TIMEZONE)


# 数据库监控开关，默认关闭
TURNON_BINLOG_LISTENER = os.getenv("TURNON_BINLOG_LISTENER", "False").lower().strip() == "true"
# Binlog 位置管理器开关，默认关闭
ENABLE_BINLOG_POSITION = os.getenv("ENABLE_BINLOG_POSITION", "False").lower().strip() == "true"
# 定时任务开关，默认关闭
TRUNON_SCHEDULER = os.getenv("TRUNON_SCHEDULER", "False").lower().strip() == "true"
# 定时任务执行时间
SCHEDULER_HOUR = os.getenv("SCHEDULER_HOUR") or "6,8,10,12,14,16"
SCHEDULER_MINUTE = os.getenv("SCHEDULER_MINUTE") or "55"

LOG_LEVEL = os.getenv("LOG_LEVEL", "").strip() or "INFO"
# 日志保留天数，默认5
LOG_RETENTION = int(os.getenv("LOG_RETENTION", 5))

# 日志引擎开关：使用 loguru (V2) 还是原生 logging (V1)
# 默认 True，使用 loguru；设置为 False 切换到原生 logging
# 注意：如果 loguru 未安装，会自动回退到原生 logging
USE_LOGURU = os.getenv("USE_LOGURU", "true").lower().strip() == "true"


# 本地 SQLite 数据库名称
SQLITE_FILE = os.getenv("SQLITE_FILE", "").replace(".sqlite3", "").strip() or "local_data"


PROTOCOL = os.getenv("PROTOCOL", "http://")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

THIS_BASE_URL = PROTOCOL + "127.0.0.1:" + str(PORT)


# 事件流量控制
MAX_EVENTS_BATCH_SIZE = max(1, int(os.getenv("MAX_EVENTS_BATCH_SIZE") or 1))
MAX_EVENTS_PER_SECOND = max(1, int(os.getenv("MAX_EVENTS_PER_SECOND") or 1))


# 监控阈值配置
MONITOR_THRESHOLDS = {
    # 资源监控阈值
    "resource": {
        "cpu": 80.0,      # CPU使用率阈值（百分比）
        "memory": 80.0,   # 内存使用率阈值（百分比）
        "threads": 200,    # 线程数阈值
    },
    
    # 数据库监控阈值
    "database": {
        "connection_timeout": 30,      # 数据库连接超时时间（秒）
        "max_connection_attempts": 3,   # 最大连接尝试次数
        "slow_query_threshold": 1.0,    # 慢查询阈值（秒）
    },
    
    # HTTP监控阈值
    "http": {
        "error_rate": 5.0,              # HTTP错误率阈值（百分比）
        "response_time": 5.0,           # HTTP响应时间阈值（秒）
    },
    
    # 调度器监控阈值
    "scheduler": {
        "job_delay_threshold": 60,      # 任务延迟阈值（秒）
        "max_running_jobs": 10,         # 最大运行中任务数
    },
}

# 资源清理配置
RESOURCE_CLEANUP_CONFIG = {
    "interval": 300,  # 资源清理间隔（秒）
    "memory_threshold": 600.0,  # 触发清理的内存阈值（MB）
}



# 项目目录
PROJECT_DIR = os.getenv("PROJECT_DIR")
if PROJECT_DIR is None:
    raise ValueError("❌ PROJECT_DIR 环境变量未设置，请在 .env 文件中设置 PROJECT_DIR")
# JSON文件中记录的配置项
PROJECT_JSON = (os.getenv("PROJECT_JSON") or "dev") + ".json"
CACHE_JSON_FILE = JSONManager(f"project_files/{PROJECT_DIR}/{PROJECT_JSON}")
json_env_config = CACHE_JSON_FILE.get("env") or {}
MYAPS_VERSION = (os.getenv("MYAPS_VERSION") or json_env_config.get("MYAPS_VERSION") or "L").upper()
MYAPS_BASE_URL = os.getenv("MYAPS_BASE_URL") or json_env_config.get("MYAPS_BASE_URL")
MYAPS_DB_HOST = os.getenv("MYAPS_DB_HOST") or json_env_config.get("MYAPS_DB_HOST")
MYAPS_DB_PORT = int(os.getenv("MYAPS_DB_PORT") or json_env_config.get("MYAPS_DB_PORT") or 3333)
MYAPS_DB_USER = os.getenv("MYAPS_DB_USER") or json_env_config.get("MYAPS_DB_USER")
MYAPS_DB_PASSWORD = os.getenv("MYAPS_DB_PASSWORD") or json_env_config.get("MYAPS_DB_PASSWORD")
MYAPS_ROOT_PASSWORD = os.getenv("MYAPS_ROOT_PASSWORD") or json_env_config.get("MYAPS_ROOT_PASSWORD") or "E9damw0o@#"
MYAPS_DB_SET = os.getenv("MYAPS_DB_SET") or json_env_config.get("MYAPS_DB_SET")
if not MYAPS_DB_SET:
    logger.warning_msg("环境变量配置", "MYAPS_DB_SET 未设置")
    MYAPS_DB_SET = ""
MYAPS_DBSET_LIST = MYAPS_DB_SET.split(",")
MYAPS_MAIN_DB = os.getenv("MYAPS_MAIN_DB") or json_env_config.get("MYAPS_MAIN_DB")
if MYAPS_MAIN_DB is None:
    MYAPS_MAIN_DB = MYAPS_DBSET_LIST[0]

STAGING_DB_NAME = "--s"


# 本API数据库配置<postgreSQL>
THIS_DB_HOST = os.getenv("THIS_DB_HOST") or json_env_config.get("THIS_DB_HOST")
THIS_DB_PORT = int(os.getenv("THIS_DB_PORT") or json_env_config.get("THIS_DB_PORT") or 5432)
THIS_DB_USER = os.getenv("THIS_DB_USER") or json_env_config.get("THIS_DB_USER")
THIS_DB_PASSWORD = os.getenv("THIS_DB_PASSWORD") or json_env_config.get("THIS_DB_PASSWORD")
THIS_DB_NAME = os.getenv("THIS_DB_NAME") or json_env_config.get("THIS_DB_NAME")


# Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST") or json_env_config.get("REDIS_HOST") or "127.0.0.1"
REDIS_PORT = int(os.getenv("REDIS_PORT") or json_env_config.get("REDIS_PORT") or 6379)
REDIS_DB = int(os.getenv("REDIS_DB") or json_env_config.get("REDIS_DB") or 0)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or json_env_config.get("REDIS_PASSWORD") or ""

