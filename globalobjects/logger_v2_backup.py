"""
日志模块 V2 - 基于 Loguru 的实现

功能特性：
- 异常堆栈自动捕获（logger.exception 和 @logger.catch）
- 彩色控制台输出
- 文件轮转（按日期前缀）
- 异步写入（enqueue=True）
- 完整调用栈追踪
- 数据库日志
- 日志流推送

迁移说明：
- 保持与 logger.py 相同的 API
- 底层使用 loguru 替代 logging
- LogHelper/EmojiManager 从 logger.py 复用
"""

import os
import sys
import logging
import inspect
import threading
import asyncio
from pathlib import Path
from typing import Optional, Any, Dict
from loguru import logger as _loguru_logger


# ============================================================================
# 配置常量（与 logger.py 保持一致）
# ============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ============================================================================
# 从 logger.py 导入必要组件（避免循环导入）
# ============================================================================

def _import_logger_components():
    """延迟导入 logger.py 的组件"""
    try:
        from globalobjects.logger import (
            LogHelper,
            EmojiManager,
            emoji_manager,
            TERMINAL_SUPPORTS_ANSI,
            ANSI_COLORS,
            db_initialized
        )
        return LogHelper, emoji_manager, TERMINAL_SUPPORTS_ANSI, ANSI_COLORS, db_initialized
    except Exception:
        # 如果导入失败，提供默认实现
        return None, None, True, {}, False


# ============================================================================
# Loguru 格式化器
# ============================================================================

def create_formatter():
    """创建格式化器函数"""
    try:
        from globalobjects.logger import ANSI_COLORS, TERMINAL_SUPPORTS_ANSI
    except Exception:
        ANSI_COLORS = {
            'DEBUG': '\033[36m',
            'INFO': '\033[32m',
            'WARNING': '\033[33m',
            'ERROR': '\033[31m',
            'CRITICAL': '\033[31m',
            'RESET': '\033[0m',
        }
        TERMINAL_SUPPORTS_ANSI = True
    
    def formatter(record):
        level = record["level"].name
        time_str = record["time"].strftime("%Y-%m-%d %H:%M:%S")
        message = record["message"]
        
        if sys.stdout.isatty() or TERMINAL_SUPPORTS_ANSI:
            color = ANSI_COLORS.get(level, "")
            reset = ANSI_COLORS.get('RESET', "")
            return f"{color}{time_str} - {level} - {message}{reset}\n"
        
        return f"{time_str} - {level} - {message}\n"
    
    return formatter


# ============================================================================
# Loguru 配置
# ============================================================================

_loguru_configured = False


def configure_loguru(
    log_level: str = "INFO",
    log_file: str = "app.log",
    rotation: str = "00:00",
    retention: str = "10 days",
    enqueue: bool = True
):
    """
    配置 Loguru
    
    Args:
        log_level: 日志级别
        log_file: 日志文件名
        rotation: 轮转时间（默认每天午夜）
        retention: 保留时间
        enqueue: 是否异步写入
    """
    global _loguru_configured
    
    if _loguru_configured:
        return
    
    # 移除默认处理器
    _loguru_logger.remove()
    
    # 控制台处理器（带颜色）
    _loguru_logger.add(
        sys.stdout,
        level=log_level,
        format=create_formatter(),
        colorize=False,
        enqueue=enqueue
    )
    
    # 文件处理器（WARNING 及以上）
    log_path = LOG_DIR / log_file
    _loguru_logger.add(
        str(log_path),
        level="WARNING",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        enqueue=enqueue,
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {message}"
    )
    
    # ERROR 级别单独文件
    error_log_path = LOG_DIR / "error.log"
    _loguru_logger.add(
        str(error_log_path),
        level="ERROR",
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
        enqueue=enqueue,
        format="{time:YYYY-MM-DD HH:mm:ss} - {level} - {message}\n{exception}"
    )
    
    _loguru_configured = True


