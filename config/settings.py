# from tortoise import Tortoise

# 根据环境不同修改以下变量
DB_HOST = "1.13.184.21"
DB_PORT = 3333
DB_USER = "MYAPS"
DB_PASSWORD = "MYAPS2025"
DB_SET = ["qdjh", "myaps0"]   # 主账套放第一个

THIS_SERVER_HOST = "127.0.0.1"
THIS_SERVER_PORT = 8000

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



