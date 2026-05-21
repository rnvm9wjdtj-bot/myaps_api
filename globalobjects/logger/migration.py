"""
统一日志系统 - 迁移模块

提供从旧logger.py/logger_v2.py到新实现的平滑迁移
"""

import os
import sys
from typing import Optional, Any, Callable


_use_unified_logger: Optional[bool] = None


def should_use_unified_logger() -> bool:
    """
    检查是否使用统一日志系统
    
    逻辑：
    1. 环境变量USE_UNIFIED_LOGGER=true时使用新实现
    2. 默认使用新实现
    
    Returns:
        bool: 使用新实现返回True
    """
    global _use_unified_logger
    
    if _use_unified_logger is not None:
        return _use_unified_logger
    
    env_value = os.getenv('USE_UNIFIED_LOGGER', 'true')
    _use_unified_logger = env_value.lower() in ('true', '1', 'yes')
    
    return _use_unified_logger


def set_use_unified_logger(use: bool) -> None:
    """
    强制设置是否使用统一日志系统
    
    Args:
        use: 是否使用
    """
    global _use_unified_logger
    _use_unified_logger = use


def get_logger_unified(name: Optional[str] = None, level: str = 'INFO') -> Any:
    """
    获取日志器（根据配置选择实现）
    
    Args:
        name: 日志器名称
        level: 日志级别
        
    Returns:
        SmartLogger或旧logger实例
    """
    if should_use_unified_logger():
        from .factory import get_logger
        return get_logger(name, level)
    else:
        try:
            from globalobjects.logger_v1_backup import get_logger as old_get_logger
            return old_get_logger(name or 'app', level)
        except ImportError:
            from .factory import get_logger
            return get_logger(name, level)


def initialize_logging_unified() -> Callable[[], Any]:
    """
    获取初始化函数（根据配置选择实现）
    
    Returns:
        初始化函数
    """
    if should_use_unified_logger():
        from .lifespan import initialize_logging
        return initialize_logging
    else:
        try:
            from globalobjects.logger_v1_backup import initialize_logging as old_init
            return old_init
        except ImportError:
            from .lifespan import initialize_logging
            return initialize_logging


def shutdown_logging_unified() -> Callable[[], Any]:
    """
    获取关闭函数（根据配置选择实现）
    
    Returns:
        关闭函数
    """
    if should_use_unified_logger():
        from .lifespan import shutdown_logging
        return shutdown_logging
    else:
        try:
            from globalobjects.logger_v1_backup import shutdown_logging as old_shutdown
            return old_shutdown
        except ImportError:
            from .lifespan import shutdown_logging
            return shutdown_logging


def set_db_initialized_unified(initialized: bool = True) -> None:
    """
    设置数据库初始化状态（统一接口）
    
    Args:
        initialized: 是否已初始化
    """
    if should_use_unified_logger():
        from .db_integration import mark_db_initialized
        mark_db_initialized()
    else:
        try:
            from globalobjects.logger_v1_backup import set_db_initialized as old_set
            old_set(initialized)
        except ImportError:
            from .db_integration import mark_db_initialized
            mark_db_initialized()


class LoggerMigration:
    """
    日志迁移助手
    
    提供迁移过程的监控和验证功能
    """
    
    def __init__(self):
        self._migration_started = False
        self._migration_completed = False
        self._errors = []
    
    def start_migration(self) -> None:
        """开始迁移"""
        self._migration_started = True
        sys.stdout.write("[LoggerMigration] Migration started\n")
    
    def record_error(self, error: str) -> None:
        """记录迁移错误"""
        self._errors.append(error)
        sys.stderr.write(f"[LoggerMigration] Error: {error}\n")
    
    def complete_migration(self) -> None:
        """完成迁移"""
        self._migration_completed = True
        status = "with errors" if self._errors else "successfully"
        sys.stdout.write(f"[LoggerMigration] Migration completed {status}\n")
    
    def get_status(self) -> dict:
        """获取迁移状态"""
        return {
            'started': self._migration_started,
            'completed': self._migration_completed,
            'errors': self._errors,
            'error_count': len(self._errors)
        }
    
    def validate_api_compatibility(self) -> bool:
        """
        验证API兼容性
        
        Returns:
            bool: 兼容返回True
        """
        try:
            from . import SmartLogger
            from . import LogHelper
            from . import get_logger
            
            required_methods = [
                'debug', 'info', 'warning', 'error', 'critical', 'exception',
                'success', 'fail', 'start', 'stop',
                'query', 'insert', 'update', 'delete',
                'set_level', 'set_db_initialized'
            ]
            
            for method in required_methods:
                if not hasattr(SmartLogger, method):
                    self.record_error(f"Missing method: SmartLogger.{method}")
            
            return len(self._errors) == 0
            
        except Exception as e:
            self.record_error(str(e))
            return False


_migration_helper: Optional[LoggerMigration] = None


def get_migration_helper() -> LoggerMigration:
    """获取迁移助手实例"""
    global _migration_helper
    
    if _migration_helper is None:
        _migration_helper = LoggerMigration()
    
    return _migration_helper
