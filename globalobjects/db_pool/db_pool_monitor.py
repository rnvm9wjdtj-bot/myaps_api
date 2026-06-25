"""
数据库连接池监控和告警集成

集成泄漏检测监控任务、告警通知机制和后台清理任务。
"""
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from globalobjects.db_pool import (
    BackgroundCleanupTask,
    EnhancedDbManager,
    get_enhanced_db_manager,
    PoolManagerConfig
)
from globalobjects import logger


class PoolMonitorTask:
    """
    连接池监控任务
    
    定期执行泄漏检测、记录使用情况并发送告警。
    """
    
    _instance: Optional['PoolMonitorTask'] = None
    
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
        self._is_running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._connection_names: list = []
        self._monitor_interval = 60  # 监控间隔（秒）
        
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
                
                # 执行监控检查
                await self._perform_monitoring()
                
            except asyncio.CancelledError:
                logger.info("PoolMonitor", "监控循环被取消")
                break
            except Exception as e:
                logger.error("PoolMonitor", f"监控循环异常: {str(e)}")
                await asyncio.sleep(60)
    
    async def _perform_monitoring(self):
        """
        执行监控检查
        """
        for connection_name in self._connection_names:
            try:
                # 获取增强管理器
                manager = get_enhanced_db_manager(connection_name, self._config)
                
                # 记录使用情况
                await manager.record_usage()
                
                # 检测泄漏
                leak_result = await manager.detect_leak()
                
                # 如果检测到泄漏，生成并发送告警
                if leak_result.leak_detected:
                    alert = EnhancedDbManager.get_leak_detector().generate_alert(connection_name, leak_result)
                    if alert:
                        await self._send_alert(alert)
                
            except Exception as e:
                logger.error(
                    "PoolMonitor",
                    f"@{connection_name}",
                    f"监控检查失败: {str(e)}"
                )
    
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
            "connection_names": self._connection_names,
            "cleanup_status": self._cleanup_task.get_status()
        }


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