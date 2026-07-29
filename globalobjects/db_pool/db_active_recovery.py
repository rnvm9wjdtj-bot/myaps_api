"""
主动连接回收和智能恢复引擎

实现主动扫描泄漏连接、智能恢复策略和自适应调整。
"""
import asyncio
import os
import time
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum
from globalobjects.db_pool.db_pool_models import PoolManagerConfig
from globalobjects.db_pool.db_enhanced_manager import get_enhanced_db_manager
from globalobjects import logger


class RecoveryStrategy(str, Enum):
    """恢复策略枚举"""
    FAST_REFRESH = "fast_refresh"  # 快速刷新（0.5秒等待）
    FULL_REFRESH = "full_refresh"  # 完整刷新（1秒等待）
    REBUILD_POOL = "rebuild_pool"  # 重建连接池
    GRACEFUL_RESTART = "graceful_restart"  # 优雅重启


class RecoveryPriority(str, Enum):
    """恢复优先级"""
    LOW = "low"  # 低优先级，可以等待
    MEDIUM = "medium"  # 中优先级，尽快恢复
    HIGH = "high"  # 高优先级，立即恢复
    CRITICAL = "critical"  # 关键，强制恢复


class RecoveryStats:
    """恢复统计"""
    
    def __init__(self):
        self.total_attempts = 0
        self.successful_recoveries = 0
        self.failed_recoveries = 0
        self.last_recovery_time: Optional[datetime] = None
        self.recovery_history: List[Dict] = []
    
    def record_attempt(self, success: bool, strategy: RecoveryStrategy, duration: float):
        """记录恢复尝试"""
        self.total_attempts += 1
        if success:
            self.successful_recoveries += 1
        else:
            self.failed_recoveries += 1
        
        self.last_recovery_time = datetime.now()
        
        self.recovery_history.append({
            "timestamp": self.last_recovery_time.isoformat(),
            "success": success,
            "strategy": strategy.value,
            "duration": duration
        })
        
        if len(self.recovery_history) > 100:
            self.recovery_history.pop(0)
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_attempts == 0:
            return 0.0
        return self.successful_recoveries / self.total_attempts


