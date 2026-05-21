"""
统一日志系统 - 输出处理器基类和控制台处理器
"""

import sys
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import datetime

from ..models import LogRecord
from ..helpers import TERMINAL_SUPPORTS_ANSI, ANSI_COLORS


class Handler(ABC):
    """
    处理器基类
    
    所有输出处理器的抽象基类
    """
    
    def __init__(
        self,
        level: int = logging.DEBUG,
        enabled: bool = True
    ):
        """
        初始化处理器
        
        Args:
            level: 最低日志级别
            enabled: 是否启用
        """
        self._level = level
        self._enabled = enabled
    
    @abstractmethod
    def emit(self, record: LogRecord) -> None:
        """
        输出日志记录
        
        Args:
            record: 日志记录
        """
        pass
    
    def handle(self, record: LogRecord) -> bool:
        """
        处理日志记录
        
        Args:
            record: 日志记录
            
        Returns:
            bool: 处理成功返回True
        """
        if not self._enabled:
            return False
        
        if record.level < self._level:
            return False
        
        try:
            self.emit(record)
            return True
        except Exception:
            return False
    
    def enable(self) -> None:
        """启用处理器"""
        self._enabled = True
    
    def disable(self) -> None:
        """禁用处理器"""
        self._enabled = False
    
    @property
    def enabled(self) -> bool:
        """是否启用"""
        return self._enabled
    
    def set_level(self, level: int) -> None:
        """设置最低日志级别"""
        self._level = level
    
    def get_level(self) -> int:
        """获取最低日志级别"""
        return self._level
    
    def close(self) -> None:
        """关闭处理器（清理资源）"""
        pass


class ConsoleHandler(Handler):
    """
    控制台处理器
    
    特性：
    - 支持ANSI颜色输出
    - 根据日志级别选择stdout/stderr
    - 支持emoji显示
    """
    
    def __init__(
        self,
        level: int = logging.DEBUG,
        enabled: bool = True,
        colorize: bool = True,
        show_module: bool = False
    ):
        """
        初始化控制台处理器
        
        Args:
            level: 最低日志级别
            enabled: 是否启用
            colorize: 是否启用颜色
            show_module: 是否显示模块名
        """
        super().__init__(level, enabled)
        self._colorize = colorize and TERMINAL_SUPPORTS_ANSI
        self._show_module = show_module
    
    def emit(self, record: LogRecord) -> None:
        """输出到控制台"""
        message = self._format(record)
        
        if record.level >= logging.ERROR:
            stream = sys.stderr
        else:
            stream = sys.stdout
        
        if self._colorize:
            message = self._colorize_message(message, record.level)
        
        try:
            stream.write(message + '\n')
            stream.flush()
        except Exception:
            pass
    
    def _format(self, record: LogRecord) -> str:
        """格式化日志消息"""
        timestamp = record.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        if self._show_module and record.module:
            return f"{timestamp} - {record.level_name} - [{record.module}] {record.message}"
        
        return f"{timestamp} - {record.level_name} - {record.message}"
    
    def _colorize_message(self, message: str, level: int) -> str:
        """添加颜色"""
        level_name = logging.getLevelName(level)
        color = ANSI_COLORS.get(level_name, '')
        reset = ANSI_COLORS.get('RESET', '')
        
        if color:
            return f"{color}{message}{reset}"
        
        return message


class StreamHandler(Handler):
    """
    流处理器基类
    
    用于日志流推送（如WebSocket）
    """
    
    def __init__(
        self,
        level: int = logging.DEBUG,
        enabled: bool = True
    ):
        super().__init__(level, enabled)
        self._subscribers = []
    
    def add_subscriber(self, subscriber: Any) -> None:
        """添加订阅者"""
        self._subscribers.append(subscriber)
    
    def remove_subscriber(self, subscriber: Any) -> None:
        """移除订阅者"""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)
    
    def has_subscribers(self) -> bool:
        """是否有订阅者"""
        return len(self._subscribers) > 0
