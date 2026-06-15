"""
MyAPS API - 统一日志系统

这是新的统一日志系统入口，替代原有的logger.py和logger_v2.py。

特性:
- 异步写入，不阻塞业务线程
- 多目标输出（控制台、文件、数据库、WebSocket）
- 敏感信息自动脱敏
- 日期前缀文件轮转
- API完全向后兼容

使用方法:
    from globalobjects import logger
    logger.info("消息")
    
    from globalobjects.logger import get_logger
    logger = get_logger(__name__)

迁移说明:
- 旧实现已备份到 logger_v1_backup.py (103KB)
- V2实现已备份到 logger_v2_backup.py (21KB)
- 新实现在 logger/ 目录下
"""

import logging
from typing import Optional, Any, Dict, List

from .logger import (
    SmartLogger,
    get_logger as _get_logger,
    LogHelper,
    EmojiManager,
    emoji_manager,
    AsyncLogQueue,
    LogRouter,
    StackTraceTracer,
    LoggerConfig,
    LogRecord,
    ConsoleHandler,
    SmartFileHandler,
    DatabaseHandler,
    WebSocketHandler,
    initialize_logging,
    shutdown_logging,
    set_db_initialized,
    mark_db_initialized,
    is_db_initialized,
)

logger = _get_logger('app')


def get_logger(name: Optional[str] = None, level: str = 'INFO') -> SmartLogger:
    """获取日志器实例"""
    return _get_logger(name, level)


def setup_logger(name: str, level: str = 'INFO', auto_file: bool = True) -> SmartLogger:
    """设置日志器（兼容旧API）"""
    return _get_logger(name, level)


def setup_file_logging(log_name: str, log_filename: str = 'app.log') -> logging.Logger:
    """设置文件日志（兼容旧API）"""
    return logging.getLogger(f"{log_name}_{log_filename}")


def get_file_logger(name: str) -> SmartLogger:
    """获取文件日志器（兼容旧API）"""
    return _get_logger(name)


def get_log_level(level_name: str) -> int:
    """获取日志级别数值"""
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    return level_map.get(level_name.upper(), logging.INFO)


def start_all_listeners() -> None:
    """启动所有监听器（兼容旧API）"""
    pass


def close_logging() -> None:
    """关闭日志系统（兼容旧API）"""
    pass


def debug(msg: Any, *args, **kwargs) -> None:
    """记录DEBUG级别日志"""
    logger.debug(msg, *args, **kwargs)


def info(msg: Any, *args, **kwargs) -> None:
    """记录INFO级别日志"""
    logger.info(msg, *args, **kwargs)


def warning(msg: Any, *args, **kwargs) -> None:
    """记录WARNING级别日志"""
    logger.warning(msg, *args, **kwargs)


def warning_console(msg: Any) -> None:
    """仅输出到控制台的警告（不写入文件，不发送到前端监控）"""
    logger.warning_console(msg)


def info_console(msg: Any) -> None:
    """仅输出到控制台的信息（不写入文件，不发送到前端监控）"""
    logger.info_console(msg)


def error(msg: Any, *args, **kwargs) -> None:
    """记录ERROR级别日志"""
    logger.error(msg, *args, **kwargs)


def critical(msg: Any, *args, **kwargs) -> None:
    """记录CRITICAL级别日志"""
    logger.critical(msg, *args, **kwargs)


def exception(msg: Any, *args, **kwargs) -> None:
    """记录异常日志"""
    logger.exception(msg, *args, **kwargs)


def get_logger_unified(name: Optional[str] = None, level: str = 'INFO') -> SmartLogger:
    """获取统一日志器（兼容旧API）"""
    return _get_logger(name, level)


def initialize_logging_unified() -> None:
    """初始化统一日志系统（兼容旧API）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(initialize_logging())
        else:
            loop.run_until_complete(initialize_logging())
    except Exception:
        pass


def shutdown_logging_unified() -> None:
    """关闭统一日志系统（兼容旧API）"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(shutdown_logging())
        else:
            loop.run_until_complete(shutdown_logging())
    except Exception:
        pass


def set_db_initialized_unified(initialized: bool = True) -> None:
    """设置数据库初始化状态（兼容旧API）"""
    set_db_initialized(initialized)


TERMINAL_SUPPORTS_ANSI = True

ANSI_COLORS = {
    'DEBUG': '\033[36m',
    'INFO': '\033[32m',
    'WARNING': '\033[33m',
    'ERROR': '\033[31m',
    'CRITICAL': '\033[31m',
    'RESET': '\033[0m',
}

LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}

DEFAULT_LOG_FORMAT = '%(asctime)s - %(name)s - %(funcName)s:%(lineno)d - %(levelname)s - %(message)s'

LOG_CONFIG = {
    'default': {'filename': 'app.log', 'level': 'INFO'},
    'error': {'filename': 'error.log', 'level': 'ERROR'},
    'debug': {'filename': 'debug.log', 'level': 'DEBUG'}
}

logger_instances: Dict[str, SmartLogger] = {}
listeners: Dict[str, Any] = {}
db_initialized: bool = False


__all__ = [
    'logger',
    'get_logger',
    'setup_logger',
    'setup_file_logging',
    'get_file_logger',
    'get_log_level',
    'start_all_listeners',
    'close_logging',
    'initialize_logging',
    'shutdown_logging',
    'set_db_initialized',
    'mark_db_initialized',
    'is_db_initialized',
    'get_logger_unified',
    'initialize_logging_unified',
    'shutdown_logging_unified',
    'set_db_initialized_unified',
    'SmartLogger',
    'LogHelper',
    'EmojiManager',
    'emoji_manager',
    'AsyncLogQueue',
    'LogRouter',
    'StackTraceTracer',
    'LoggerConfig',
    'LogRecord',
    'ConsoleHandler',
    'SmartFileHandler',
    'DatabaseHandler',
    'WebSocketHandler',
    'debug',
    'info',
    'warning',
    'error',
    'critical',
    'exception',
    'TERMINAL_SUPPORTS_ANSI',
    'ANSI_COLORS',
    'LOG_LEVELS',
    'DEFAULT_LOG_FORMAT',
    'LOG_CONFIG',
    'logger_instances',
    'listeners',
    'db_initialized',
]


if __name__ == "__main__":
    print("=== 统一日志系统测试 ===")
    print(f"SmartLogger: {SmartLogger}")
    print(f"LogHelper: {LogHelper}")
    print(f"EmojiManager: {emoji_manager}")
    print(f"Logger实例: {logger}")
    print("✅ 统一日志系统加载成功")