class ActiveConnectionRecovery:
    """
    主动连接回收和智能恢复引擎
    
    功能：
    1. 主动扫描连接池中的僵尸连接
    2. 智能恢复策略（渐进式重试、指数退避）
    3. 自适应调整恢复参数
    4. 分级告警和恢复
    """
    
    _instance: Optional['ActiveConnectionRecovery'] = None
    
    @classmethod
    def get_instance(cls, config: Optional[PoolManagerConfig] = None) -> 'ActiveConnectionRecovery':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def __init__(self, config: Optional[PoolManagerConfig] = None):
        """初始化主动恢复引擎"""
        self._config = config or PoolManagerConfig()
        self._recovery_stats: Dict[str, RecoveryStats] = {}
        self._recovery_locks: Dict[str, asyncio.Lock] = {}
        self._last_recovery_attempt: Dict[str, float] = {}
        self._recovery_backoff: Dict[str, float] = {}
        
        self._is_running = False
        self._recovery_task: Optional[asyncio.Task] = None
        
        # 从环境变量读取配置，支持自定义
        self._max_recovery_attempts = int(os.getenv("DBPOOL_MAX_RECOVERY_ATTEMPTS", "5"))
        self._base_backoff = float(os.getenv("DBPOOL_BASE_BACKOFF", "5.0"))
        self._max_backoff = float(os.getenv("DBPOOL_MAX_BACKOFF", "300.0"))
    
    async def start(self):
        """启动主动恢复引擎"""
        if self._is_running:
            logger.warning("ActiveRecovery", "主动恢复引擎已在运行")
            return
        
        self._is_running = True
        self._recovery_task = asyncio.create_task(self._recovery_loop())
        
        logger.info(
            "ActiveRecovery",
            f"主动恢复引擎已启动，扫描间隔: {self._config.cleanup_interval}秒"
        )
    
    async def stop(self):
        """停止主动恢复引擎"""
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
            self._recovery_task = None
        
        logger.info("ActiveRecovery", "主动恢复引擎已停止")
    
    async def _recovery_loop(self):
        """恢复循环"""
        while self._is_running:
            try:
                await asyncio.sleep(self._config.cleanup_interval)
                
                await self._scan_and_recover()
                
            except asyncio.CancelledError:
                logger.info("ActiveRecovery", "恢复循环被取消")
                break
            except Exception as e:
                logger.error("ActiveRecovery", f"恢复循环异常: {str(e)}")
                await asyncio.sleep(60)
    
    async def _scan_and_recover(self):
        """扫描并恢复所有连接"""
        for connection_name in self._recovery_stats:
            try:
                manager = get_enhanced_db_manager(connection_name, self._config)
                
                pool_status = await manager.get_connection_pool_status()
                
                if not pool_status.pool_available:
                    await self._attempt_recovery(
                        connection_name,
                        RecoveryPriority.HIGH,
                        reason="连接池不可用"
                    )
                    continue
                
                if pool_status.usage_rate >= 95:
                    await self._attempt_recovery(
                        connection_name,
                        RecoveryPriority.CRITICAL,
                        reason=f"连接使用率过高: {pool_status.usage_rate:.1f}%"
                    )
                    continue

            except Exception as e:
                logger.error(
                    "ActiveRecovery",
                    f"@{connection_name}",
                    f"扫描恢复失败: {str(e)}"
                )
    
    async def _attempt_recovery(
        self,
        connection_name: str,
        priority: RecoveryPriority,
        reason: str
    ) -> bool:
        """
        尝试恢复连接
        
        Args:
            connection_name: 连接名称
            priority: 恢复优先级
            reason: 恢复原因
            
        Returns:
            是否恢复成功
        """
        if connection_name not in self._recovery_locks:
            self._recovery_locks[connection_name] = asyncio.Lock()
        
        async with self._recovery_locks[connection_name]:
            if not self._should_attempt_recovery(connection_name, priority):
                logger.debug(
                    "ActiveRecovery",
                    f"@{connection_name}",
                    f"恢复尝试被退避策略阻止: {reason}"
                )
                return False
            
            strategy = self._select_recovery_strategy(priority)
            
            logger.info(
                "ActiveRecovery",
                f"@{connection_name}",
                f"开始恢复: 策略={strategy.value}, 优先级={priority.value}, 原因={reason}"
            )
            
            start_time = time.time()
            success = False
            
            try:
                success = await self._execute_recovery_strategy(connection_name, strategy)
                
                duration = time.time() - start_time
                
                self._record_recovery_result(connection_name, success, strategy, duration)
                
                if success:
                    self._reset_backoff(connection_name)
                    logger.info(
                        "ActiveRecovery",
                        f"@{connection_name}",
                        f"恢复成功: 策略={strategy.value}, 耗时={duration:.2f}秒"
                    )
                else:
                    self._increase_backoff(connection_name)
                    logger.warning(
                        "ActiveRecovery",
                        f"@{connection_name}",
                        f"恢复失败: 策略={strategy.value}, 耗时={duration:.2f}秒"
                    )
                
            except Exception as e:
                duration = time.time() - start_time
                self._record_recovery_result(connection_name, False, strategy, duration)
                self._increase_backoff(connection_name)
                
                logger.error(
                    "ActiveRecovery",
                    f"@{connection_name}",
                    f"恢复异常: {str(e)}"
                )
            
            return success
    
    def _should_attempt_recovery(self, connection_name: str, priority: RecoveryPriority) -> bool:
        """
        判断是否应该尝试恢复（基于退避策略）
        
        Args:
            connection_name: 连接名称
            priority: 恢复优先级
            
        Returns:
            是否应该尝试
        """
        current_time = time.time()
        last_attempt = self._last_recovery_attempt.get(connection_name, 0)
        backoff = self._recovery_backoff.get(connection_name, self._base_backoff)
        
        if priority == RecoveryPriority.CRITICAL:
            return True
        
        if priority == RecoveryPriority.HIGH:
            backoff = backoff * 0.5
        elif priority == RecoveryPriority.LOW:
            backoff = backoff * 2.0
        
        if current_time - last_attempt < backoff:
            return False
        
        return True
    
    def _select_recovery_strategy(self, priority: RecoveryPriority) -> RecoveryStrategy:
        """
        选择恢复策略
        
        Args:
            priority: 恢复优先级
            
        Returns:
            恢复策略
        """
        strategy_map = {
            RecoveryPriority.LOW: RecoveryStrategy.FAST_REFRESH,
            RecoveryPriority.MEDIUM: RecoveryStrategy.FULL_REFRESH,
            RecoveryPriority.HIGH: RecoveryStrategy.REBUILD_POOL,
            RecoveryPriority.CRITICAL: RecoveryStrategy.GRACEFUL_RESTART
        }
        
        return strategy_map.get(priority, RecoveryStrategy.FULL_REFRESH)
    
    async def _execute_recovery_strategy(
        self,
        connection_name: str,
        strategy: RecoveryStrategy
    ) -> bool:
        """
        执行恢复策略
        
        Args:
            connection_name: 连接名称
            strategy: 恢复策略
            
        Returns:
            是否成功
        """
        manager = get_enhanced_db_manager(connection_name, self._config)
        
        if strategy == RecoveryStrategy.FAST_REFRESH:
            return await manager.refresh_connection(fast_mode=True)
        
        elif strategy == RecoveryStrategy.FULL_REFRESH:
            return await manager.refresh_connection(fast_mode=False)
        
        elif strategy == RecoveryStrategy.REBUILD_POOL:
            return await self._rebuild_connection_pool(connection_name)
        
        elif strategy == RecoveryStrategy.GRACEFUL_RESTART:
            return await self._graceful_restart(connection_name)
        
        return False
    
    async def _rebuild_connection_pool(self, connection_name: str) -> bool:
        """
        重建连接池
        
        使用增强管理器的安全刷新机制，而非直接操作池内部状态，
        避免绕过连接池的状态管理导致连接泄漏。
        
        Args:
            connection_name: 连接名称
            
        Returns:
            是否成功
        """
        manager = get_enhanced_db_manager(connection_name, self._config)
        
        # 先执行一次完整刷新，等待池关闭稳定
        success = await manager.refresh_connection(fast_mode=False)
        if success:
            logger.info(
                "ActiveRecovery",
                f"@{connection_name}",
                "连接池重建成功"
            )
            return True
        
        # 如果刷新失败，延长等待时间再重试一次
        logger.warning(
            "ActiveRecovery",
            f"@{connection_name}",
            "首次刷新失败，延长等待后重试"
        )
        await asyncio.sleep(2.0)
        return await manager.refresh_connection(fast_mode=False)
    
    async def _graceful_restart(self, connection_name: str) -> bool:
        """
        优雅重启（多次安全刷新重试）
        
        使用增强管理器的安全刷新机制，避免直接操作池内部状态。
        
        Args:
            connection_name: 连接名称
            
        Returns:
            是否成功
        """
        manager = get_enhanced_db_manager(connection_name, self._config)
        
        for attempt in range(3):
            try:
                success = await manager.refresh_connection(fast_mode=False)
                
                if success:
                    return True
                
                wait_time = (attempt + 1) * 5.0
                logger.warning(
                    "ActiveRecovery",
                    f"@{connection_name}",
                    f"优雅重启失败，{wait_time}秒后重试（{attempt + 1}/3）"
                )
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(
                    "ActiveRecovery",
                    f"@{connection_name}",
                    f"优雅重启异常: {str(e)}"
                )
        
        return False
    
    def _record_recovery_result(
        self,
        connection_name: str,
        success: bool,
        strategy: RecoveryStrategy,
        duration: float
    ):
        """记录恢复结果"""
        if connection_name not in self._recovery_stats:
            self._recovery_stats[connection_name] = RecoveryStats()
        
        self._recovery_stats[connection_name].record_attempt(success, strategy, duration)
        self._last_recovery_attempt[connection_name] = time.time()
    
    def _reset_backoff(self, connection_name: str):
        """重置退避时间"""
        self._recovery_backoff[connection_name] = self._base_backoff
    
    def _increase_backoff(self, connection_name: str):
        """增加退避时间（指数退避）"""
        current_backoff = self._recovery_backoff.get(connection_name, self._base_backoff)
        new_backoff = min(current_backoff * 2.0, self._max_backoff)
        self._recovery_backoff[connection_name] = new_backoff
        
        logger.debug(
            "ActiveRecovery",
            f"@{connection_name}",
            f"退避时间增加: {current_backoff:.1f}秒 -> {new_backoff:.1f}秒"
        )
    
    def register_connection(self, connection_name: str):
        """注册需要监控的连接"""
        if connection_name not in self._recovery_stats:
            self._recovery_stats[connection_name] = RecoveryStats()
            self._recovery_locks[connection_name] = asyncio.Lock()
            self._recovery_backoff[connection_name] = self._base_backoff
            
            logger.info(
                "ActiveRecovery",
                f"@{connection_name}",
                "已注册到主动恢复引擎"
            )
    
    def get_recovery_stats(self, connection_name: str) -> Optional[Dict]:
        """获取恢复统计"""
        if connection_name in self._recovery_stats:
            stats = self._recovery_stats[connection_name]
            return {
                "total_attempts": stats.total_attempts,
                "successful_recoveries": stats.successful_recoveries,
                "failed_recoveries": stats.failed_recoveries,
                "success_rate": stats.success_rate,
                "last_recovery_time": stats.last_recovery_time.isoformat() if stats.last_recovery_time else None,
                "recovery_history": stats.recovery_history[-10:],
                "current_backoff": self._recovery_backoff.get(connection_name, self._base_backoff)
            }
        return None
    
    def get_status(self) -> Dict:
        """获取引擎状态"""
        return {
            "is_running": self._is_running,
            "registered_connections": list(self._recovery_stats.keys()),
            "connection_stats": {
                name: self.get_recovery_stats(name)
                for name in self._recovery_stats.keys()
            }
        }