# ============================================================================
# SmartLoggerV2 - 适配器类
# ============================================================================

class SmartLoggerV2:
    """
    智能日志器 V2 - 基于 Loguru
    
    API 与 SmartLogger 保持兼容，底层使用 loguru
    """
    
    def __init__(self, name: str = "app"):
        self.name = name
        self._logger = _loguru_logger.bind(logger_name=name)
        self._file_logger = None
        self._auto_file_enabled = True
        self._db_enabled = True
        self._db_min_level = logging.INFO
        self._db_initialized = False
    
    def set_file_logger(self, file_logger) -> None:
        self._file_logger = file_logger
    
    def enable_auto_file(self) -> None:
        self._auto_file_enabled = True
    
    def disable_auto_file(self) -> None:
        self._auto_file_enabled = False
    
    def enable_db_logging(self) -> None:
        self._db_enabled = True
    
    def disable_db_logging(self) -> None:
        self._db_enabled = False
    
    def set_db_min_level(self, level: int) -> None:
        self._db_min_level = level
    
    def set_db_initialized(self, initialized: bool = True) -> None:
        self._db_initialized = initialized
    
    def set_db_initialized_all(self, initialized: bool = True) -> None:
        global _db_initialized_global
        _db_initialized_global = initialized
    
    # -------------------------------------------------------------------------
    # 辅助方法
    # -------------------------------------------------------------------------
    
    @staticmethod
    def _format_msg(msg: Any, args: tuple) -> str:
        if not args:
            return str(msg)
        try:
            return msg % args
        except (TypeError, ValueError):
            return f"{msg} {' '.join(map(str, args))}"
    
    def _get_caller_info(self):
        """获取调用者信息"""
        try:
            stack = inspect.stack()
            skip_modules = {'asyncio', 'globalobjects.logger', 'globalobjects.logger_v2', 'logging'}
            
            for frame_info in stack[2:]:
                frame = frame_info.frame
                module_name = frame.f_globals.get('__name__', '')
                
                if module_name not in skip_modules and not module_name.startswith('asyncio'):
                    return {
                        'module': module_name,
                        'function': frame_info.function,
                        'line_number': frame_info.lineno
                    }
        except Exception:
            pass
        return None
    
    async def _log_to_database(self, level: int, msg: str, caller_info=None, **kwargs) -> None:
        """异步写入数据库"""
        try:
            from core.settings import SQLITE_FILE
        except Exception:
            return
        
        global _db_initialized_global
        if not _db_initialized_global or not self._db_enabled:
            return
        
        if level < self._db_min_level:
            return
        
        try:
            from apps.common.monitor.models import SystemLog
        except Exception:
            return
        
        stack_trace = None
        if level >= logging.ERROR:
            try:
                import traceback
                stack_trace = ''.join(traceback.format_stack())
            except Exception:
                pass
        
        if not caller_info:
            caller_info = self._get_caller_info()
        
        try:
            SystemLog._meta.default_connection = SQLITE_FILE
            
            await SystemLog.create(
                level=logging.getLevelName(level),
                module=caller_info.get('module', '') if caller_info else '',
                function=caller_info.get('function', '') if caller_info else '',
                line_number=caller_info.get('line_number', 0) if caller_info else 0,
                message=msg,
                details=str(kwargs) if kwargs else None,
                stack_trace=stack_trace,
                process_id=os.getpid(),
                thread_id=threading.get_ident(),
                thread_name=threading.current_thread().name
            )
        except Exception:
            pass
    
    def _send_to_log_stream(self, level: int, msg: str):
        """发送到日志流"""
        try:
            from apps.common.monitor.log_stream_service import _log_stream_manager
            handlers = _log_stream_manager.get_handlers()
            if not handlers:
                return
            
            caller_info = self._get_caller_info()
            
            record = logging.LogRecord(
                name=caller_info.get('module', self.name) if caller_info else self.name,
                level=level,
                pathname='',
                lineno=caller_info.get('line_number', 0) if caller_info else 0,
                msg=msg,
                args=(),
                exc_info=None,
                func=caller_info.get('function', '') if caller_info else ''
            )
            record.module = record.name
            
            _log_stream_manager.emit_to_handlers(record)
        except Exception:
            pass
    
    # -------------------------------------------------------------------------
    # 基础日志方法
    # -------------------------------------------------------------------------
    
    def _log(self, level: int, msg: Any, *args, **kwargs) -> None:
        """统一日志方法"""
        formatted_msg = self._format_msg(msg, args)
        level_name = logging.getLevelName(level)
        
        # 获取调用者信息
        caller_info = self._get_caller_info()
        
        # 异步写入数据库
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._log_to_database(level, formatted_msg, caller_info, **kwargs))
        except Exception:
            pass
        
        # 发送到日志流
        self._send_to_log_stream(level, formatted_msg)
        
        # 使用 loguru 输出
        getattr(self._logger.opt(depth=2), level_name.lower())(formatted_msg)
    
    def debug(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: Any, *args, **kwargs) -> None:
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: Any, *args, **kwargs) -> None:
        """记录异常日志（自动捕获完整堆栈）"""
        formatted_msg = self._format_msg(msg, args)
        caller_info = self._get_caller_info()
        
        # 异步写入数据库
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._log_to_database(logging.ERROR, formatted_msg, caller_info, **kwargs))
        except Exception:
            pass
        
        # 发送到日志流
        self._send_to_log_stream(logging.ERROR, formatted_msg)
        
        # loguru 自动捕获异常堆栈
        self._logger.opt(depth=2).exception(formatted_msg)
    
    # -------------------------------------------------------------------------
    # 业务便捷方法
    # -------------------------------------------------------------------------
    
    def success(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.success(action, subject, details)
        else:
            msg = f"✅ {action}成功：{subject}" + (f"，{details}" if details else "")
        self.info(msg)
    
    def fail(self, action: str, subject: str = "", reason: str = "", to_file: bool = True) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.fail(action, subject, reason)
        else:
            msg = f"❌ {action}失败：{subject}" + (f" - {reason}" if reason else "")
        self.error(msg)
    
    def start(self, action: str, subject: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.start(action, subject)
        else:
            msg = f"⏰ 开始{action}" + (f"：{subject}" if subject else "")
        self.info(msg)
    
    def stop(self, action: str, subject: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.stop(action, subject)
        else:
            msg = f"🛑 结束{action}" + (f"：{subject}" if subject else "")
        self.info(msg)
    
    def status_change(self, subject: str, old_status: str, new_status: str, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.status_change(subject, old_status, new_status)
        else:
            msg = f"🔄 {subject}状态变更：{old_status} -> {new_status}"
        self.info(msg)
    
    def api_response(self, api_name: str, status_code: int, details: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.api_response(api_name, status_code, details)
        else:
            emoji = "✅" if 200 <= status_code < 300 else "❌"
            msg = f"{emoji} {api_name}响应：{status_code}" + (f"，{details}" if details else "")
        
        if 200 <= status_code < 300:
            self.info(msg)
        else:
            self.error(msg)
    
    def query(self, target: str, result: str = "", count: int = None, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.query(target, result, count)
        else:
            if count is not None:
                msg = f"✅ 查询{target}成功：共{count}条"
            elif result:
                msg = f"🔍 查询{target}：{result}"
            else:
                msg = f"🔍 开始查询{target}"
        self.info(msg)
    
    def insert(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.insert(target, subject, count)
        else:
            if count is not None:
                msg = f"📥 插入{target}成功：共{count}条"
            elif subject:
                msg = f"📥 插入{target}：{subject}"
            else:
                msg = f"📥 插入{target}"
        self.info(msg)
    
    def update(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.update(target, subject, count)
        else:
            if count is not None:
                msg = f"🔄 更新{target}成功：共{count}条"
            elif subject:
                msg = f"🔄 更新{target}：{subject}"
            else:
                msg = f"🔄 更新{target}"
        self.info(msg)
    
    def delete(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.delete(target, subject, count)
        else:
            if count is not None:
                msg = f"🗑️ 删除{target}成功：共{count}条"
            elif subject:
                msg = f"🗑️ 删除{target}：{subject}"
            else:
                msg = f"🗑️ 删除{target}"
        self.info(msg)
    
    def warning_msg(self, subject: str, message: str, to_file: bool = True) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.warning(subject, message)
        else:
            msg = f"⚠️ {subject}：{message}"
        self.warning(msg)
    
    def sync(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.sync(action, subject, details)
        else:
            msg = f"🔄 {action}" + (f"：{subject}" if subject else "") + (f"，{details}" if details else "")
        self.info(msg)
    
    def connect(self, target: str, status: str = "成功", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.connect(target, status)
        else:
            emoji = "🔗" if status == "成功" else "🚫"
            msg = f"{emoji} 连接{target}{status}"
        
        if status == "成功":
            self.info(msg)
        else:
            self.error(msg)
    
    def disconnect(self, target: str, to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.disconnect(target)
        else:
            msg = f"🔌 断开{target}连接"
        self.info(msg)
    
    def cache(self, action: str, target: str = "", details: str = "", to_file: bool = False) -> None:
        LogHelper, _, _, _, _ = _import_logger_components()
        if LogHelper:
            msg = LogHelper.cache(action, target, details)
        else:
            msg = f"💾 {action}缓存" + (f"：{target}" if target else "") + (f"，{details}" if details else "")
        self.info(msg)
    
    # -------------------------------------------------------------------------
    # 装饰器
    # -------------------------------------------------------------------------
    
    def catch(self, exception=Exception, level="ERROR", reraise=False, message=""):
        """装饰器：自动捕获异常并记录"""
        return self._logger.catch(exception=exception, level=level, reraise=reraise, message=message)
    
    def isEnabledFor(self, level: int) -> bool:
        return True


# ============================================================================
# 全局状态
# ============================================================================

_db_initialized_global = False
_logger_instances: Dict[str, SmartLoggerV2] = {}


# ============================================================================
# 工厂函数
# ============================================================================

def get_logger_v2(name: str = "app", level: str = "INFO") -> SmartLoggerV2:
    """获取日志器实例（V2 版本）"""
    if name not in _logger_instances:
        logger_instance = SmartLoggerV2(name)
        _logger_instances[name] = logger_instance
    return _logger_instances[name]


# ============================================================================
# 便捷函数
# ============================================================================

def debug(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().debug(msg, *args, **kwargs)

def info(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().info(msg, *args, **kwargs)

def warning(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().warning(msg, *args, **kwargs)

def error(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().error(msg, *args, **kwargs)

def critical(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().critical(msg, *args, **kwargs)

def exception(msg: Any, *args, **kwargs) -> None:
    get_logger_v2().exception(msg, *args, **kwargs)


# ============================================================================
# 初始化和关闭
# ============================================================================

def initialize_logging_v2(log_level: str = "INFO") -> None:
    """初始化日志系统 V2"""
    global _db_initialized_global
    configure_loguru(log_level=log_level)
    _db_initialized_global = False
    get_logger_v2().info("✅ 日志系统 V2 (Loguru) 初始化完成")

def shutdown_logging_v2() -> None:
    """关闭日志系统 V2"""
    get_logger_v2().info("✅ 日志系统 V2 已关闭")
    _logger_instances.clear()


# ============================================================================
# 数据库初始化标记
# ============================================================================

def set_db_initialized(initialized: bool = True) -> None:
    """设置数据库初始化状态"""
    global _db_initialized_global
    _db_initialized_global = initialized
    for logger in _logger_instances.values():
        logger.set_db_initialized(initialized)


# ============================================================================
# 默认日志器实例
# ============================================================================

configure_loguru()
logger = get_logger_v2()
