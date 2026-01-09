# from tortoise import Tortoise

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载.env文件中的环境变量
BASE_DIR = os.getcwd()
load_dotenv(os.getenv('ENV_FILE', os.path.join(BASE_DIR, '.env')))

# 从环境变量读取配置
MYAPS_BASE_URL = os.getenv("MYAPS_BASE_URL")
MYAPS_DB_HOST = os.getenv("MYAPS_DB_HOST")
MYAPS_DB_PORT = int(os.getenv("MYAPS_DB_PORT"))
MYAPS_DB_USER = os.getenv("MYAPS_DB_USER")
MYAPS_DB_PASSWORD = os.getenv("MYAPS_DB_PASSWORD")
MYAPS_DB_SET = os.getenv("MYAPS_DB_SET")
MYAPS_DBSET_LIST = MYAPS_DB_SET.split(",")
MYAPS_MAIN_DB = os.getenv("MYAPS_MAIN_DB")

PROTOCOL = os.getenv("PROTOCOL", "http://")
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", 8000))
THIS_BASE_URL = f"{PROTOCOL}{HOST}:{PORT}"

# 本API数据库配置<postgreSQL>
THIS_DB_HOST = os.getenv("THIS_DB_HOST")
THIS_DB_PORT = int(os.getenv("THIS_DB_PORT"))
THIS_DB_USER = os.getenv("THIS_DB_USER")
THIS_DB_PASSWORD = os.getenv("THIS_DB_PASSWORD")
THIS_DB_NAME = os.getenv("THIS_DB_NAME")

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
            "default_connection": THIS_DB_NAME  # 使用PostgreSQL
        },
    },
}

