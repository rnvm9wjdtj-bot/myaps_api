# from tortoise import Tortoise

import os
from pathlib import Path
from dotenv import load_dotenv


from globalobjects.json_manager import JSONManager
# 加载.env文件中的环境变量
BASE_DIR = os.getcwd()
load_dotenv(os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env')))

# 项目目录
PROJECT_DIR = os.getenv("PROJECT_DIR")
if PROJECT_DIR is None:
    raise ValueError("❌ PROJECT_DIR 环境变量未设置，请在 .env 文件中设置 PROJECT_DIR")
# 数据库监控开关
TURNON_DBMONITOR = os.getenv("TURNON_DBMONITOR", "False").lower() == "true"

# JSON文件中记录的配置项
CACHE_FILE = JSONManager(f"project_files/{PROJECT_DIR}/cache.json")
env_config = CACHE_FILE.get("env")

PROTOCOL = env_config.get("PROTOCOL", "http://")
HOST = env_config.get("HOST", "localhost")
PORT = int(env_config.get("PORT", 8000))
THIS_BASE_URL = f"{PROTOCOL}{HOST}:{PORT}"

MYAPS_VERSION = env_config.get("MYAPS_VERSION", "L").upper()
MYAPS_BASE_URL = env_config.get("MYAPS_BASE_URL")
MYAPS_DB_HOST = env_config.get("MYAPS_DB_HOST")
MYAPS_DB_PORT = int(env_config.get("MYAPS_DB_PORT"))
MYAPS_DB_USER = env_config.get("MYAPS_DB_USER")
MYAPS_DB_PASSWORD = env_config.get("MYAPS_DB_PASSWORD")
MYAPS_DB_SET = env_config.get("MYAPS_DB_SET")
MYAPS_MAIN_DB = env_config.get("MYAPS_MAIN_DB")
MYAPS_DBSET_LIST = MYAPS_DB_SET.split(",")

# 本API数据库配置<postgreSQL>
THIS_DB_HOST = env_config.get("THIS_DB_HOST")
THIS_DB_PORT = env_config.get("THIS_DB_PORT") 
THIS_DB_USER = env_config.get("THIS_DB_USER") 
THIS_DB_PASSWORD = env_config.get("THIS_DB_PASSWORD")
THIS_DB_NAME = env_config.get("THIS_DB_NAME")



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
            "default_connection": MYAPS_MAIN_DB  # 当THIS_DB_NAME为None时，使用MYAPS_MAIN_DB作为默认连接
        },
    },
}

