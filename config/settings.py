# from tortoise import Tortoise

import os
from dotenv import load_dotenv

# 加载.env文件中的环境变量
load_dotenv(os.getenv('ENV_FILE', os.path.join(os.getcwd(), '.env')))

# 从环境变量读取配置，如果不存在则使用默认值
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SET = os.getenv("DB_SET").split(",")  # 主账套放第一个

THIS_SERVER_HOST = os.getenv("THIS_SERVER_HOST")
THIS_SERVER_PORT = int(os.getenv("THIS_SERVER_PORT"))

######################################################################################
# 数据库配置
TORTOISE_ORM_CONFIG = {
    "connections": {
        db:{
            "engine": "tortoise.backends.mysql",
            "credentials": {
                "host": DB_HOST,
                "port": DB_PORT,
                "user": DB_USER,
                "password": DB_PASSWORD,
                "database": db,
                "charset": "utf8mb4",
            },
        } for db in DB_SET
    },
    "apps": {
        "models": {
            "models": ["project_code.models"], 
            "default_connection": DB_SET[0],
        },
    },
}

# async def init_db():
#     """初始化数据库连接"""
#     await Tortoise.init(config=TORTOISE_ORM_CONFIG)
#     await Tortoise.generate_schemas(safe=True)

# async def close_db():
#     """关闭数据库连接"""
#     await Tortoise.close_connections()



