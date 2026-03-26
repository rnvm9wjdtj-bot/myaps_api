# from tortoise import Tortoise

import os
from pathlib import Path
from dotenv import load_dotenv


from globalobjects.json_manager import JSONManager
from globalobjects import logger as log_config


console_log = log_config.get_logger(__name__)
# 加载.env文件中的环境变量
BASE_DIR = os.getcwd()
load_dotenv(os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env')))

# 项目目录
PROJECT_DIR = os.getenv("PROJECT_DIR")
if PROJECT_DIR is None:
    raise ValueError("❌ PROJECT_DIR 环境变量未设置，请在 .env 文件中设置 PROJECT_DIR")
# 数据库监控开关
TURNON_DBMONITOR = os.getenv("TURNON_DBMONITOR", "False").lower() == "true"
# 定时任务开关
TRUNON_SCHEDULER = os.getenv("TRUNON_SCHEDULER", "False").lower() == "true"
# 定时任务执行时间
SCHEDULER_HOUR = os.getenv("SCHEDULER_HOUR") or "6,8,10,12,14,16"
SCHEDULER_MINUTE = os.getenv("SCHEDULER_MINUTE") or "55"


# JSON文件中记录的配置项
CACHE_FILENAME = os.getenv("CACHE_FILENAME") or "cache.json"
CACHE_FILE = JSONManager(f"project_files/{PROJECT_DIR}/{CACHE_FILENAME}")
json_env_config = CACHE_FILE.get("env") or {}

PROTOCOL = os.getenv("PROTOCOL") or json_env_config.get("PROTOCOL") or "http://"
HOST = os.getenv("HOST") or json_env_config.get("HOST")  or "localhost"
PORT = int(os.getenv("PORT") or json_env_config.get("PORT") or 8000)
THIS_BASE_URL = f"{PROTOCOL}localhost:{PORT}"

MYAPS_VERSION = (os.getenv("MYAPS_VERSION") or json_env_config.get("MYAPS_VERSION") or "L").upper()
MYAPS_BASE_URL = os.getenv("MYAPS_BASE_URL") or json_env_config.get("MYAPS_BASE_URL")
MYAPS_DB_HOST = os.getenv("MYAPS_DB_HOST") or json_env_config.get("MYAPS_DB_HOST")
MYAPS_DB_PORT = int(os.getenv("MYAPS_DB_PORT") or json_env_config.get("MYAPS_DB_PORT") or 3333)
MYAPS_DB_USER = os.getenv("MYAPS_DB_USER") or json_env_config.get("MYAPS_DB_USER")
MYAPS_DB_PASSWORD = os.getenv("MYAPS_DB_PASSWORD") or json_env_config.get("MYAPS_DB_PASSWORD")
MYAPS_DB_SET = os.getenv("MYAPS_DB_SET") or json_env_config.get("MYAPS_DB_SET")
if not MYAPS_DB_SET:
    console_log.warning_msg("环境变量配置", "MYAPS_DB_SET 未设置")
    MYAPS_DB_SET = ""
MYAPS_DBSET_LIST = MYAPS_DB_SET.split(",")
MYAPS_MAIN_DB = os.getenv("MYAPS_MAIN_DB") or json_env_config.get("MYAPS_MAIN_DB")
if MYAPS_MAIN_DB is None:
    MYAPS_MAIN_DB = MYAPS_DBSET_LIST[0]
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"

# 本API数据库配置<postgreSQL>
THIS_DB_HOST = os.getenv("THIS_DB_HOST") or json_env_config.get("THIS_DB_HOST")
THIS_DB_PORT = int(os.getenv("THIS_DB_PORT") or json_env_config.get("THIS_DB_PORT") or 5432)
THIS_DB_USER = os.getenv("THIS_DB_USER") or json_env_config.get("THIS_DB_USER")
THIS_DB_PASSWORD = os.getenv("THIS_DB_PASSWORD") or json_env_config.get("THIS_DB_PASSWORD")
THIS_DB_NAME = os.getenv("THIS_DB_NAME") or json_env_config.get("THIS_DB_NAME")



######################################################################################
# 数据库配置
connections = {}
# 为每个账套创建MySQL连接配置
for db in MYAPS_DBSET_LIST:
    connections[db] = {
        "engine": "tortoise.backends.mysql",
        "credentials": {
            "host": MYAPS_DB_HOST,
            "port": MYAPS_DB_PORT,
            "user": MYAPS_DB_USER,
            "password": MYAPS_DB_PASSWORD,
            "database": db,
            "charset": "utf8mb4",
            "connect_timeout": 5,  # 添加连接超时设置
        }
    }

if THIS_DB_NAME:
    # 创建PostgreSQL连接配置
    connections[THIS_DB_NAME] = {
        "engine": "tortoise.backends.asyncpg",
        "credentials": {
            "host": THIS_DB_HOST,
            "port": THIS_DB_PORT,
            "user": THIS_DB_USER,
            "password": THIS_DB_PASSWORD,
            "database": THIS_DB_NAME
        }
    }

TORTOISE_ORM_CONFIG = {
    "connections": connections,
    "apps": {
        "io_api_models": {
            "models": ["apps.io_api.models",],
            "default_connection": MYAPS_MAIN_DB  # 使用MyAPS账套
        },
        "data_opt_models": {
            "models": ["apps.data_opt.models", "aerich.models"],
            "default_connection": THIS_DB_NAME or MYAPS_MAIN_DB  # 当THIS_DB_NAME为None时，使用MYAPS_MAIN_DB作为默认连接
        },
    },
}

