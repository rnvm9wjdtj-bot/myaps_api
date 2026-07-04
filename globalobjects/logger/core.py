"""
统一日志系统 - SmartLogger核心实现

提供统一的日志记录API，保持与现有logger.py完全兼容
"""

import os
import sys
import time
import logging
import threading
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

from .models import LogRecord, LoggerConfig
from .queue import AsyncLogQueue
from .router import LogRouter
from .tracer import StackTraceTracer
from .handlers import ConsoleHandler, SmartFileHandler, DatabaseHandler, WebSocketHandler
from .handlers import _log_stream_manager
from .helpers import LogHelper, emoji_manager


class SmartLogger:
    """
    智能日志器
    
    特性：
    - 统一的日志记录API
    - 异步写入不阻塞
    - 多目标输出
    - 业务语义化便捷方法
    - 完全兼容现有logger.py
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        name: str = "app",
        config: Optional[LoggerConfig] = None
    ):
        """
        初始化日志器
        
        Args:
            name: 日志器名称
            config: 日志配置
        """
        if self._initialized:
            return
        
        self._initialized = True
        self._name = name
        self._config = config or LoggerConfig.from_env()
        
        self._queue = AsyncLogQueue(
            max_size=self._config.queue_size,
            batch_size=self._config.batch_size,
            flush_interval=self._config.flush_interval
        )
        
        self._tracer = StackTraceTracer(enabled=self._config.stack_trace)
        
        self._router = LogRouter(config=self._config, queue=self._queue)
        
        self._console_handler: Optional[ConsoleHandler] = None
        self._file_handler: Optional[SmartFileHandler] = None
        self._database_handler: Optional[DatabaseHandler] = None
        self._websocket_handler: Optional[WebSocketHandler] = None
        
        self._level = self._config.get_level_int()
        self._running = False
        
        self._targets = {
            'console': self._config.to_console,
            'file': self._config.to_file,
            'database': self._config.to_database,
            'websocket': self._config.to_websocket
        }
    
    async def initialize(self) -> None:
        """初始化日志系统"""
        if self._running:
            return
        
        self._setup_handlers()
        
        await self._queue.start()
        
        self._setup_queue_handlers()
        
        self._running = True
    
    def _setup_handlers(self) -> None:
        """设置处理器"""
        if self._targets.get('console', True):
            self._console_handler = ConsoleHandler(
                level=self._level,
                enabled=True,
                colorize=True,
                show_module=False
            )
        
        if self._targets.get('file', True):
            self._file_handler = SmartFileHandler(
                log_dir=self._config.log_dir,
                level=logging.WARNING,
                enabled=True,
                retention_days=self._config.retention_days
            )
        
        if self._targets.get('database', True):
            self._database_handler = DatabaseHandler(
                level=logging.INFO,
                enabled=True,
                batch_size=self._config.batch_size,
                flush_interval=self._config.flush_interval
            )
        
        if self._targets.get('websocket', True):
            self._websocket_handler = WebSocketHandler(
                level=logging.DEBUG,
                enabled=True,
                max_connections=100
            )
    
    def _setup_queue_handlers(self) -> None:
        """设置队列处理器"""
        if self._console_handler:
            self._queue.add_handler(self._console_handler.handle)
        
        if self._file_handler:
            self._queue.add_handler(self._file_handler.handle)
        
        if self._database_handler:
            self._queue.add_handler(self._database_handler.emit)
    
    async def shutdown(self) -> None:
        """关闭日志系统"""
        if not self._running:
            return
        
        self._running = False
        
        await self._queue.stop()
        
        if self._console_handler:
            self._console_handler.close()
        if self._file_handler:
            self._file_handler.close()
        if self._database_handler:
            self._database_handler.close()
        if self._websocket_handler:
            self._websocket_handler.close()
    
    def _log(
        self,
        level: int,
        msg: Any,
        *args,
        exc_info: bool = False,
        **kwargs
    ) -> None:
        """
        内部日志方法
        
        Args:
            level: 日志级别
            msg: 日志消息
            args: 格式化参数
            exc_info: 是否捕获异常信息
            kwargs: 额外参数
        """
        if level < self._level:
            return
        
        formatted_msg = self._format_message(msg, args)
        
        caller_info = self._tracer.get_caller_info(skip_frames=3)
        
        stack_trace = None
        if exc_info or level >= logging.ERROR:
            import traceback
            try:
                stack_trace = ''.join(traceback.format_stack())
                if stack_trace and len(stack_trace) > 65535:
                    stack_trace = stack_trace[:65530] + '\n[TRUNCATED]'
            except Exception:
                pass
        
        record = LogRecord(
            level=level,
            level_name=logging.getLevelName(level),
            message=formatted_msg,
            module=caller_info.get('module') if caller_info else None,
            function=caller_info.get('function') if caller_info else None,
            line=caller_info.get('line_number') if caller_info else None,
            stack_trace=stack_trace,
            process_id=os.getpid(),
            thread_id=threading.get_ident(),
            thread_name=threading.current_thread().name,
            extra=kwargs.get('extra')
        )
        
        self._send_to_log_stream(record, formatted_msg)
        
        if not self._running:
            return
        
        self._router.route(record)

    
    def _format_message(self, msg: Any, args: tuple) -> str:
        """格式化消息"""
        if not args:
            return str(msg)
        
        try:
            return msg % args
        except (TypeError, ValueError):
            return f"{msg} {' '.join(map(str, args))}"
    
    def _send_to_log_stream(self, record: LogRecord, message: str) -> None:
        """
        发送日志到日志流服务
        
        Args:
            record: 日志记录对象
            message: 格式化后的消息
        """
        try:
            import logging as logging_module
            
            pathname = record.module or "unknown"
            lineno = record.line or 0
            
            std_record = logging_module.LogRecord(
                name=self._name,
                level=record.level,
                pathname=pathname,
                lineno=lineno,
                msg=message,
                args=(),
                exc_info=None
            )
            
            std_record.module = record.module or "unknown"
            std_record.funcName = record.function or ""
            std_record.levelname = record.level_name
            std_record.created = record.timestamp.timestamp()
            std_record.msecs = (std_record.created - int(std_record.created)) * 1000
            std_record.message = message
            
            for handler in _log_stream_manager.get_handlers():
                handler.emit(std_record)
        except Exception:
            pass
    
    def debug(self, msg: Any, *args, **kwargs) -> None:
        """记录DEBUG级别日志"""
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: Any, *args, **kwargs) -> None:
        """记录INFO级别日志"""
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: Any, *args, **kwargs) -> None:
        """记录WARNING级别日志"""
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: Any, *args, **kwargs) -> None:
        """记录ERROR级别日志"""
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: Any, *args, **kwargs) -> None:
        """记录CRITICAL级别日志"""
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: Any, *args, **kwargs) -> None:
        """记录异常日志（自动捕获异常堆栈）"""
        import traceback
        exc_traceback = traceback.format_exc()
        kwargs['extra'] = kwargs.get('extra', {})
        kwargs['extra']['exception'] = exc_traceback
        self._log(logging.ERROR, msg, *args, exc_info=True, **kwargs)
    
    def success(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        """记录成功消息"""
        msg = LogHelper.success(action, subject, details)
        self.info(msg)
    
    def fail(self, action: str, subject: str = "", reason: str = "", to_file: bool = True) -> None:
        """记录失败消息"""
        msg = LogHelper.fail(action, subject, reason)
        self.error(msg)
    
    def start(self, action: str, subject: str = "", to_file: bool = False) -> None:
        """记录开始消息"""
        msg = LogHelper.start(action, subject)
        self.info(msg)
    
    def stop(self, action: str, subject: str = "", to_file: bool = False) -> None:
        """记录结束消息"""
        msg = LogHelper.stop(action, subject)
        self.info(msg)
    
    def status_change(self, subject: str, old_status: str, new_status: str, to_file: bool = False) -> None:
        """记录状态变更消息"""
        msg = LogHelper.status_change(subject, old_status, new_status)
        self.info(msg)
    
    def api_response(self, api_name: str, status_code: int, details: str = "", to_file: bool = False) -> None:
        """记录API响应消息"""
        msg = LogHelper.api_response(api_name, status_code, details)
        if 200 <= status_code < 300:
            self.info(msg)
        else:
            self.error(msg)
    
    def query(self, target: str, result: str = "", count: int = None, to_file: bool = False) -> None:
        """记录查询消息"""
        msg = LogHelper.query(target, result, count)
        self.info(msg)
    
    def insert(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """记录插入消息"""
        msg = LogHelper.insert(target, subject, count)
        self.info(msg)
    
    def update(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """记录更新消息"""
        msg = LogHelper.update(target, subject, count)
        self.info(msg)
    
    def delete(self, target: str, subject: str = "", count: int = None, to_file: bool = False) -> None:
        """记录删除消息"""
        msg = LogHelper.delete(target, subject, count)
        self.info(msg)
    
    def warning_msg(self, subject: str, message: str, to_file: bool = True) -> None:
        """记录警告消息"""
        msg = LogHelper.warning(subject, message)
        self.warning(msg)
    
    def warning_console(self, message: str) -> None:
        """
        输出到控制台的警告（不发送到前端监控）
        
        使用场景：
        1. 开发调试临时输出
        2. 敏感信息调试（如密码、token）
        3. 高频调试日志（避免污染前端监控）
        """
        import sys
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        module = self._name if hasattr(self, '_name') else 'unknown'
        
        print(
            f"{timestamp} - WARNING - CONSOLE_ONLY - [{module}] {message}",
            file=sys.stderr
        )
    
    def info_console(self, message: str) -> None:
        """
        输出到控制台的信息（不发送到前端监控）
        
        使用场景：
        1. 开发调试临时输出
        2. 敏感信息调试（如密码、token）
        3. 高频调试日志（避免污染前端监控）
        """
        import sys
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        module = self._name if hasattr(self, '_name') else 'unknown'
        
        print(
            f"{timestamp} - INFO - CONSOLE_ONLY - [{module}] {message}",
            file=sys.stderr
        )
    
    def sync(self, action: str, subject: str = "", details: str = "", to_file: bool = False) -> None:
        """记录同步消息"""
        msg = LogHelper.sync(action, subject, details)
        self.info(msg)
    
    def connect(self, target: str, status: str = "成功", to_file: bool = False) -> None:
        """记录连接消息"""
        msg = LogHelper.connect(target, status)
        if status == "成功":
            self.info(msg)
        else:
            self.error(msg)
    
    def disconnect(self, target: str, to_file: bool = False) -> None:
        """记录断开连接消息"""
        msg = LogHelper.disconnect(target)
        self.info(msg)
    
    def cache(self, action: str, target: str = "", details: str = "", to_file: bool = False) -> None:
        """记录缓存消息"""
        msg = LogHelper.cache(action, target, details)
        self.info(msg)
    
    def set_level(self, level: str) -> None:
        """设置日志级别"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        self._level = level_map.get(level.upper(), logging.INFO)
        self._router.set_level(level)
        
        if self._console_handler:
            self._console_handler.set_level(self._level)
    
    def get_level(self) -> int:
        """获取当前日志级别"""
        return self._level
    
    def enable_target(self, target: str) -> None:
        """启用输出目标"""
        self._targets[target] = True
        
        if target == 'console' and self._console_handler:
            self._console_handler.enable()
        elif target == 'file' and self._file_handler:
            self._file_handler.enable()
        elif target == 'database' and self._database_handler:
            self._database_handler.enable()
        elif target == 'websocket' and self._websocket_handler:
            self._websocket_handler.enable()
    
    def disable_target(self, target: str) -> None:
        """禁用输出目标"""
        self._targets[target] = False
        
        if target == 'console' and self._console_handler:
            self._console_handler.disable()
        elif target == 'file' and self._file_handler:
            self._file_handler.disable()
        elif target == 'database' and self._database_handler:
            self._database_handler.disable()
        elif target == 'websocket' and self._websocket_handler:
            self._websocket_handler.disable()
    
    def set_db_initialized(self, initialized: bool = True) -> None:
        """设置数据库初始化状态"""
        if self._database_handler:
            self._database_handler.mark_db_ready()
    
    def isEnabledFor(self, level: int) -> bool:
        """检查是否启用指定级别"""
        return level >= self._level
    
    def get_logger(self, name: str = None, level: str = None) -> 'SmartLogger':
        """
        获取日志器实例（兼容旧API）
        
        Args:
            name: 日志器名称
            level: 日志级别
            
        Returns:
            SmartLogger实例（返回自身）
        """
        if level:
            self.set_level(level)
        return self
    
    def initialize_logging_unified(self) -> None:
        """初始化统一日志系统（兼容旧API）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._async_init())
            else:
                loop.run_until_complete(self._async_init())
        except Exception:
            pass
    
    async def _async_init(self) -> None:
        """异步初始化"""
        await self.initialize()
    
    def shutdown_logging_unified(self) -> None:
        """关闭统一日志系统（兼容旧API）"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.shutdown())
            else:
                loop.run_until_complete(self.shutdown())
        except Exception:
            pass
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'running': self._running,
            'level': logging.getLevelName(self._level),
            'targets': self._targets,
            'queue': self._queue.get_stats() if self._queue else None
        }
        
        if self._database_handler:
            stats['database'] = self._database_handler.get_stats()
        
        if self._websocket_handler:
            stats['websocket'] = self._websocket_handler.get_stats()
        
        return stats
    
    @property
    def name(self) -> str:
        """获取日志器名称"""
        return self._name
    
    def __repr__(self) -> str:
        return f"<SmartLogger '{self._name}' level={logging.getLevelName(self._level)}>"
