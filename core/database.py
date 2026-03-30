from tortoise.contrib.fastapi import register_tortoise
from config.settings import TORTOISE_ORM_CONFIG
from globalobjects import logger as log_config

def register_database(app):
    register_tortoise(
        app=app,
        config=TORTOISE_ORM_CONFIG,
        # modules={"models": ["project_code.models"]},
        # generate_schemas=True,    # 生产环境不要开，若数据库为空则自动生成对应表单
        # add_exception_handlers=True,  # 生产环境不要开，会泄露调试信息
    )

async def check_db_connections():
    """定期检查数据库连接状态"""
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            # 检查连接健康状态
            is_healthy = await manager.check_connection_health()
            if not is_healthy:
                log_config.warning(f"数据库连接 {db_name} 不健康，尝试刷新连接")
                await manager.refresh_connection()
            # 获取连接池状态
            pool_status = await manager.get_connection_pool_status()
            log_config.debug(f"连接池状态 - {db_name}: {pool_status}")
        log_config.debug("数据库连接检查完成")
    except Exception as e:
        log_config.error(f"数据库连接检查异常: {e}")
