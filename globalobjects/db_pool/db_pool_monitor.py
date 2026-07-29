"""
数据库连接池监控和告警集成

集成泄漏检测监控任务、告警通知机制和后台清理任务。
支持自动恢复检测：当数据库服务恢复后，自动刷新连接池恢复服务。
"""
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from tortoise import Tortoise
from globalobjects.db_pool import (
    BackgroundCleanupTask,
    EnhancedDbManager,
    get_enhanced_db_manager,
    PoolManagerConfig
)
from globalobjects.db_pool.db_active_recovery import ActiveConnectionRecovery
from globalobjects import logger


class PoolMonitorTask:
    """
    连接池监控任务
    
    定期执行泄漏检测、记录使用情况并发送告警。
    支持告警冷却机制和动态监控间隔。
    """
    
    _instance: Optional['PoolMonitorTask'] = None
    
    MIN_MONITOR_INTERVAL = 60
    MAX_MONITOR_INTERVAL = 300
    INTERVAL_ADJUST_STEP = 30
    
    @classmethod
    def get_instance(cls, config: Optional[PoolManagerConfig] = None) -> 'PoolMonitorTask':
        """
        获取单例实例
        
        Args:
            config: 配置对象
            
        Returns:
            监控任务实例
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def __init__(self, config: Optional[PoolManagerConfig] = None):
        """
        初始化监控任务
        
        Args:
            config: 配置对象
        """
        self._config = config or PoolManagerConfig()
        self._cleanup_task = BackgroundCleanupTask.get_instance(self._config)
        self._active_recovery = ActiveConnectionRecovery.get_instance(self._config)
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._connection_names: list = []
        self._monitor_interval = self.MIN_MONITOR_INTERVAL
        self._last_health_status: Dict[str, bool] = {}
    
    def _update_monitor_interval(self):
        """
        根据健康状态动态调整监控间隔
        
        当所有连接都健康时，使用最小间隔；
        当有连接不健康时，逐渐增加间隔避免日志风暴。
        """
        if not self._last_health_status:
            self._monitor_interval = self.MIN_MONITOR_INTERVAL
            return
        
        all_healthy = all(self._last_health_status.values())
        
        if all_healthy:
            self._monitor_interval = max(
                self.MIN_MONITOR_INTERVAL,
                self._monitor_interval - self.INTERVAL_ADJUST_STEP
            )
        else:
            self._monitor_interval = min(
                self.MAX_MONITOR_INTERVAL,
                self._monitor_interval + self.INTERVAL_ADJUST_STEP
            )
        
    async def start(self, connection_names: list):
        """
        启动监控任务
        
        Args:
            connection_names: 要监控的连接名称列表
        """
        if self._is_running:
            logger.warning("PoolMonitor", "监控任务已在运行")
            return
        
        self._connection_names = connection_names
        self._is_running = True
        
        # 启动后台清理任务
        await self._cleanup_task.start()
        
        # 启动主动恢复引擎
        for conn_name in connection_names:
            self._active_recovery.register_connection(conn_name)
        await self._active_recovery.start()
        
        # 启动监控循环
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info(
            "PoolMonitor",
            f"监控任务已启动，监控连接: {connection_names}，间隔: {self._monitor_interval}秒"
        )
    
    async def stop(self):
        """
        停止监控任务
        """
        if not self._is_running:
            return
        
        self._is_running = False
        
        # 停止监控循环
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        
        # 停止主动恢复引擎
        await self._active_recovery.stop()
        
        # 停止后台清理任务
        await self._cleanup_task.stop()
        
        logger.info("PoolMonitor", "监控任务已停止")
    
    async def _monitor_loop(self):
        """
        监控循环
        """
        while self._is_running:
            try:
                await asyncio.sleep(self._monitor_interval)
                
                await self._perform_monitoring()
                
                self._update_monitor_interval()
                
            except asyncio.CancelledError:
                logger.info("PoolMonitor", "监控循环被取消")
                break
            except Exception as e:
                logger.error("PoolMonitor", f"监控循环异常: {str(e)}")
                await asyncio.sleep(60)
    
    async def _perform_monitoring(self):
        """
        执行监控检查
        
        当检测到连接从不可用变为可用时，自动触发连接刷新恢复服务。
        """
        for connection_name in self._connection_names:
            try:
                manager = get_enhanced_db_manager(connection_name, self._config)
                
                # 记录之前的状态，用于判断是否发生了状态变化
                was_previously_unhealthy = not self._last_health_status.get(connection_name, True)
                
                # 记录使用情况并检测泄漏
                await manager.record_usage()
                leak_result = await manager.detect_leak()
                
                # 通过标准健康检查获取状态（当池状态为CLOSED时会直接返回不可用）
                health_result = await manager.check_health()
                current_healthy = health_result.is_healthy
                
                # === 自动恢复检测 ===
                # 如果之前不健康且标准检查仍然不健康，尝试直接连接数据库
                # 绕过状态管理器的检查，检测数据库是否已实际恢复
                if was_previously_unhealthy and not current_healthy:
                    recovered = await self._try_direct_health_check(connection_name)
                    if recovered:
                        logger.info(
                            "PoolMonitor",
                            f"@{connection_name}",
                            "检测到数据库服务已恢复，正在刷新连接池..."
                        )
                        try:
                            refresh_success = await manager.refresh_connection(fast_mode=True)
                            if refresh_success:
                                logger.info(
                                    "PoolMonitor",
                                    f"@{connection_name}",
                                    "连接池自动恢复成功"
                                )
                                current_healthy = True
                            else:
                                logger.warning(
                                    "PoolMonitor",
                                    f"@{connection_name}",
                                    "连接池刷新失败，将下次重试"
                                )
                        except Exception as refresh_e:
                            logger.error(
                                "PoolMonitor",
                                f"@{connection_name}",
                                f"连接池刷新异常: {str(refresh_e)}"
                            )
                
                self._last_health_status[connection_name] = current_healthy
                
                # 告警处理
                if leak_result.leak_detected:
                    if EnhancedDbManager.get_leak_detector()._should_log_alert(connection_name):
                        alert = EnhancedDbManager.get_leak_detector().generate_alert(connection_name, leak_result)
                        if alert:
                            await self._send_alert(alert)
                    else:
                        logger.debug(
                            "PoolMonitor",
                            f"@{connection_name}",
                            f"告警在冷却期内，跳过发送: {leak_result.severity.value}"
                        )
                
            except Exception as e:
                self._last_health_status[connection_name] = False
                logger.error(
                    "PoolMonitor",
                    f"@{connection_name}",
                    f"监控检查失败: {str(e)}"
                )
    
    async def _try_direct_health_check(self, connection_name: str) -> bool:
        """
        直接尝试数据库连接，绕过状态管理器检查
        
        用于检测数据库服务是否已从故障中恢复。
        
        Args:
            connection_name: 连接名称
            
        Returns:
            True 如果数据库连接成功
        """
        try:
            conn = Tortoise.get_connection(connection_name)
            if not conn:
                return False
            
            await asyncio.wait_for(conn.execute_query(self._config.health_check_sql), timeout=self._config.health_check_timeout)
            
            return True
        except asyncio.TimeoutError:
            logger.debug(
                "PoolMonitor",
                f"@{connection_name}",
                "直接健康检查超时，数据库可能仍未恢复"
            )
            return False
        except Exception as e:
            logger.debug(
                "PoolMonitor",
                f"@{connection_name}",
                f"直接健康检查失败: {str(e)}"
            )
            return False
    
    async def _send_alert(self, alert: Any):
        """
        发送告警
        
        Args:
            alert: 告警消息对象
        """
        # 记录到日志
        log_level = "warning" if alert.alert_level.value == "warning" else "error"
        getattr(logger, log_level)(
            "PoolMonitor",
            f"@{alert.connection_name}",
            f"告警: {alert.message}"
        )
        
        # TODO: 可以扩展为发送到外部监控系统
        # 例如：Prometheus、Grafana、钉钉、邮件等
        # await self._send_to_prometheus(alert)
        # await self._send_to_dingtalk(alert)
        # await self._send_email(alert)
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取监控状态
        
        Returns:
            状态信息
        """
        return {
            "is_running": self._is_running,
            "monitor_interval": self._monitor_interval,
            "min_interval": self.MIN_MONITOR_INTERVAL,
            "max_interval": self.MAX_MONITOR_INTERVAL,
            "connection_names": self._connection_names,
            "health_status": self._last_health_status,
            "cleanup_status": self._cleanup_task.get_status(),
            "active_recovery_status": self._active_recovery.get_status()
        }
    
    @classmethod
    def cleanup_alert_timestamps(cls, connection_name: str = None):
        """
        清理告警时间戳记录
        
        委托给泄漏检测器的冷却管理，确保冷却状态集中管理。
        
        Args:
            connection_name: 连接名称（None则清空所有）
        """
        EnhancedDbManager.get_leak_detector().cleanup_alert_timestamps(connection_name)


async def start_pool_monitoring(connection_names: list, config: Optional[PoolManagerConfig] = None):
    """
    启动连接池监控（便捷函数）
    
    Args:
        connection_names: 要监控的连接名称列表
        config: 配置对象
    """
    monitor = PoolMonitorTask.get_instance(config)
    await monitor.start(connection_names)


async def stop_pool_monitoring():
    """
    停止连接池监控（便捷函数）
    """
    monitor = PoolMonitorTask.get_instance()
    await monitor.stop()


def get_pool_monitor_status() -> Dict[str, Any]:
    """
    获取监控状态（便捷函数）
    
    Returns:
        状态信息
    """
    monitor = PoolMonitorTask.get_instance()
    return monitor.get_status()