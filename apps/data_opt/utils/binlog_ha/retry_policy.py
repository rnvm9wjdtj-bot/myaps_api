"""
Binlog 监听器 - 重试策略管理器

提供指数退避重试机制，支持错误类型分类
"""
import asyncio
import random
import time
from typing import Callable, Optional, TypeVar, Any
from functools import wraps

from .models import ErrorType
from globalobjects import logger

T = TypeVar('T')


class RetryPolicy:
    """重试策略管理器"""
    
    ERROR_TYPE_BASE_DELAY = {
        ErrorType.NETWORK_TIMEOUT: 5.0,
        ErrorType.TEMPORARY_ERROR: 1.0,
        ErrorType.RESOURCE_LIMIT: 2.0,
    }
    
    def __init__(
        self,
        max_attempts: int = 10,
        base_delay: float = 5.0,
        max_delay: float = 300.0,
        jitter_factor: float = 0.2
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter_factor = jitter_factor
        self._attempt_count = 0
    
    def calculate_delay(self, attempt: int, error_type: Optional[ErrorType] = None) -> float:
        """
        计算重试延迟（指数退避 + 抖动）
        
        公式：delay = min(base_delay × 2^attempt × (1 ± jitter), max_delay)
        
        Args:
            attempt: 当前重试次数（从0开始）
            error_type: 错误类型（影响基础延迟）
        
        Returns:
            重试延迟时间（秒）
        """
        base = self.ERROR_TYPE_BASE_DELAY.get(error_type, self.base_delay)
        
        delay = base * (2 ** attempt)
        
        jitter = random.uniform(1 - self.jitter_factor, 1 + self.jitter_factor)
        delay = delay * jitter
        
        delay = min(delay, self.max_delay)
        
        return delay
    
    def classify_error(self, exception: Exception) -> ErrorType:
        """
        分类错误类型
        
        Args:
            exception: 异常对象
        
        Returns:
            错误类型枚举
        """
        error_str = str(exception).lower()
        error_type_name = type(exception).__name__.lower()
        
        if any(keyword in error_str for keyword in ['timeout', 'timed out', 'connection timeout']):
            return ErrorType.NETWORK_TIMEOUT
        
        if any(keyword in error_str for keyword in ['resource', 'limit', 'quota', 'too many']):
            return ErrorType.RESOURCE_LIMIT
        
        if any(keyword in error_type_name for keyword in ['connectionerror', 'connectionrefusederror']):
            return ErrorType.NETWORK_TIMEOUT
        
        if any(keyword in error_type_name for keyword in ['valueerror', 'typeerror', 'keyerror']):
            return ErrorType.PERMANENT_ERROR
        
        return ErrorType.TEMPORARY_ERROR
    
    def should_retry(self, attempt: int, error_type: ErrorType) -> bool:
        """
        判断是否应重试
        
        Args:
            attempt: 当前重试次数
            error_type: 错误类型
        
        Returns:
            是否应继续重试
        """
        if error_type == ErrorType.PERMANENT_ERROR:
            return False
        
        return attempt < self.max_attempts
    
    async def execute_with_retry(
        self,
        operation: Callable[..., T],
        *args,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ) -> T:
        """
        带重试的异步执行包装器
        
        Args:
            operation: 要执行的异步操作
            on_retry: 重试回调函数
            *args, **kwargs: 操作参数
        
        Returns:
            操作结果
        
        Raises:
            Exception: 达到最大重试次数后抛出最后一次异常
        """
        last_exception = None
        
        for attempt in range(self.max_attempts + 1):
            try:
                if asyncio.iscoroutinefunction(operation):
                    return await operation(*args, **kwargs)
                else:
                    return operation(*args, **kwargs)
                    
            except Exception as e:
                last_exception = e
                error_type = self.classify_error(e)
                
                if not self.should_retry(attempt, error_type):
                    logger.error(f"❌ 操作执行失败（不重试）: {error_type.value} - {e}")
                    raise
                
                delay = self.calculate_delay(attempt, error_type)
                
                if attempt < self.max_attempts:
                    logger.warning(
                        f"⚠️ 操作执行失败，{attempt + 1}/{self.max_attempts} 重试 "
                        f"({delay:.2f}s后): {error_type.value} - {e}"
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    await asyncio.sleep(delay)
        
        logger.error(f"❌ 操作执行失败，已达最大重试次数: {last_exception}")
        raise last_exception
    
    def execute_with_retry_sync(
        self,
        operation: Callable[..., T],
        *args,
        on_retry: Optional[Callable[[int, Exception], None]] = None,
        **kwargs
    ) -> T:
        """
        带重试的同步执行包装器
        
        Args:
            operation: 要执行的同步操作
            on_retry: 重试回调函数
            *args, **kwargs: 操作参数
        
        Returns:
            操作结果
        """
        last_exception = None
        
        for attempt in range(self.max_attempts + 1):
            try:
                return operation(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                error_type = self.classify_error(e)
                
                if not self.should_retry(attempt, error_type):
                    logger.error(f"❌ 操作执行失败（不重试）: {error_type.value} - {e}")
                    raise
                
                delay = self.calculate_delay(attempt, error_type)
                
                if attempt < self.max_attempts:
                    logger.warning(
                        f"⚠️ 操作执行失败，{attempt + 1}/{self.max_attempts} 重试 "
                        f"({delay:.2f}s后): {error_type.value} - {e}"
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(delay)
        
        logger.error(f"❌ 操作执行失败，已达最大重试次数: {last_exception}")
        raise last_exception


def with_retry(
    max_attempts: int = 10,
    base_delay: float = 5.0,
    max_delay: float = 300.0
):
    """
    重试装饰器
    
    用法：
        @with_retry(max_attempts=5)
        async def my_operation():
            ...
    """
    policy = RetryPolicy(max_attempts=max_attempts, base_delay=base_delay, max_delay=max_delay)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            return await policy.execute_with_retry(func, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            return policy.execute_with_retry_sync(func, *args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


retry_policy = RetryPolicy()
