import asyncio
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import initialize_scheduler
from core.database import check_db_connections

async def startup_event():
    """应用启动事件"""
    # 初始化定时任务管理器
    await initialize_scheduler()
    
    # 设置定期检查数据库连接的任务
    async def schedule_db_checks():
        """定期执行数据库连接检查"""
        while True:
            await check_db_connections()
            # 每300秒（5分钟）检查一次
            await asyncio.sleep(300)
    
    # 启动数据库连接检查任务
    asyncio.create_task(schedule_db_checks())
    log_config.info("数据库连接检查任务已启动")
