"""
统一日志系统 - 工厂函数和模块级API
"""

import logging
from typing import Optional, Dict, Any

from .core import SmartLogger
from .models import LoggerConfig, LogRecord
from .helpers import LogHelper, EmojiManager, emoji_manager
from .tracer import StackTraceTracer


_logger_cache: Dict[str, SmartLogger] = {}
_default_logger: Optional[SmartLogger] = None
_config: Optional[LoggerConfig] = None


def get_logger(name: Optional[str] = None, level: str = 'INFO') -> SmartLogger:
    """
    获取日志器实例
    
    Args:
        name: 日志器名称，默认使用调用模块名
        level: 日志级别
        
    Returns:
        SmartLogger实例
    """
    global _default_logger
    
    if name is None:
        import inspect
        frame = inspect.currentframe()
        try:
            if frame and frame.f_back:
                name = frame.f_back.f_globals.get('__name__', 'app')
            else:
                name = 'app'
        finally:
            if frame:
                del frame
    
    if name in _logger_cache:
        return _logger_cache[name]
    
    global _config
    if _config is None:
        _config = LoggerConfig.from_env()
        _config.log_level = level
    
    logger = SmartLogger(name=name, config=_config)
    _logger_cache[name] = logger
    
    if _default_logger is None:
        _default_logger = logger
    
    return logger


def get_default_logger() -> SmartLogger:
    """获取默认日志器"""
    global _default_logger
    
    if _default_logger is None:
        _default_logger = get_logger('app')
    
    return _default_logger


def set_config(config: LoggerConfig) -> None:
    """设置全局配置"""
    global _config
    _config = config


def get_config() -> Optional[LoggerConfig]:
    """获取全局配置"""
    return _config


def clear_cache() -> None:
    """清除日志器缓存"""
    global _default_logger
    _logger_cache.clear()
    _default_logger = None


def debug(msg: Any, *args, **kwargs) -> None:
    """模块级DEBUG日志"""
    get_default_logger().debug(msg, *args, **kwargs)


def info(msg: Any, *args, **kwargs) -> None:
    """模块级INFO日志"""
    get_default_logger().info(msg, *args, **kwargs)


def warning(msg: Any, *args, **kwargs) -> None:
    """模块级WARNING日志"""
    get_default_logger().warning(msg, *args, **kwargs)


def error(msg: Any, *args, **kwargs) -> None:
    """模块级ERROR日志"""
    get_default_logger().error(msg, *args, **kwargs)


def critical(msg: Any, *args, **kwargs) -> None:
    """模块级CRITICAL日志"""
    get_default_logger().critical(msg, *args, **kwargs)


def exception(msg: Any, *args, **kwargs) -> None:
    """模块级异常日志"""
    get_default_logger().exception(msg, *args, **kwargs)


def success(action: str, subject: str = "", details: str = "") -> None:
    """模块级成功日志"""
    get_default_logger().success(action, subject, details)


def fail(action: str, subject: str = "", reason: str = "") -> None:
    """模块级失败日志"""
    get_default_logger().fail(action, subject, reason)


def start(action: str, subject: str = "") -> None:
    """模块级开始日志"""
    get_default_logger().start(action, subject)


def stop(action: str, subject: str = "") -> None:
    """模块级结束日志"""
    get_default_logger().stop(action, subject)
