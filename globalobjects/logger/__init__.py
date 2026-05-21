"""
统一日志系统 - 模块主入口

导出所有公共API
"""

import logging

from .core import SmartLogger
from .factory import (
    get_logger,
    get_default_logger,
    set_config,
    get_config,
    clear_cache,
    debug,
    info,
    warning,
    error,
    critical,
    exception,
    success,
    fail,
    start,
    stop
)
from .models import LogRecord, LoggerConfig
from .helpers import LogHelper, EmojiManager, emoji_manager, sensitive_masker
from .tracer import StackTraceTracer
from .queue import AsyncLogQueue
from .router import LogRouter
from .handlers import (
    Handler,
    ConsoleHandler,
    DatePrefixFileHandler,
    SmartFileHandler,
    DatabaseHandler,
    WebSocketHandler,
    _log_stream_manager
)
from .lifespan import initialize_logging, shutdown_logging
from .db_integration import set_db_initialized, mark_db_initialized, is_db_initialized

def set_db_initialized_unified(initialized: bool = True) -> None:
    """
    设置数据库初始化状态（统一接口，兼容旧API）
    
    Args:
        initialized: 是否已初始化
    """
    set_db_initialized(initialized)


__all__ = [
    'SmartLogger',
    'get_logger',
    'get_default_logger',
    'set_config',
    'get_config',
    'clear_cache',
    'LogRecord',
    'LoggerConfig',
    'LogHelper',
    'EmojiManager',
    'emoji_manager',
    'sensitive_masker',
    'StackTraceTracer',
    'AsyncLogQueue',
    'LogRouter',
    'Handler',
    'ConsoleHandler',
    'DatePrefixFileHandler',
    'SmartFileHandler',
    'DatabaseHandler',
    'WebSocketHandler',
    '_log_stream_manager',
    'debug',
    'info',
    'warning',
    'error',
    'critical',
    'exception',
    'success',
    'fail',
    'start',
    'stop',
    'initialize_logging',
    'shutdown_logging',
    'set_db_initialized',
    'mark_db_initialized',
    'is_db_initialized',
    'set_db_initialized_unified',
    'LOG_LEVELS',
    'ANSI_COLORS',
    'TERMINAL_SUPPORTS_ANSI',
    'logger_instances',
    'listeners',
    'db_initialized',
]


logger = get_logger('app')


LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

ANSI_COLORS = {
    'DEBUG': '\033[36m',
    'INFO': '\033[32m',
    'WARNING': '\033[33m',
    'ERROR': '\033[31m',
    'CRITICAL': '\033[31m',
    'RESET': '\033[0m',
}

TERMINAL_SUPPORTS_ANSI = True
logger_instances = {}
listeners = {}
db_initialized = False
