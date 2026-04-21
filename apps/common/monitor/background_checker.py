"""
数据库健康检查器 - 后台定时任务模块

提供独立的数据库连接健康检查，不依赖前端访问
"""

import asyncio
import os
import time
from typing import Dict, Any, Optional
from globalobjects import logger as log_config, RemindType, reminder_manager
from .collectors import DatabaseCollector

from .failed_operation_recovery import FailedOperationRecovery


logger = log_config.get_logger(__name__)


class DatabaseHealthChecker:
    """
    数据库健康检查器 - 后台定时任务

    独立于前端 WebSocket 连接，定时检查数据库连接状态
    """

    def __init__(
        self,
        interval: int = 60,
        alert_cooldown: int = 300,
        enabled: bool = True,
        reuse_cache: bool = True,
        cache_threshold: int = 30
    ):
        self._interval = interval
        self._alert_cooldown = alert_cooldown
        self._enabled = enabled
        self._reuse_cache = reuse_cache
        self._cache_threshold = cache_threshold
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._db_collector = DatabaseCollector()

        self._last_alert_time: Dict[str, float] = {}

        self._stats = {
            "check_count": 0,
            "check_success": 0,
            "check_failure": 0,
            "alert_triggered": 0,
            "alert_blocked": 0,
            "cache_hits": 0,
        }

    async def start(self):
        """启动后台检查任务"""
        if not self._enabled:
            logger.info("数据库健康检查器未启用（DB_HEALTH_CHECK_ENABLED=false）")
            return

        if self._running:
            logger.warning("数据库健康检查器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"数据库健康检查器已启动（检查间隔: {self._interval}秒, 告警冷却: {self._alert_cooldown}秒）")

    async def stop(self):
        """停止后台检查任务"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("数据库健康检查器已停止")

    async def check_once(self) -> Dict[str, Any]:
        """立即执行一次检查，返回检查结果"""
        self._stats["check_count"] += 1
        try:
            status = await self._db_collector.get_connection_status()
            self._stats["check_success"] += 1
            return status
        except Exception as e:
            self._stats["check_failure"] += 1
            logger.error(f"数据库健康检查执行失败: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """获取检查统计信息"""
        return {
            **self._stats,
            "running": self._running,
            "interval": self._interval,
            "alert_cooldown": self._alert_cooldown,
        }

    async def _check_loop(self):
        """定时检查循环"""
        logger.info("数据库健康检查循环已启动")
        while self._running:
            try:
                await self._perform_check()
            except Exception as e:
                logger.error(f"数据库健康检查循环异常: {e}")

            await asyncio.sleep(self._interval)

    async def _perform_check(self):
        """执行检查逻辑"""
        self._stats["check_count"] += 1

        try:
            # 添加超时控制，避免健康检查阻塞
            status = await asyncio.wait_for(
                self._db_collector.get_connection_status(),
                timeout=30
            )
            self._stats["check_success"] += 1
        except asyncio.TimeoutError:
            logger.warning("数据库健康检查超时")
            self._stats["check_failure"] += 1
            return
        except Exception as e:
            self._stats["check_failure"] += 1
            logger.error(f"获取数据库连接状态失败: {e}")
            return

        unhealthy_count = status.get("summary", {}).get("unhealthy", 0)

        if unhealthy_count > 0:
            alert_key = f"db_unhealthy_{unhealthy_count}"
            current_time = time.time()
            last_alert = self._last_alert_time.get(alert_key, 0)

            if current_time - last_alert >= self._alert_cooldown:
                await alert_sender.trigger_alert(
                    RemindType.DB_CONNECTION,
                    f"数据库连接异常: {unhealthy_count} 个连接不健康"
                )
                self._last_alert_time[alert_key] = current_time
                self._stats["alert_triggered"] += 1
                logger.warning(f"数据库健康检查触发告警: {unhealthy_count} 个连接不健康")
            else:
                self._stats["alert_blocked"] += 1
                remaining = int(self._alert_cooldown - (current_time - last_alert))
                logger.debug(f"数据库健康检查告警被冷却拦截，剩余 {remaining} 秒")


class FailedOperationRecoveryManager:
    """
    失败操作恢复管理器 - 后台定时任务
    """

    def __init__(
        self,
        interval: int = 30,
        cleanup_days: int = 7,
        enabled: bool = True
    ):
        self._interval = interval
        self._cleanup_days = cleanup_days
        self._enabled = enabled
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._recovery = FailedOperationRecovery

        self._stats = {
            "recovery_count": 0,
            "recovery_success": 0,
            "recovery_failure": 0,
            "cleanup_count": 0,
        }

    async def start(self):
        """启动后台恢复任务"""
        if not self._enabled:
            logger.info("OperationRecovery管理器未启用")
            return

        if self._running:
            logger.warning("OperationRecovery管理器已在运行中")
            return

        self._running = True
        self._task = asyncio.create_task(self._recovery_loop())
        logger.info(f"OperationRecovery管理器已启动（检查间隔: {self._interval}秒）")

    async def stop(self):
        """停止后台恢复任务"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("OperationRecovery管理器已停止")

    def get_stats(self) -> Dict[str, Any]:
        """获取恢复统计信息"""
        return {
            **self._stats,
            "running": self._running,
            "interval": self._interval,
        }

    async def _recovery_loop(self):
        """定时恢复循环"""
        logger.info("OperationRecovery循环已启动")
        cleanup_counter = 0
        
        while self._running:
            try:
                # 处理待重试操作
                processed = await self._recovery.process_pending_operations()
                if processed > 0:
                    self._stats["recovery_count"] += processed
                
                # 每20次循环执行一次清理（大约10分钟）
                cleanup_counter += 1
                if cleanup_counter >= 20:
                    try:
                        cleaned = await self._recovery.cleanup_completed_operations(self._cleanup_days)
                        if cleaned > 0:
                            self._stats["cleanup_count"] += cleaned
                        cleanup_counter = 0
                    except Exception as cleanup_error:
                        logger.error(f"清理操作失败: {cleanup_error}")
                        
            except Exception as e:
                logger.error(f"OperationRecovery循环异常: {e}")

            await asyncio.sleep(self._interval)


# 全局实例
db_health_checker = DatabaseHealthChecker(
    interval=int(os.getenv('DB_HEALTH_CHECK_INTERVAL', '60')),
    alert_cooldown=int(os.getenv('DB_HEALTH_CHECK_COOLDOWN', '300')),
    enabled=os.getenv('DB_HEALTH_CHECK_ENABLED', 'true').lower() == 'true',
)

failed_operation_recovery_manager = FailedOperationRecoveryManager(
    interval=int(os.getenv('FAILED_OP_RECOVERY_INTERVAL', '30')),
    cleanup_days=int(os.getenv('FAILED_OP_CLEANUP_DAYS', '7')),
    enabled=os.getenv('FAILED_OP_RECOVERY_ENABLED', 'true').lower() == 'true',
)


async def start_db_health_checker():
    """启动数据库健康检查器"""
    await db_health_checker.start()


async def stop_db_health_checker():
    """停止数据库健康检查器"""
    await db_health_checker.stop()


async def start_failed_operation_recovery():
    """启动失败操作恢复管理器"""
    await failed_operation_recovery_manager.start()


async def stop_failed_operation_recovery():
    """停止失败操作恢复管理器"""
    await failed_operation_recovery_manager.stop()
