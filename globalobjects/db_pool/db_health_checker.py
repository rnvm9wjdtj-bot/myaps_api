"""
数据库连接健康检查器

执行连接健康检查，职责单一（仅检查不修复），支持超时控制和异常隔离。
"""
import asyncio
import time
from typing import Dict, Optional
from tortoise import Tortoise
from globalobjects.db_pool.db_pool_models import (
    HealthCheckResult,
    PoolManagerConfig
)
from globalobjects.db_pool.db_pool_state_manager import ConnectionPoolStateManager
from globalobjects.db_pool.db_pool_exceptions import (
    HealthCheckError,
    ConnectionPoolUnavailableError
)
from globalobjects import logger


class HealthChecker:
    """
    健康检查器
    
    负责执行数据库连接健康检查，仅检查不修复。
    支持超时控制和异常隔离，支持告警冷却机制避免重复告警。
    """
    
    # 类变量：每个连接的上次告警时间（时间戳）
    _warning_timestamps: Dict[str, float] = {}
    
    # 告警冷却时间（秒）：同一连接的重复告警在此时长内不会重复记录
    WARNING_COOLDOWN = 60
    
    def __init__(
        self,
        connection_name: str,
        state_manager: ConnectionPoolStateManager,
        config: Optional[PoolManagerConfig] = None
    ):
        """
        初始化健康检查器
        
        Args:
            connection_name: 连接名称
            state_manager: 状态管理器
            config: 配置对象
        """
        self._connection_name = connection_name
        self._state_manager = state_manager
        self._config = config or PoolManagerConfig()
    
    def _should_log_warning(self) -> bool:
        """
        检查是否应该记录警告日志（基于冷却机制）
        
        Returns:
            True 如果应该记录，False 如果在冷却期内
        """
        current_time = time.time()
        last_time = self._warning_timestamps.get(self._connection_name, 0)
        
        if current_time - last_time >= self.WARNING_COOLDOWN:
            # 冷却期已过，更新时间戳并允许记录
            self._warning_timestamps[self._connection_name] = current_time
            return True
        return False
    
    def _reset_warning_cooldown(self) -> None:
        """
        重置指定连接的告警冷却时间（当健康检查成功时调用）
        """
        self.__class__.cleanup_warning_timestamps(self._connection_name)
    
    @classmethod
    def cleanup_warning_timestamps(cls, connection_name: str) -> None:
        """
        清理指定连接的告警时间戳记录
        
        当连接被销毁或不再需要监控时调用，防止类级字典内存泄漏。
        
        Args:
            connection_name: 连接名称
        """
        cls._warning_timestamps.pop(connection_name, None)
        
    async def check(self, timeout: Optional[float] = None) -> HealthCheckResult:
        """
        执行健康检查
        
        Args:
            timeout: 超时时间（秒），None则使用配置的默认值
            
        Returns:
            健康检查结果
        """
        if timeout is None:
            timeout = self._config.health_check_timeout
            
        if not self._state_manager.is_available:
            logger.warning(
                "HealthChecker",
                f"@{self._connection_name}",
                "连接池不可用，跳过健康检查"
            )
            return HealthCheckResult(
                is_healthy=False,
                error_message="连接池不可用",
                connection_name=self._connection_name
            )
        
        start_time = time.time()
        
        try:
            conn = Tortoise.get_connection(self._connection_name)
            
            async with asyncio.timeout(timeout):
                await conn.execute_query(self._config.health_check_sql)
            
            response_time = time.time() - start_time
            
            logger.debug(
                "HealthChecker",
                f"@{self._connection_name}",
                f"健康检查成功，响应时间: {response_time:.3f}秒"
            )
            
            # 健康检查成功时，重置告警冷却时间
            self._reset_warning_cooldown()
            
            return HealthCheckResult(
                is_healthy=True,
                response_time=response_time,
                connection_name=self._connection_name
            )
            
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            error_msg = f"健康检查超时（{timeout}秒）"
            
            # 使用冷却机制，避免重复告警
            if self._should_log_warning():
                logger.warning(
                    "HealthChecker",
                    f"@{self._connection_name}",
                    error_msg
                )
            
            return HealthCheckResult(
                is_healthy=False,
                response_time=response_time,
                error_message=error_msg,
                connection_name=self._connection_name
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = f"健康检查失败: {str(e)}"
            
            # 使用冷却机制，避免重复告警
            if self._should_log_warning():
                logger.warning(
                    "HealthChecker",
                    f"@{self._connection_name}",
                    error_msg
                )
            
            return HealthCheckResult(
                is_healthy=False,
                response_time=response_time,
                error_message=error_msg,
                connection_name=self._connection_name
            )
    
    async def check_with_retry(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: Optional[float] = None
    ) -> HealthCheckResult:
        """
        执行带重试的健康检查
        
        Args:
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            timeout: 超时时间（秒）
            
        Returns:
            健康检查结果
        """
        last_result = None
        
        for attempt in range(max_retries + 1):
            result = await self.check(timeout)
            
            if result.is_healthy:
                if attempt > 0:
                    logger.info(
                        "HealthChecker",
                        f"@{self._connection_name}",
                        f"健康检查成功，重试次数: {attempt}"
                    )
                return result
            
            last_result = result
            
            if attempt < max_retries:
                logger.debug(
                    "HealthChecker",
                    f"@{self._connection_name}",
                    f"健康检查失败，{retry_delay}秒后重试（{attempt + 1}/{max_retries}）"
                )
                await asyncio.sleep(retry_delay)
        
        logger.error(
            "HealthChecker",
            f"@{self._connection_name}",
            f"健康检查失败，已重试{max_retries}次"
        )
        
        return last_result
    
    async def check_fast(self) -> HealthCheckResult:
        """
        快速健康检查（使用较短的超时时间）
        
        Returns:
            健康检查结果
        """
        return await self.check(timeout=2.0)