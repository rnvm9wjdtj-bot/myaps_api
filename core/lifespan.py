from contextlib import asynccontextmanager
import asyncio
import time
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status, initialize_scheduler
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from apps.common.utils.resource_monitor import resource_monitor
from globalobjects import EVENT_AGGREGATOR
from config.settings import TURNON_DBMONITOR, TRUNON_SCHEDULER
from core.database import check_db_connections

@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理器"""
    # 应用启动时执行的操作
    log_config.initialize_logging()
    
    # 将主应用事件循环传递给调度器
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    # 定时任务管理器将在后面通过initialize_scheduler()统一初始化和启动
    
    if TURNON_DBMONITOR:
        mysql_monitor.start_monitoring()
        log_config.info("MySQL Binlog监控已启动")
    else:
        log_config.warning("⚠️ MySQL Binlog监控未启动")
    
    # 启动资源监控
    log_config.info("开始启动资源监控...")
    resource_monitor.start_monitoring(interval=30)
    log_config.info("系统资源监控已启动")
    
    if TRUNON_SCHEDULER:
        initialize_scheduler()
    else:
        log_config.warning("⚠️ 定时任务初始化被跳过，因为 TRUNON_SCHEDULER=false")
    
    # 设置定期检查数据库连接的任务（从原startup_event迁移）
    async def schedule_db_checks():
        """定期执行数据库连接检查"""
        while True:
            await check_db_connections()
            # 每300秒（5分钟）检查一次
            await asyncio.sleep(300)
    
    # 启动数据库连接检查任务（从原startup_event迁移）
    asyncio.create_task(schedule_db_checks())
    log_config.info("数据库连接检查任务已启动")
    
    # 等待一段时间，确保资源监控线程正常启动
    time.sleep(1)
    log_config.info("应用启动完成，开始运行")
    
    yield  # 应用运行期间
    
    # 应用关闭时执行的操作
    log_config.info("应用关闭中...")
    
    if TURNON_DBMONITOR:
        mysql_monitor.stop_monitoring()
        log_config.info("MySQL Binlog监控已停止")
    else:
        log_config.debug("⚠️ MySQL Binlog监控未启动，无需停止")

    # 关闭调度器
    if TRUNON_SCHEDULER:
        scheduler_manager.shutdown()
        log_config.info("定时任务管理器已关闭")
    else:
        log_config.debug("⚠️ 定时任务管理器未启动，无需关闭")
    
    # 停止资源监控
    resource_monitor.stop_monitoring()
    log_config.info("系统资源监控已停止")
    
    # 停止事件聚合器
    EVENT_AGGREGATOR.stop()
    log_config.info("事件聚合器已停止")
    
    # 关闭统一日志系统
    log_config.shutdown_logging()
