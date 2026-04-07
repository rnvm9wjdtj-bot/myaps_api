from pathlib import Path
current_dir = Path.cwd()
# root_dir = current_dir.parent.parent
# print(root_dir)
import sys
sys.path.append(str(current_dir))

import os
from dotenv import load_dotenv

load_dotenv(os.getenv('ENV_FILE', os.path.join(current_dir, '.env')))
PROJECT_DIR = os.getenv("PROJECT_DIR")
PROJECT_JSON = os.getenv("PROJECT_JSON")

from globalobjects.json_manager import JSONManager

CACHE_JSON_FILE = JSONManager(f"{current_dir}/project_files/{PROJECT_DIR}/{PROJECT_JSON}.json")

MYAPS_MAIN_DB = CACHE_JSON_FILE.get('env').get("MYAPS_MAIN_DB", "default")
MYAPS_DB_HOST = CACHE_JSON_FILE.get('env').get("MYAPS_DB_HOST", "localhost")
MYAPS_DB_PORT = CACHE_JSON_FILE.get('env').get("MYAPS_DB_PORT", 3333)
MYAPS_DB_USER = CACHE_JSON_FILE.get('env').get("MYAPS_DB_USER", "root")
MYAPS_DB_PASSWORD = CACHE_JSON_FILE.get('env').get("MYAPS_DB_PASSWORD", "123456")

connections = {
    MYAPS_MAIN_DB: {
        "engine": "tortoise.backends.mysql",
        "credentials": {
            "host": MYAPS_DB_HOST,
            "port": MYAPS_DB_PORT,
            "user": MYAPS_DB_USER,
            "password": MYAPS_DB_PASSWORD,
            "database": MYAPS_MAIN_DB,
            "charset": "utf8mb4",
            "connect_timeout": 5,  # 添加连接超时设置
        }
    }
}

print(connections)


# 导入模型类
from apps.io_api.models import TMaterial  # 替换为你的模型
from tortoise import Tortoise  # Tortoise ORM 核心

import asyncio  # 用于执行异步操作


TORTOISE_ORM_CONFIG = {
    "connections": connections,
    "apps": {
        "io_api_models": {
            "models": ["apps.io_api.models",],
            "default_connection": MYAPS_MAIN_DB
        },
    },
}

async def init_db():
    """初始化 Tortoise ORM"""
    await Tortoise.init(config=TORTOISE_ORM_CONFIG)
    print("Tortoise ORM 初始化完成")

# 执行初始化
asyncio.run(init_db())

async def test_query():
    """测试查询操作"""
    result = await TMaterial.filter(materialno="01000").first().values()
    print(f"查询结果: {result}")

# 直接使用 await 执行
asyncio.run(test_query())
