"""
统一日志系统 - 日志路由器

负责日志消息的路由、过滤和分发
"""

import logging
from typing import Optional, Dict, Any, List, Callable

from .models import LogRecord, LoggerConfig
from .helpers import sensitive_masker


class LogRouter:
    """
    日志路由器
    
    职责：
    - 日志级别过滤
    - 敏感信息脱敏
    - 路由到异步队列
    - 立即返回不阻塞
    """
    
    def __init__(
        self,
        config: Optional[LoggerConfig] = None,
        queue: Optional[Any] = None
    ):
        """
        初始化路由器
        
        Args:
            config: 日志配置
            queue: 异步队列实例
        """
        self._config = config or LoggerConfig()
        self._queue = queue
        self._min_level = self._config.get_level_int()
        self._masker = sensitive_masker
        self._enabled = True
        self._pre_filters: List[Callable[[LogRecord], bool]] = []
    
    def set_queue(self, queue: Any) -> None:
        """设置异步队列"""
        self._queue = queue
    
    def set_level(self, level: str) -> None:
        """
        设置最低日志级别
        
        Args:
            level: 级别名称（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        self._min_level = level_map.get(level.upper(), logging.INFO)
    
    def add_filter(self, filter_func: Callable[[LogRecord], bool]) -> None:
        """
        添加前置过滤器
        
        Args:
            filter_func: 过滤函数，返回False则丢弃日志
        """
        self._pre_filters.append(filter_func)
    
    def remove_filter(self, filter_func: Callable[[LogRecord], bool]) -> None:
        """移除过滤器"""
        if filter_func in self._pre_filters:
            self._pre_filters.remove(filter_func)
    
    def enable(self) -> None:
        """启用路由器"""
        self._enabled = True
    
    def disable(self) -> None:
        """禁用路由器"""
        self._enabled = False
    
    def route(self, record: LogRecord) -> bool:
        """
        路由日志记录
        
        Args:
            record: 日志记录
            
        Returns:
            bool: 成功路由返回True，否则返回False
        """
        if not self._enabled:
            return False
        
        if record.level < self._min_level:
            return False
        
        for filter_func in self._pre_filters:
            try:
                if not filter_func(record):
                    return False
            except Exception:
                pass
        
        if self._config.sensitive_fields:
            record.message = self._masker.mask(record.message)
        
        if self._queue:
            result = self._queue.put_nowait(record)
            return result
        
        return False
    
    def should_log(self, level: int) -> bool:
        """
        检查是否应该记录该级别日志
        
        Args:
            level: 日志级别数值
            
        Returns:
            bool: 应该记录返回True
        """
        return self._enabled and level >= self._min_level
    
    def get_level(self) -> int:
        """获取当前最低日志级别"""
        return self._min_level
    
    def get_level_name(self) -> str:
        """获取当前最低日志级别名称"""
        return logging.getLevelName(self._min_level)
