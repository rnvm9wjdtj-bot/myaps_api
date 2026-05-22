from contextlib import asynccontextmanager
import asyncio
import os
import time
import json
import inspect
import redis
from globalobjects import logger as log_config
from globalobjects.logger import shutdown_logging
from apps.data_opt.utils.scheduler import scheduler_manager, get_scheduler_status, initialize_scheduler
from apps.data_opt.utils.binlog_listener import binlog_listener
from apps.common.utils.resource_monitor import resource_monitor
from apps.common.monitor import (
    start_db_health_checker, stop_db_health_checker,
    start_failed_operation_recovery, stop_failed_operation_recovery
)
from apps.common.monitor.log_stream_service import start_log_stream, stop_log_stream
from globalobjects import EVENT_AGGREGATOR
from core.settings import TURNON_BINLOG_LISTENER, TRUNON_SCHEDULER, MAX_EVENTS_BATCH_SIZE
from core.database import check_db_connections, warmup_connections, start_pool_monitoring, db_init_manager


@asynccontextmanager
async def lifespan(app):
    """应用生命周期管理器"""
    from globalobjects.logger.lifespan import initialize_logging
    await initialize_logging()
    log_config.info("✅ 统一日志系统初始化完成")
    
    main_loop = asyncio.get_running_loop()
    scheduler_manager.set_main_loop(main_loop)
    log_config.info(f"已将主应用事件循环传递给调度器: {main_loop}")
    
    from core.database import validate_database_config
    from tortoise import Tortoise
    
    try:
        validate_database_config()
    except Exception as e:
        log_config.error(f"❌ 数据库配置验证失败: {e}")
        raise
    
    # register_tortoise已经通过_merge_lifespan_context确保Tortoise先初始化
    # 这里只需检查状态并等待连接建立完成
    max_wait = 30.0
    start_wait = time.time()
    
    while not Tortoise._inited:
        elapsed = time.time() - start_wait
        if elapsed > max_wait:
            error_msg = f"Tortoise ORM 初始化超时（{elapsed:.1f}秒）"
            log_config.error(f"❌ {error_msg}")
            raise RuntimeError(error_msg)
        log_config.debug(f"⏳ 等待 Tortoise ORM 初始化... ({elapsed:.1f}s)")
        await asyncio.sleep(0.1)
    
    elapsed = time.time() - start_wait
    log_config.info(f"✅ Tortoise ORM 已初始化（等待{elapsed:.2f}秒）")
    
    # 标记初始化完成
    db_init_manager.mark_initialized()
    
    log_config.set_db_initialized(True)
    log_config.info("✅ 日志数据库写入已启用")
    
    log_config.info("开始预热数据库连接...")
    try:
        await asyncio.wait_for(warmup_connections(), timeout=60)
        log_config.info("数据库连接预热完成")
    except asyncio.TimeoutError:
        log_config.warning("⚠️ 数据库连接预热超时，继续启动其他服务")
    except Exception as e:
        log_config.error(f"❌ 数据库连接预热失败: {e}")
    
    log_config.info("开始启动资源监控...")
    resource_monitor.start_monitoring(interval=30)
    log_config.info("系统资源监控已启动")
    
    log_config.info("等待服务器完全就绪...")
    await asyncio.sleep(1)
    log_config.info("服务器已就绪")
    
    if TURNON_BINLOG_LISTENER:
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
    
    log_config.info("🔹 进入数据库连接检查任务设置阶段...")
    
    # 设置定期检查数据库连接的任务（从原startup_event迁移）
    log_config.info("🔹 定义 schedule_db_checks 函数...")
    async def schedule_db_checks():
        """定期执行数据库连接检查"""
        log_config.info("🔍 数据库连接检查任务开始执行")
        while True:
            try:
                log_config.debug("🔍 开始执行 check_db_connections...")
                # 添加超时保护
                await asyncio.wait_for(check_db_connections(), timeout=30)
                log_config.debug("🔍 check_db_connections 执行完成")
            except asyncio.TimeoutError:
                log_config.warning("⚠️ check_db_connections 执行超时")
            except Exception as e:
                log_config.error(f"❌ check_db_connections 执行失败: {e}")
            # 每300秒（5分钟）检查一次
            await asyncio.sleep(300)

    log_config.info("🔹 schedule_db_checks 函数定义完成")
    
    # 启动数据库连接检查任务（从原startup_event迁移）
    log_config.info("启动数据库连接检查任务...")
    db_check_task = asyncio.create_task(schedule_db_checks())
    log_config.info("数据库连接检查任务已启动")
    
    # 启动连接池监控任务
    log_config.info("启动连接池监控任务...")
    pool_monitor_task = asyncio.create_task(start_pool_monitoring())
    log_config.info("连接池监控任务已启动")
    
    # 启动日志数据库批次刷新任务
    async def schedule_log_db_flush():
        """定期刷新日志数据库批次"""
        from globalobjects.logger.core import SmartLogger
        logger_instance = SmartLogger._instance
        while True:
            try:
                await asyncio.sleep(5)
                if logger_instance and logger_instance._database_handler:
                    handler = logger_instance._database_handler
                    batch_size = len(handler._batch)
                    if batch_size > 0:
                        await handler.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                pass
    
    log_config.info("启动日志数据库批次刷新任务...")
    log_db_flush_task = asyncio.create_task(schedule_log_db_flush())
    log_config.info("日志数据库批次刷新任务已启动")

    # 启动数据库健康检查器（独立后台任务，不依赖前端访问）
    log_config.info("启动数据库健康检查器...")
    try:
        await asyncio.wait_for(start_db_health_checker(), timeout=30)
        log_config.info("数据库健康检查器已启动")
    except asyncio.TimeoutError:
        log_config.warning("⚠️ 数据库健康检查器启动超时")
    except Exception as e:
        log_config.error(f"❌ 数据库健康检查器启动失败: {e}")

    # 启动失败操作恢复管理器（后台自动重试失败的数据库操作）
    log_config.info("启动失败操作恢复管理器...")
    try:
        await asyncio.wait_for(start_failed_operation_recovery(), timeout=30)
        log_config.info("失败操作恢复管理器已启动")
    except asyncio.TimeoutError:
        log_config.warning("⚠️ 失败操作恢复管理器启动超时")
    except Exception as e:
        log_config.error(f"❌ 失败操作恢复管理器启动失败: {e}")

    # 启动实时日志流服务
    log_config.info("启动实时日志流服务...")
    try:
        await asyncio.wait_for(start_log_stream(), timeout=30)
        log_config.info("实时日志流服务已启动")
    except asyncio.TimeoutError:
        log_config.warning("⚠️ 实时日志流服务启动超时")
    except Exception as e:
        log_config.error(f"❌ 实时日志流服务启动失败: {e}")

    # 启动 Redis 健康检查任务
    async def schedule_redis_checks():
        """定期执行 Redis 连接检查"""
        # 系统启动阶段延迟执行，避免与其他服务竞争资源
        await asyncio.sleep(10)
        
        while True:
            try:
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                pool_manager = get_redis_pool_manager()
                is_healthy = pool_manager.is_healthy()
                if is_healthy:
                    log_config.debug("Redis 连接健康")
                else:
                    log_config.warning("Redis 连接不健康，尝试重新初始化")
                    pool_manager._init_pool()
                
                # 检查缓冲大小
                buffer_size = pool_manager.get_buffer_size()
                if buffer_size > 0:
                    log_config.info(f"Redis 本地缓冲中有 {buffer_size} 个事件")
                    # 尝试刷新缓冲
                    flushed = pool_manager.flush_buffer()
                    if flushed > 0:
                        log_config.info(f"成功刷新 {flushed} 个事件到 Redis")
                
                # 获取监控指标并检查是否需要告警
                metrics = pool_manager.get_monitoring_metrics()
                if metrics.get('needs_alert', False):
                    alerts = metrics.get('alerts', [])
                    for alert in alerts:
                        log_config.warning(f"Redis 监控告警: {alert}")
                    # 这里可以添加告警通知逻辑，如发送邮件、短信等
            except Exception as e:
                log_config.error(f"Redis 健康检查失败: {e}")
            
            # 每90秒检查一次，与数据库检查时间错开
            await asyncio.sleep(90)

    # 创建 Redis 健康检查任务
    redis_check_task = asyncio.create_task(schedule_redis_checks())
    log_config.info("Redis 健康检查任务已启动")

    # 启动 Redis 消息消费者（处理来自数据库监听器的事件）
    async def start_redis_consumer():
        """启动 Redis 消息消费者，处理来自数据库监听器的事件"""
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
            loop = asyncio.get_event_loop()

            # 在线程池中获取连接池管理器
            def get_pool_manager():
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                return get_redis_pool_manager()

            pool_manager = await loop.run_in_executor(executor, get_pool_manager)

            # 在线程池中获取 Redis 客户端
            def get_redis_client():
                return pool_manager.get_client()

            redis_client = await loop.run_in_executor(executor, get_redis_client)
            if redis_client is None:
                log_config.error("Redis 连接池获取失败，Redis 消费者无法启动")
                return

            log_config.info(f"Redis 连接已建立，等待事件...")

            while True:
                try:
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

                    for result in events:
                        _, message = result
                        event_data = json.loads(message.decode('utf-8'))
                        event_type = event_data.get('event_type')
                        data = event_data.get('data')
                        log_config.info(f"从消息队列接收到事件: {event_type}")
                        asyncio.create_task(handle_redis_event(event_type, data))
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    log_config.warning(f"Redis 连接断开或超时，尝试重新获取连接: {e}")
                    await asyncio.sleep(1)
                    redis_client = await loop.run_in_executor(executor, get_redis_client)
                    if redis_client is None:
                        log_config.error("Redis 连接获取失败")
                        break
                except Exception as e:
                    log_config.error(f"Redis 消费者处理事件时出错: {e}")
                    await asyncio.sleep(1)
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
                log_config.debug(f"⚠️ 未找到事件处理器: {event_handler_name}")
        except Exception as e:
            log_config.error(f"处理 Redis 事件 {event_type} 时出错: {e}")

    async def cleanup_expired_events():
        """定期清理过期事件"""
        try:
            import concurrent.futures
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            loop = asyncio.get_event_loop()

            # 在线程池中获取连接池管理器
            def get_pool_manager():
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                return get_redis_pool_manager()

            pool_manager = await loop.run_in_executor(executor, get_pool_manager)
            log_config.info("Redis 事件清理任务已启动，每小时清理一次过期事件")

            while True:
                try:
                    # 在线程池中获取 Redis 客户端
                    def get_redis_client():
                        return pool_manager.get_client()

                    redis_client = await loop.run_in_executor(executor, get_redis_client)
                    if redis_client is None:
                        await asyncio.sleep(60)
                        continue

                    # 在线程池中获取列表长度
                    def get_list_length():
                        return redis_client.llen('db_events')

                    length = await loop.run_in_executor(executor, get_list_length)
                    if length > 0:
                        log_config.info(f"开始清理过期事件，当前队列长度: {length}")
                        processed_count = 0
                        expired_count = 0

                        for _ in range(min(length, 1000)):
                            # 在线程池中执行 rpop 操作
                            def rpop():
                                return redis_client.rpop('db_events')

                            event_data = await loop.run_in_executor(executor, rpop)
                            if event_data:
                                processed_count += 1
                                try:
                                    event = json.loads(event_data.decode('utf-8'))
                                    event_timestamp = event.get('timestamp', 0)
                                    if time.time() - event_timestamp <= 86400:
                                        # 在线程池中执行 lpush 操作
                                        def lpush():
                                            return redis_client.lpush('db_events', event_data)
                                        await loop.run_in_executor(executor, lpush)
                                    else:
                                        expired_count += 1
                                except Exception as e:
                                    log_config.debug(f"解析事件失败，跳过: {e}")
                                    expired_count += 1

                        log_config.info(f"事件清理完成，处理了 {processed_count} 个事件，清理了 {expired_count} 个过期事件")
                except (redis.ConnectionError, redis.TimeoutError) as e:
                    log_config.warning(f"Redis 连接断开或超时: {e}")
                    await asyncio.sleep(10)
                except Exception as e:
                    log_config.error(f"清理过期事件失败: {e}")

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
    log_config.info("==================应用启动完成，开始运行==================")
    
    yield  # 应用运行期间
    
    # 应用关闭时执行的操作
    log_config.info("应用关闭中...")
    
    # 0. 关闭数据库连接
    log_config.info("正在关闭数据库连接...")
    try:
        from tortoise import Tortoise
        await Tortoise.close_connections()
        log_config.info("✅ 数据库连接已关闭")
    except Exception as e:
        log_config.warning(f"⚠️ 关闭数据库连接时出错: {e}")
    
    # 1. 先停止 MySQL Binlog 监控（最依赖数据库）
    if TURNON_BINLOG_LISTENER:
        log_config.info("正在停止 MySQL Binlog 监控...")
        binlog_listener.stop_monitoring()
        log_config.info("==================MySQL Binlog监控已停止==================")
    else:
        log_config.debug("⚠️ MySQL Binlog监控未启动，无需停止")

    # 2. 停止 Redis 相关任务
    log_config.info("正在停止 Redis 相关任务...")
    # 在线程池中执行缓冲刷新，避免阻塞事件循环
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop = asyncio.get_event_loop()

    def get_buffer_size():
        from apps.common.utils.redis_pool_manager import get_redis_pool_manager
        return get_redis_pool_manager().get_buffer_size()

    buffer_size = await loop.run_in_executor(executor, get_buffer_size)
    if buffer_size > 0:
        log_config.info(f"发现 {buffer_size} 个事件在本地缓冲中，准备刷新...")

        def flush_buffer():
            from apps.common.utils.redis_pool_manager import flush_event_buffer
            return flush_event_buffer('db_events')

        flushed = await loop.run_in_executor(executor, flush_buffer)
        log_config.info(f"缓冲刷新完成，成功刷新 {flushed} 个事件")
    log_config.info("==================Redis 相关任务已停止==================")

    # 2.1 关闭事件辅助模块（DeadLetter队列等）
    log_config.info("正在关闭事件辅助模块...")
    from apps.common.utils.event_helpers import shutdown_event_helpers
    shutdown_event_helpers()
    log_config.info("==================事件辅助模块已关闭==================")

    # 3. 等待一段时间，确保所有任务完成
    log_config.info("⏳ 等待所有后台任务完成...")
    await asyncio.sleep(5)  # 等待5秒，让所有任务完成

    # 4. 关闭调度器
    if TRUNON_SCHEDULER:
        log_config.info("正在关闭调度器...")
        scheduler_manager.shutdown()
        log_config.info("==================定时任务管理器已关闭==================")
    else:
        log_config.debug("⚠️ 定时任务管理器未启动，无需关闭")
    
    # 5. 停止资源监控
    log_config.info("正在停止资源监控...")
    resource_monitor.stop_monitoring()
    log_config.info("==================系统资源监控已停止==================")
    
    # 6. 停止事件聚合器
    log_config.info("正在停止事件聚合器...")
    log_config.info("==================事件聚合器已停止==================")
    EVENT_AGGREGATOR.stop()
    log_config.info("==================事件聚合器已停止==================")

    # 6.1 关闭事件线程池管理器
    log_config.info("正在关闭事件线程池...")
    from globalobjects.event_aggregator import get_event_pool_manager
    get_event_pool_manager().shutdown_all()
    log_config.info("==================事件线程池已关闭==================")

    # 7. 停止数据库健康检查器
    log_config.info("正在停止数据库健康检查器...")
    await stop_db_health_checker()
    log_config.info("==================数据库健康检查器已停止==================")

    # 8. 停止失败操作恢复管理器
    log_config.info("正在停止OperationRecovery管理器...")
    await stop_failed_operation_recovery()
    log_config.info("==================OperationRecovery管理器已停止==================")

    # 10. 取消后台任务
    if 'db_check_task' in locals():
        log_config.info("正在取消数据库连接检查任务...")
        db_check_task.cancel()
        try:
            await db_check_task
        except asyncio.CancelledError:
            pass
        log_config.info("==================数据库连接检查任务已取消==================")
    
    if 'log_db_flush_task' in locals():
        log_config.info("正在取消日志数据库批次刷新任务...")
        log_db_flush_task.cancel()
        try:
            await log_db_flush_task
        except asyncio.CancelledError:
            pass
        log_config.info("==================日志数据库批次刷新任务已取消==================")

    if 'pool_monitor_task' in locals():
        log_config.info("正在取消连接池监控任务...")
        pool_monitor_task.cancel()
        try:
            await pool_monitor_task
        except asyncio.CancelledError:
            pass
        log_config.info("==================连接池监控任务已取消==================")

    # 取消 Redis 健康检查任务
    if 'redis_check_task' in locals():
        log_config.info("正在取消 Redis 健康检查任务...")
        redis_check_task.cancel()
        try:
            await redis_check_task
        except asyncio.CancelledError:
            pass
        log_config.info("==================Redis 健康检查任务已取消==================")

    # 11. 等待一段时间，确保所有任务真正完成
    log_config.info("⏳ 等待所有任务彻底完成...")
    await asyncio.sleep(3)  # 再等待3秒

    log_config.info("==================应用关闭完成==================")

    # 12. 关闭统一日志系统
    await shutdown_logging()

    # 13. 停止实时日志流服务
    await stop_log_stream()
