"""
增强的数据库管理器

集成连接池状态管理、健康检查、安全刷新和泄漏检测功能。
"""
import asyncio
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
from tortoise import Tortoise

from globalobjects.db_pool.db_pool_models import (
    HealthCheckResult,
    ConnectionPoolStatus,
    PoolManagerConfig
)
from globalobjects.db_pool.db_pool_state_manager import ConnectionPoolStateManager
from globalobjects.db_pool.db_health_checker import HealthChecker
from globalobjects.db_pool.db_connection_refresher import SafeConnectionRefresher
from globalobjects.db_pool.db_leak_detector import EnhancedConnectionLeakDetector
from globalobjects.db_pool.db_pool_exceptions import ConnectionPoolUnavailableError
from globalobjects import logger


class EnhancedDbManager:
    """
    增强的数据库管理器
    
    集成连接池状态管理、健康检查、安全刷新和泄漏检测功能。
    """
    
    _instances: Dict[str, 'EnhancedDbManager'] = {}
    _leak_detector: Optional[EnhancedConnectionLeakDetector] = None
    
    @classmethod
    def get_instance(
        cls,
        connection_name: str,
        config: Optional[PoolManagerConfig] = None
    ) -> 'EnhancedDbManager':
        """
        获取或创建增强管理器实例（单例模式）
        
        Args:
            connection_name: 连接名称
            config: 配置对象
            
        Returns:
            增强管理器实例
        """
        if connection_name not in cls._instances:
            cls._instances[connection_name] = cls(connection_name, config)
        return cls._instances[connection_name]
    
    @classmethod
    def get_leak_detector(cls) -> EnhancedConnectionLeakDetector:
        """
        获取泄漏检测器实例
        
        Returns:
            泄漏检测器实例
        """
        if cls._leak_detector is None:
            cls._leak_detector = EnhancedConnectionLeakDetector()
        return cls._leak_detector
    
    @classmethod
    def clear_instance(cls, connection_name: str):
        """
        清除增强管理器实例
        
        Args:
            connection_name: 连接名称
        """
        cls._instances.pop(connection_name, None)
        ConnectionPoolStateManager.clear_instance(connection_name)
        HealthChecker.cleanup_warning_timestamps(connection_name)
    
    def __init__(
        self,
        connection_name: str,
        config: Optional[PoolManagerConfig] = None
    ):
        """
        初始化增强管理器
        
        Args:
            connection_name: 连接名称
            config: 配置对象
        """
        self._connection_name = connection_name
        self._config = config or PoolManagerConfig()
        
        self._state_manager = ConnectionPoolStateManager.get_instance(
            connection_name,
            self._config
        )
        
        self._health_checker = HealthChecker(
            connection_name,
            self._state_manager,
            self._config
        )
        
        self._safe_refresher = SafeConnectionRefresher(
            connection_name,
            self._state_manager,
            self._health_checker,
            self._config
        )
        
    @property
    def connection_name(self) -> str:
        """获取连接名称"""
        return self._connection_name
    
    @property
    def state_manager(self) -> ConnectionPoolStateManager:
        """获取状态管理器"""
        return self._state_manager
    
    @property
    def health_checker(self) -> HealthChecker:
        """获取健康检查器"""
        return self._health_checker
    
    @property
    def safe_refresher(self) -> SafeConnectionRefresher:
        """获取安全刷新器"""
        return self._safe_refresher
    
    @asynccontextmanager
    async def get_connection(self):
        """
        获取数据库连接（增强版）
        
        在返回连接前检查连接池状态，确保连接池可用。
        
        Yields:
            数据库连接对象
            
        Raises:
            ConnectionPoolUnavailableError: 连接池不可用
        """
        if not self._state_manager.is_available:
            logger.warning(
                "EnhancedDbManager",
                f"@{self._connection_name}",
                "连接池不可用，拒绝获取连接"
            )
            raise ConnectionPoolUnavailableError(
                self._connection_name,
                reason="连接池已关闭或正在刷新"
            )
        
        try:
            conn = Tortoise.get_connection(self._connection_name)
            yield conn
        except Exception as e:
            logger.error(
                "EnhancedDbManager",
                f"@{self._connection_name}",
                f"获取连接时出错: {str(e)}"
            )
            raise
    
    async def check_health(self, timeout: Optional[float] = None, force: bool = False) -> HealthCheckResult:
        """
        检查连接健康状态
        
        Args:
            timeout: 超时时间（秒）
            force: 是否强制执行（绕过连接池状态检查）。
                用于刷新流程内部验证刚重建的连接。
            
        Returns:
            健康检查结果
        """
        return await self._health_checker.check(timeout, force=force)
    
    async def refresh_connection(self, fast_mode: bool = False) -> bool:
        """
        刷新连接（安全版）
        
        Args:
            fast_mode: 是否使用快速模式
            
        Returns:
            是否刷新成功
        """
        return await self._safe_refresher.refresh(fast_mode)
    
    async def get_connection_pool_status(self) -> ConnectionPoolStatus:
        """
        获取连接池状态
        
        Returns:
            连接池状态
        """
        try:
            conn = Tortoise.get_connection(self._connection_name)
            
            if not conn:
                return ConnectionPoolStatus(
                    connection_name=self._connection_name,
                    pool_available=False
                )
            
            used_connections = 0
            idle_connections = 0
            total_connections = 0
            
            if hasattr(conn, '_pool') and conn._pool:
                pool = conn._pool
                
                if hasattr(pool, '_used'):
                    used_connections = len(pool._used)
                if hasattr(pool, '_idle'):
                    idle_connections = len(pool._idle)
                if hasattr(pool, '_connections'):
                    total_connections = len(pool._connections)
            
            usage_rate = 0.0
            if total_connections > 0:
                usage_rate = (used_connections / total_connections) * 100
            
            return ConnectionPoolStatus(
                connection_name=self._connection_name,
                total_connections=total_connections,
                used_connections=used_connections,
                idle_connections=idle_connections,
                usage_rate=usage_rate,
                pool_available=self._state_manager.is_available
            )
            
        except Exception as e:
            logger.error(
                "EnhancedDbManager",
                f"@{self._connection_name}",
                f"获取连接池状态时出错: {str(e)}"
            )
            return ConnectionPoolStatus(
                connection_name=self._connection_name,
                pool_available=False
            )
    
    async def record_usage(self):
        """
        记录连接使用情况（用于泄漏检测）
        """
        pool_status = await self.get_connection_pool_status()
        health_result = await self.check_health()
        
        leak_detector = self.get_leak_detector()
        leak_detector.record_usage(
            self._connection_name,
            pool_status,
            health_result.is_healthy
        )
    
    async def detect_leak(self):
        """
        检测连接泄漏
        """
        leak_detector = self.get_leak_detector()
        return leak_detector.detect_leak(self._connection_name)
    
    def get_state_info(self):
        """
        获取状态信息
        """
        return self._state_manager.get_state_info()
    
    def __repr__(self) -> str:
        return f"EnhancedDbManager(connection_name={self._connection_name}, state={self._state_manager.state.value})"


def get_enhanced_db_manager(
    connection_name: str,
    config: Optional[PoolManagerConfig] = None
) -> EnhancedDbManager:
    """
    获取增强的数据库管理器实例

    Args:
        connection_name: 连接名称
        config: 配置对象，不传时使用 get_cached_config()（环境变量配置），
            避免 PoolManagerConfig() 字段默认值与 get_pool_config() 不一致
            导致健康检查超时等参数分叉

    Returns:
        增强的数据库管理器实例
    """
    if config is None:
        from globalobjects.db_pool.config import get_cached_config
        config = get_cached_config()
    return EnhancedDbManager.get_instance(connection_name, config)