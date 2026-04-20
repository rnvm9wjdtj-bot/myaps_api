from contextlib import asynccontextmanager
import asyncio
import os
import time
import redis
import json
import inspect
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status, initialize_scheduler
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from apps.common.utils.resource_monitor import resource_monitor
from apps.common.monitor import start_db_health_checker, stop_db_health_checker
from globalobjects import EVENT_AGGREGATOR
from core.settings import TURNON_DBMONITOR, TRUNON_SCHEDULER, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
from core.database import check_db_connections, warmup_connections, start_pool_monitoring

@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理器"""
    # 应用启动时执行的操作
    log_config.initialize_logging()
    
    # 将主应用事件循环传递给调度器
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    # 预热数据库连接（在启动其他服务之前）
    log_config.info("开始预热数据库连接...")
    await warmup_connections()
    log_config.info("数据库连接预热完成")
    
    # 启动资源监控
    log_config.info("开始启动资源监控...")
    resource_monitor.start_monitoring(interval=30)
    log_config.info("系统资源监控已启动")
    
    # 等待服务器完全就绪，确保客户端可以正常连接
    log_config.info("等待服务器完全就绪...")
    await asyncio.sleep(1)
    log_config.info("服务器已就绪")
    
    if TURNON_DBMONITOR:
        mysql_monitor.start_monitoring()
        log_config.info("MySQL Binlog监控已启动")
    else:
        log_config.warning("⚠️ MySQL Binlog监控未启动")
    
    # 延迟启动定时任务，确保服务器完全就绪
    if TRUNON_SCHEDULER:
        log_config.info("准备启动定时任务...")
        await asyncio.sleep(1)  # 减少等待时间
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
    db_check_task = asyncio.create_task(schedule_db_checks())
    log_config.info("数据库连接检查任务已启动")
    
    # 启动连接池监控任务
    pool_monitor_task = asyncio.create_task(start_pool_monitoring())
    log_config.info("连接池监控任务已启动")

    # 启动数据库健康检查器（独立后台任务，不依赖前端访问）
    await start_db_health_checker()

    # 启动 Redis 消息消费者（处理来自数据库监听器的事件）
    async def start_redis_consumer():
        """启动 Redis 消息消费者，处理来自数据库监听器的事件"""
        try:
            log_config.info(f"尝试连接到 Redis: {REDIS_HOST}:{REDIS_PORT}, DB: {REDIS_DB}")
            
            # 创建线程池
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            loop = asyncio.get_event_loop()
            
            # 在线程池中创建 Redis 连接
            def create_redis_client():
                return redis.Redis(
                    host=REDIS_HOST, 
                    port=REDIS_PORT, 
                    db=REDIS_DB, 
                    password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
            
            redis_client = await loop.run_in_executor(executor, create_redis_client)
            log_config.info(f"Redis 连接已建立，等待事件...")
            
            while True:
                # 在线程池中执行 blpop 操作
                def blpop():
                    return redis_client.blpop('db_events', timeout=1)
                
                result = await loop.run_in_executor(executor, blpop)
                if result:
                    _, message = result
                    event_data = json.loads(message.decode('utf-8'))
                    event_type = event_data.get('event_type')
                    data = event_data.get('data')
                    log_config.info(f"从消息队列接收到事件: {event_type}")
                    asyncio.create_task(handle_redis_event(event_type, data))
        except Exception as e:
            log_config.error(f"Redis 消费者启动失败: {e}")


    async def handle_redis_event(event_type: str, event_data):
        """处理从 Redis 消息队列接收的事件"""
        log_config.info(f"开始处理事件: {event_type}")
        try:
            import importlib
            import concurrent.futures
            PROJECT_DIR_VALUE = os.getenv('PROJECT_DIR')
            if not PROJECT_DIR_VALUE:
                log_config.warning("PROJECT_DIR 环境变量未设置，无法处理 Redis 事件")
                return
            
            project_module = importlib.import_module(f'project_files.{PROJECT_DIR_VALUE}.client')
            event_handler_name = f"batch_handle_{event_type}"
            event_handler = getattr(project_module, event_handler_name, None)
            
            if event_handler:
                log_config.info(f"找到事件处理器: {event_handler_name}")
                # 创建独立的线程池，避免阻塞主事件循环
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    if inspect.iscoroutinefunction(event_handler):
                        # 对于协程函数，在事件循环中执行
                        await event_handler(event_data)
                    else:
                        # 对于同步函数，在线程池中执行
                        await loop.run_in_executor(executor, event_handler, event_data)
                log_config.info(f"事件处理成功: {event_type}")
            else:
                log_config.warning(f"未找到事件处理器: {event_handler_name}")
        except Exception as e:
            log_config.error(f"处理 Redis 事件 {event_type} 时出错: {e}")

    asyncio.create_task(start_redis_consumer())
    log_config.info("Redis 消息消费者已启动")

    # 等待一段时间，确保所有服务正常启动
    await asyncio.sleep(1)
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

    # 停止数据库健康检查器
    await stop_db_health_checker()
    log_config.info("数据库健康检查器已停止")

    # 取消后台任务
    if 'db_check_task' in locals():
        db_check_task.cancel()
        try:
            await db_check_task
        except asyncio.CancelledError:
            pass
        log_config.info("数据库连接检查任务已取消")

    if 'pool_monitor_task' in locals():
        pool_monitor_task.cancel()
        try:
            await pool_monitor_task
        except asyncio.CancelledError:
            pass
        log_config.info("连接池监控任务已取消")

    log_config.info("应用关闭完成")

    # 关闭统一日志系统
    log_config.shutdown_logging()
