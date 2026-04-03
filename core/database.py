import time

from tortoise.contrib.fastapi import register_tortoise
from config.settings import TORTOISE_ORM_CONFIG, MYAPS_MAIN_DB, MYAPS_DBSET_LIST
from globalobjects import logger as log_config



def register_database(app):
    register_tortoise(
        app=app,
        config=TORTOISE_ORM_CONFIG,
        # modules={"models": ["project_code.models"]},
        # generate_schemas=True,    # 生产环境不要开，若数据库为空则自动生成对应表单
        # add_exception_handlers=True,  # 生产环境不要开，会泄露调试信息
    )


async def warmup_connections():
    """预热数据库连接"""
    if not MYAPS_MAIN_DB:
        return
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            try:
                start_time = time.time()
                is_healthy = await manager.check_connection_health()
                response_time = time.time() - start_time
                if is_healthy:
                    log_config.info(f"连接预热成功: {db_name} - 响应时间: {response_time:.3f}秒")
                else:
                    log_config.warning(f"连接预热失败: {db_name}")
                    # 尝试刷新连接
                    await manager.refresh_connection()
            except Exception as e:
                log_config.error(f"连接预热异常: {db_name} - {str(e)}")
        log_config.info("数据库连接预热完成")
    except Exception as e:
        log_config.error(f"连接预热异常: {str(e)}")


async def check_db_connections():
    """定期检查数据库连接状态"""
    if not MYAPS_MAIN_DB:
        return
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            # 检查连接健康状态
            start_time = time.time()
            is_healthy = await manager.check_connection_health()
            response_time = time.time() - start_time
            
            # 记录响应时间，超过1秒时预警
            if response_time > 1.0:
                log_config.warning(f"数据库连接响应缓慢: {db_name} - {response_time:.3f}秒")
            
            if not is_healthy:
                log_config.warning(f"数据库连接 {db_name} 不健康，尝试刷新连接")
                await manager.refresh_connection()
            # 获取连接池状态
            pool_status = await manager.get_connection_pool_status()
            log_config.debug(f"连接池状态 - {db_name}: {pool_status}")
        log_config.debug("数据库连接检查完成")
    except Exception as e:
        log_config.error(f"数据库连接检查异常: {e}")

