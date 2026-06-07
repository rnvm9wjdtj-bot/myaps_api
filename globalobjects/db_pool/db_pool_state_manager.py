"""
数据库连接池状态管理器

管理连接池生命周期状态，提供原子性状态标记和并发访问控制。
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any
from globalobjects.db_pool.db_pool_models import (
    ConnectionPoolState,
    ConnectionPoolStateInfo,
    PoolManagerConfig
)
from globalobjects.db_pool.db_pool_exceptions import (
    ConnectionPoolStateError,
    StateTransitionError
)
from globalobjects import logger


class ConnectionPoolStateManager:
    """
    连接池状态管理器
    
    负责管理连接池的生命周期状态，确保状态更新的原子性和一致性。
    使用asyncio.Lock保证并发访问安全。
    """
    
    _instances: Dict[str, 'ConnectionPoolStateManager'] = {}
    
    @classmethod
    def get_instance(cls, connection_name: str, config: Optional[PoolManagerConfig] = None) -> 'ConnectionPoolStateManager':
        """
        获取或创建状态管理器实例（单例模式）
        
        Args:
            connection_name: 连接名称
            config: 配置对象
            
        Returns:
            状态管理器实例
        """
        if connection_name not in cls._instances:
            cls._instances[connection_name] = cls(connection_name, config)
        return cls._instances[connection_name]
    
    @classmethod
    def clear_instance(cls, connection_name: str):
        """
        清除状态管理器实例
        
        Args:
            connection_name: 连接名称
        """
        cls._instances.pop(connection_name, None)
    
    def __init__(self, connection_name: str, config: Optional[PoolManagerConfig] = None):
        """
        初始化状态管理器
        
        Args:
            connection_name: 连接名称
            config: 配置对象
        """
        self._connection_name = connection_name
        self._state = ConnectionPoolState.OPEN
        self._last_update_time: Optional[datetime] = None
        self._update_reason: Optional[str] = None
        self._lock = asyncio.Lock()
        self._state_change_event = asyncio.Event()
        self._config = config or PoolManagerConfig()
        
    @property
    def connection_name(self) -> str:
        """获取连接名称"""
        return self._connection_name
    
    @property
    def state(self) -> ConnectionPoolState:
        """获取当前状态"""
        return self._state
    
    @property
    def is_available(self) -> bool:
        """检查连接池是否可用"""
        return self._state == ConnectionPoolState.OPEN
    
    async def mark_closed(self, reason: str = "manual_close") -> bool:
        """
        标记连接池为已关闭状态
        
        Args:
            reason: 关闭原因
            
        Returns:
            是否成功标记（False表示已经是关闭状态）
            
        Raises:
            StateTransitionError: 状态转换失败
        """
        try:
            async with asyncio.wait_for(
                self._lock.acquire(),
                timeout=self._config.state_lock_timeout
            ):
                if self._state == ConnectionPoolState.CLOSED:
                    logger.debug(
                        "ConnectionPoolState",
                        f"@{self._connection_name}",
                        "已经是关闭状态，跳过标记"
                    )
                    return False
                
                old_state = self._state
                self._state = ConnectionPoolState.CLOSED
                self._last_update_time = datetime.now()
                self._update_reason = reason
                self._state_change_event.set()
                self._state_change_event.clear()
                
                logger.info(
                    "ConnectionPoolState",
                    f"@{self._connection_name}",
                    f"状态变更: {old_state.value} -> CLOSED, 原因: {reason}"
                )
                return True
        except asyncio.TimeoutError:
            logger.error(
                "ConnectionPoolState",
                f"@{self._connection_name}",
                f"获取状态锁超时，无法标记为关闭状态"
            )
            raise StateTransitionError(
                self._connection_name,
                self._state.value,
                ConnectionPoolState.CLOSED.value,
                reason="获取状态锁超时"
            )
        finally:
            if self._lock.locked():
                self._lock.release()
    
    async def mark_open(self, reason: str = "refresh_success") -> bool:
        """
        标记连接池为打开状态
        
        Args:
            reason: 打开原因
            
        Returns:
            是否成功标记（False表示已经是打开状态）
            
        Raises:
            StateTransitionError: 状态转换失败
        """
        try:
            async with asyncio.wait_for(
                self._lock.acquire(),
                timeout=self._config.state_lock_timeout
            ):
                if self._state == ConnectionPoolState.OPEN:
                    logger.debug(
                        "ConnectionPoolState",
                        f"@{self._connection_name}",
                        "已经是打开状态，跳过标记"
                    )
                    return False
                
                old_state = self._state
                self._state = ConnectionPoolState.OPEN
                self._last_update_time = datetime.now()
                self._update_reason = reason
                self._state_change_event.set()
                self._state_change_event.clear()
                
                logger.info(
                    "ConnectionPoolState",
                    f"@{self._connection_name}",
                    f"状态变更: {old_state.value} -> OPEN, 原因: {reason}"
                )
                return True
        except asyncio.TimeoutError:
            logger.error(
                "ConnectionPoolState",
                f"@{self._connection_name}",
                f"获取状态锁超时，无法标记为打开状态"
            )
            raise StateTransitionError(
                self._connection_name,
                self._state.value,
                ConnectionPoolState.OPEN.value,
                reason="获取状态锁超时"
            )
        finally:
            if self._lock.locked():
                self._lock.release()
    
    async def mark_refreshing(self, reason: str = "refresh_start") -> bool:
        """
        标记连接池为刷新中状态
        
        Args:
            reason: 刷新原因
            
        Returns:
            是否成功标记
            
        Raises:
            StateTransitionError: 状态转换失败
        """
        try:
            async with asyncio.wait_for(
                self._lock.acquire(),
                timeout=self._config.state_lock_timeout
            ):
                if self._state == ConnectionPoolState.REFRESHING:
                    logger.debug(
                        "ConnectionPoolState",
                        f"@{self._connection_name}",
                        "已经是刷新中状态，跳过标记"
                    )
                    return False
                
                old_state = self._state
                self._state = ConnectionPoolState.REFRESHING
                self._last_update_time = datetime.now()
                self._update_reason = reason
                self._state_change_event.set()
                self._state_change_event.clear()
                
                logger.info(
                    "ConnectionPoolState",
                    f"@{self._connection_name}",
                    f"状态变更: {old_state.value} -> REFRESHING, 原因: {reason}"
                )
                return True
        except asyncio.TimeoutError:
            logger.error(
                "ConnectionPoolState",
                f"@{self._connection_name}",
                f"获取状态锁超时，无法标记为刷新中状态"
            )
            raise StateTransitionError(
                self._connection_name,
                self._state.value,
                ConnectionPoolState.REFRESHING.value,
                reason="获取状态锁超时"
            )
        finally:
            if self._lock.locked():
                self._lock.release()
    
    def get_state_info(self) -> ConnectionPoolStateInfo:
        """
        获取状态信息
        
        Returns:
            状态信息对象
        """
        return ConnectionPoolStateInfo(
            connection_name=self._connection_name,
            state=self._state,
            last_update_time=self._last_update_time,
            update_reason=self._update_reason,
            is_available=self.is_available
        )
    
    async def wait_for_state(
        self,
        target_state: ConnectionPoolState,
        timeout: float = 10.0
    ) -> bool:
        """
        等待状态变化到目标状态
        
        Args:
            target_state: 目标状态
            timeout: 超时时间（秒）
            
        Returns:
            是否成功等待到目标状态
        """
        if self._state == target_state:
            return True
        
        try:
            async with asyncio.timeout(timeout):
                while True:
                    await self._state_change_event.wait()
                    if self._state == target_state:
                        return True
        except asyncio.TimeoutError:
            logger.warning(
                "ConnectionPoolState",
                f"@{self._connection_name}",
                f"等待状态变化超时: 目标状态={target_state.value}, 当前状态={self._state.value}"
            )
            return False
    
    def reset(self):
        """
        重置状态管理器
        
        将状态重置为初始状态（OPEN）
        """
        self._state = ConnectionPoolState.OPEN
        self._last_update_time = None
        self._update_reason = None
        logger.info(
            "ConnectionPoolState",
            f"@{self._connection_name}",
            "状态已重置为OPEN"
        )
    
    def __repr__(self) -> str:
        return f"ConnectionPoolStateManager(connection_name={self._connection_name}, state={self._state.value})"