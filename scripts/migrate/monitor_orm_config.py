from core import TORTOISE_ORM_CONFIG, SQLITE_FILE

# 复用 TORTOISE_ORM_CONFIG 中的 SQLITE_FILE 连接配置和 monitor_models 应用配置
monitor_orm_config = {
    "connections": {
        SQLITE_FILE: TORTOISE_ORM_CONFIG["connections"][SQLITE_FILE]
    },
    "apps": {
        "monitor_models": TORTOISE_ORM_CONFIG["apps"]["monitor_models"]
    },
}
