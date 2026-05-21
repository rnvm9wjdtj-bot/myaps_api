"""
统一日志系统 - 数据库集成

处理ORM初始化前后的日志缓冲和刷新
"""

import asyncio
from typing import Optional, Callable, Any

from .factory import get_default_logger
from .handlers.database import DatabaseHandler


_db_initialized = False
_init_callbacks: list = []


def is_db_initialized() -> bool:
    """检查数据库是否已初始化"""
    return _db_initialized


def set_db_initialized(initialized: bool = True) -> None:
    """
    设置数据库初始化状态
    
    Args:
        initialized: 是否已初始化
    """
    global _db_initialized
    _db_initialized = initialized
    
    if initialized:
        logger = get_default_logger()
        logger.set_db_initialized(True)


async def wait_for_db_init(timeout: float = 30.0) -> bool:
    """
    等待数据库初始化
    
    Args:
        timeout: 超时时间（秒）
        
    Returns:
        bool: 成功初始化返回True
    """
    global _db_initialized
    
    if _db_initialized:
        return True
    
    start_time = asyncio.get_event_loop().time()
    
    while not _db_initialized:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed >= timeout:
            return False
        await asyncio.sleep(0.1)
    
    return True


def mark_db_initialized() -> None:
    """标记数据库已初始化"""
    global _db_initialized
    
    _db_initialized = True
    
    logger = get_default_logger()
    logger.set_db_initialized(True)
    
    for callback in _init_callbacks:
        try:
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback())
            else:
                callback()
        except Exception:
            pass
    
    _init_callbacks.clear()


def on_db_initialized(callback: Callable[[], Any]) -> None:
    """
    注册数据库初始化回调
    
    Args:
        callback: 回调函数
    """
    if _db_initialized:
        try:
            if asyncio.iscoroutinefunction(callback):
                asyncio.create_task(callback())
            else:
                callback()
        except Exception:
            pass
    else:
        _init_callbacks.append(callback)


def setup_tortoise_hooks() -> None:
    """
    设置Tortoise ORM钩子
    
    在ORM初始化后自动调用mark_db_initialized
    """
    try:
        from tortoise import Tortoise
        
        original_init = Tortoise.init
        
        async def wrapped_init(*args, **kwargs):
            result = await original_init(*args, **kwargs)
            mark_db_initialized()
            return result
        
        Tortoise.init = wrapped_init
        
    except ImportError:
        pass


class DatabaseLogBuffer:
    """
    数据库日志缓冲区
    
    在数据库初始化前缓存日志，初始化后刷新
    """
    
    def __init__(self, max_size: int = 1000):
        self._buffer = []
        self._max_size = max_size
        self._flushed = False
    
    def add(self, record: Any) -> bool:
        """
        添加日志记录到缓冲区
        
        Args:
            record: 日志记录
            
        Returns:
            bool: 成功添加返回True
        """
        if self._flushed:
            return False
        
        if len(self._buffer) >= self._max_size:
            self._buffer.pop(0)
        
        self._buffer.append(record)
        return True
    
    def flush(self, handler: DatabaseHandler) -> int:
        """
        刷新缓冲区到数据库处理器
        
        Args:
            handler: 数据库处理器
            
        Returns:
            int: 刷新的记录数
        """
        if self._flushed:
            return 0
        
        self._flushed = True
        count = len(self._buffer)
        
        for record in self._buffer:
            handler.emit(record)
        
        self._buffer.clear()
        return count
    
    def clear(self) -> int:
        """
        清空缓冲区
        
        Returns:
            int: 清空的记录数
        """
        count = len(self._buffer)
        self._buffer.clear()
        return count
    
    @property
    def size(self) -> int:
        """获取缓冲区大小"""
        return len(self._buffer)
    
    @property
    def flushed(self) -> bool:
        """是否已刷新"""
        return self._flushed


_db_log_buffer: Optional[DatabaseLogBuffer] = None


def get_db_log_buffer(max_size: int = 1000) -> DatabaseLogBuffer:
    """
    获取数据库日志缓冲区实例
    
    Args:
        max_size: 最大缓冲大小
        
    Returns:
        DatabaseLogBuffer实例
    """
    global _db_log_buffer
    
    if _db_log_buffer is None:
        _db_log_buffer = DatabaseLogBuffer(max_size)
    
    return _db_log_buffer
