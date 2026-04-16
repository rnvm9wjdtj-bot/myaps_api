from core import TORTOISE_ORM_CONFIG

# 复用 TORTOISE_ORM_CONFIG 中的 local_data 连接配置和 monitor_models 应用配置
monitor_orm_config = {
    "connections": {
        "local_data": TORTOISE_ORM_CONFIG["connections"]["local_data"]
    },
    "apps": {
        "monitor_models": TORTOISE_ORM_CONFIG["apps"]["monitor_models"]
    },
}
