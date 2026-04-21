from contextlib import asynccontextmanager
import asyncio
import os
import time
import redis
import json
import inspect
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status, initialize_scheduler
from apps.data_opt.utils.binlog_listener import binlog_listener
from apps.common.utils.resource_monitor import resource_monitor
from apps.common.monitor import (
    start_db_health_checker, stop_db_health_checker,
    start_failed_operation_recovery, stop_failed_operation_recovery
)
from globalobjects import EVENT_AGGREGATOR
from core.settings import TURNON_DBMONITOR, TRUNON_SCHEDULER, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, MAX_EVENTS_BATCH_SIZE
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
        binlog_listener.start_monitoring()
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

    # 启动失败操作恢复管理器（后台自动重试失败的数据库操作）
    await start_failed_operation_recovery()

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
                # 批量读取事件
                events = []
                for _ in range(MAX_EVENTS_BATCH_SIZE):
                    # 在线程池中执行 blpop 操作
                    def blpop():
                        return redis_client.blpop('db_events', timeout=1)
                    
                    result = await loop.run_in_executor(executor, blpop)
                    if result:
                        events.append(result)
                    else:
                        break
                
                # 批量处理事件
                for result in events:
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

    async def cleanup_expired_events():
        """定期清理过期事件"""
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
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
            log_config.info("Redis 事件清理任务已启动，每小时清理一次过期事件")
            
            while True:
                try:
                    # 获取列表长度
                    def get_list_length():
                        return redis_client.llen('db_events')
                    
                    length = await loop.run_in_executor(executor, get_list_length)
                    if length > 0:
                        log_config.info(f"开始清理过期事件，当前队列长度: {length}")
                        # 从列表尾部开始检查
                        processed_count = 0
                        expired_count = 0
                        
                        for _ in range(min(length, 1000)):  # 每次最多检查1000个事件
                            # 获取尾部元素
                            def rpop():
                                return redis_client.rpop('db_events')
                            
                            event_data = await loop.run_in_executor(executor, rpop)
                            if event_data:
                                processed_count += 1
                                try:
                                    event = json.loads(event_data.decode('utf-8'))
                                    event_timestamp = event.get('timestamp', 0)
                                    # 如果事件未过期（24小时内），重新添加到列表
                                    if time.time() - event_timestamp <= 86400:
                                        def lpush():
                                            return redis_client.lpush('db_events', event_data)
                                        await loop.run_in_executor(executor, lpush)
                                    else:
                                        expired_count += 1
                                except Exception as e:
                                    # 如果解析失败，认为是无效事件，不重新添加
                                    log_config.debug(f"解析事件失败，跳过: {e}")
                                    expired_count += 1
                        
                        log_config.info(f"事件清理完成，处理了 {processed_count} 个事件，清理了 {expired_count} 个过期事件")
                except Exception as e:
                    log_config.error(f"清理过期事件失败: {e}")
                
                # 每小时清理一次
                await asyncio.sleep(3600)
        except Exception as e:
            log_config.error(f"Redis 事件清理任务启动失败: {e}")

    asyncio.create_task(start_redis_consumer())
    log_config.info("Redis 消息消费者已启动")

    # 启动 Redis 事件清理任务
    asyncio.create_task(cleanup_expired_events())
    log_config.info("Redis 事件清理任务已启动")

    # 等待一段时间，确保所有服务正常启动
    await asyncio.sleep(1)
    log_config.info("应用启动完成，开始运行")
    
    yield  # 应用运行期间
    
    # 应用关闭时执行的操作
    log_config.info("应用关闭中...")
    
    # 1. 先停止 MySQL Binlog 监控（最依赖数据库）
    if TURNON_DBMONITOR:
        log_config.info("正在停止 MySQL Binlog 监控...")
        binlog_listener.stop_monitoring()
        log_config.info("MySQL Binlog监控已停止")
    else:
        log_config.debug("⚠️ MySQL Binlog监控未启动，无需停止")

    # 2. 停止 Redis 相关任务
    log_config.info("正在停止 Redis 相关任务...")
    # 这里可以添加 Redis 消费者的停止逻辑
    log_config.info("Redis 相关任务已停止")

    # 3. 等待一段时间，确保所有任务完成
    log_config.info("⏳ 等待所有后台任务完成...")
    await asyncio.sleep(5)  # 等待5秒，让所有任务完成

    # 4. 关闭调度器
    if TRUNON_SCHEDULER:
        log_config.info("正在关闭调度器...")
        scheduler_manager.shutdown()
        log_config.info("定时任务管理器已关闭")
    else:
        log_config.debug("⚠️ 定时任务管理器未启动，无需关闭")
    
    # 5. 停止资源监控
    log_config.info("正在停止资源监控...")
    resource_monitor.stop_monitoring()
    log_config.info("系统资源监控已停止")
    
    # 6. 停止事件聚合器
    log_config.info("正在停止事件聚合器...")
    EVENT_AGGREGATOR.stop()
    log_config.info("事件聚合器已停止")

    # 7. 停止数据库健康检查器
    log_config.info("正在停止数据库健康检查器...")
    await stop_db_health_checker()
    log_config.info("数据库健康检查器已停止")

    # 8. 停止失败操作恢复管理器
    log_config.info("正在停止OperationRecovery管理器...")
    await stop_failed_operation_recovery()
    log_config.info("OperationRecovery管理器已停止")

    # 10. 取消后台任务
    if 'db_check_task' in locals():
        log_config.info("正在取消数据库连接检查任务...")
        db_check_task.cancel()
        try:
            await db_check_task
        except asyncio.CancelledError:
            pass
        log_config.info("数据库连接检查任务已取消")

    if 'pool_monitor_task' in locals():
        log_config.info("正在取消连接池监控任务...")
        pool_monitor_task.cancel()
        try:
            await pool_monitor_task
        except asyncio.CancelledError:
            pass
        log_config.info("连接池监控任务已取消")

    # 11. 等待一段时间，确保所有任务真正完成
    log_config.info("⏳ 等待所有任务彻底完成...")
    await asyncio.sleep(3)  # 再等待3秒

    log_config.info("应用关闭完成")

    # 12. 关闭统一日志系统
    log_config.shutdown_logging()
