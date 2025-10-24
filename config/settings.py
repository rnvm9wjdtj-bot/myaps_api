# from tortoise import Tortoise

import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv(os.getenv('ENV_FILE', os.path.join(os.getcwd(), '.env')))

# 从环境变量读取配置，如果不存在则使用默认值
MYAPS_DB_HOST = os.getenv("MYAPS_DB_HOST")
MYAPS_DB_PORT = int(os.getenv("MYAPS_DB_PORT"))
MYAPS_DB_USER = os.getenv("MYAPS_DB_USER")
MYAPS_DB_PASSWORD = os.getenv("MYAPS_DB_PASSWORD")
MYAPS_DB_SET = os.getenv("MYAPS_DB_SET").split(",")  # 主账套放第一个

THIS_SERVER_HOST = os.getenv("THIS_SERVER_HOST")
THIS_SERVER_PORT = int(os.getenv("THIS_SERVER_PORT"))
# 本API数据库配置<postgreSQL>
THIS_DB_HOST = os.getenv("THIS_DB_HOST")
THIS_DB_PORT = int(os.getenv("THIS_DB_PORT"))
THIS_DB_USER = os.getenv("THIS_DB_USER")
THIS_DB_PASSWORD = os.getenv("THIS_DB_PASSWORD")
THIS_DB_NAME = os.getenv("THIS_DB_NAME")

######################################################################################
# 数据库配置
connections = {}
for db in MYAPS_DB_SET:
    connections[db] = {
        "engine": "tortoise.backends.mysql",
        "credentials": {
            "host": MYAPS_DB_HOST,
            "port": MYAPS_DB_PORT,
            "user": MYAPS_DB_USER,
            "password": MYAPS_DB_PASSWORD,
            "database": db,
            "charset": "utf8mb4",
        },
    }
TORTOISE_ORM_CONFIG = {
    "connections": connections,
    "apps": {
        "models": {
            "models": ["apps.io_api.models", "apps.data_manager.models"], 
            "default_connection": MYAPS_DB_SET[0],
        },
    },
}

print(TORTOISE_ORM_CONFIG)