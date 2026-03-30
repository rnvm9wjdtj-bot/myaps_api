from contextlib import asynccontextmanager
import asyncio
import time
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from apps.common.utils.resource_monitor import resource_monitor
from globalobjects import EVENT_AGGREGATOR
from config.settings import TURNON_DBMONITOR, TRUNON_SCHEDULER

@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理器"""
    # 应用启动时执行的操作
    log_config.initialize_logging()
    
    # 将主应用事件循环传递给调度器
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    # 初始化并启动定时任务管理器
    if TRUNON_SCHEDULER:
        scheduler_manager.init_scheduler()
        scheduler_manager.start()
        log_config.info(f"定时任务管理器状态: {get_scheduler_status()}")
    else:
        log_config.warning("⚠️ 定时任务管理器未启动")
    
    if TURNON_DBMONITOR:
        mysql_monitor.start_monitoring()
        log_config.info("MySQL Binlog监控已启动")
    else:
        log_config.warning("⚠️ MySQL Binlog监控未启动")
    
    # 启动资源监控
    log_config.info("开始启动资源监控...")
    resource_monitor.start_monitoring(interval=30)
    log_config.info("系统资源监控已启动")
    
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
