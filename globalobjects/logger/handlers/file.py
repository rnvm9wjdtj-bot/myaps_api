"""
统一日志系统 - 文件处理器

支持日期前缀命名、自动轮转、历史文件清理
"""

import os
import sys
import time
import logging
import threading
import glob as glob_module
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from ..models import LogRecord
from .base import Handler


class DatePrefixFileHandler(Handler):
    """
    日期前缀文件处理器
    
    特性：
    - 文件名格式：{YYYYMMDD}_{prefix}.log
    - 支持日期变更轮转
    - 支持文件大小轮转
    - 自动清理过期文件
    - 线程安全
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        prefix: str = "app",
        level: int = logging.WARNING,
        enabled: bool = True,
        max_size: int = 100 * 1024 * 1024,
        retention_days: int = 7,
        encoding: str = "utf-8"
    ):
        """
        初始化文件处理器
        
        Args:
            log_dir: 日志目录
            prefix: 文件前缀
            level: 最低日志级别
            enabled: 是否启用
            max_size: 单文件最大大小（字节）
            retention_days: 保留天数
            encoding: 文件编码
        """
        super().__init__(level, enabled)
        
        self._log_dir = Path(log_dir)
        self._prefix = prefix
        self._max_size = max_size
        self._retention_days = retention_days
        self._encoding = encoding
        
        self._current_file: Optional[object] = None
        self._current_date: str = ""
        self._current_size: int = 0
        self._lock = threading.Lock()
        
        self._ensure_log_dir()
        self._open_file()
    
    def _ensure_log_dir(self) -> None:
        """确保日志目录存在"""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            sys.stderr.write(f"[FileHandler] Failed to create log dir: {e}\n")
    
    def _get_today_str(self) -> str:
        """获取今天的日期字符串"""
        return datetime.now().strftime("%Y%m%d")
    
    def _get_current_filename(self) -> str:
        """获取当前日志文件名"""
        return f"{self._current_date}_{self._prefix}.log"
    
    def _open_file(self) -> None:
        """打开当前日志文件"""
        self._current_date = self._get_today_str()
        filename = self._get_current_filename()
        filepath = self._log_dir / filename
        
        try:
            self._current_file = open(filepath, 'a', encoding=self._encoding)
            
            try:
                self._current_size = filepath.stat().st_size
            except Exception:
                self._current_size = 0
                
        except Exception as e:
            sys.stderr.write(f"[FileHandler] Failed to open file: {e}\n")
            self._current_file = None
    
    def emit(self, record: LogRecord) -> None:
        """写入日志文件"""
        with self._lock:
            if self._current_file is None:
                return
            
            self._check_rotation()
            
            message = self._format(record)
            
            try:
                self._current_file.write(message + '\n')
                self._current_file.flush()
                self._current_size += len(message.encode(self._encoding)) + 1
            except Exception as e:
                sys.stderr.write(f"[FileHandler] Write failed: {e}\n")
    
    def _format(self, record: LogRecord) -> str:
        """格式化日志消息"""
        timestamp = record.timestamp.strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        
        parts = [timestamp, record.level_name]
        
        if record.module:
            parts.append(record.module)
        if record.function:
            parts.append(f"{record.function}:{record.line or 0}")
        
        parts.append(record.message)
        
        return ' - '.join(parts)
    
    def _check_rotation(self) -> None:
        """检查是否需要轮转"""
        today = self._get_today_str()
        
        if today != self._current_date:
            self._rotate(today)
            return
        
        if self._current_size >= self._max_size:
            self._rotate(today)
    
    def _rotate(self, new_date: str) -> None:
        """执行轮转"""
        if self._current_file:
            try:
                self._current_file.close()
            except Exception:
                pass
            self._current_file = None
        
        self._current_date = new_date
        self._open_file()
        
        self._cleanup_old_files()
    
    def _cleanup_old_files(self) -> None:
        """清理过期日志文件"""
        if self._retention_days <= 0:
            return
        
        cutoff_date = datetime.now() - timedelta(days=self._retention_days)
        cutoff_str = cutoff_date.strftime("%Y%m%d")
        
        pattern = str(self._log_dir / f"????????_{self._prefix}.log")
        
        try:
            for filepath in glob_module.glob(pattern):
                filename = os.path.basename(filepath)
                date_str = filename[:8]
                
                if date_str < cutoff_str:
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
        except Exception:
            pass
    
    def close(self) -> None:
        """关闭文件处理器"""
        with self._lock:
            if self._current_file:
                try:
                    self._current_file.close()
                except Exception:
                    pass
                self._current_file = None


from datetime import timedelta


class SmartFileHandler(Handler):
    """
    智能文件处理器
    
    根据日志级别选择不同的文件：
    - WARNING及以上写入app.log
    - ERROR及以上写入error.log
    """
    
    def __init__(
        self,
        log_dir: str = "logs",
        level: int = logging.WARNING,
        enabled: bool = True,
        retention_days: int = 7
    ):
        super().__init__(level, enabled)
        
        self._app_handler = DatePrefixFileHandler(
            log_dir=log_dir,
            prefix="app",
            level=logging.WARNING,
            enabled=True,
            retention_days=retention_days
        )
        
        self._error_handler = DatePrefixFileHandler(
            log_dir=log_dir,
            prefix="error",
            level=logging.ERROR,
            enabled=True,
            retention_days=retention_days
        )
    
    def emit(self, record: LogRecord) -> None:
        """写入日志文件"""
        if record.level >= logging.ERROR:
            self._error_handler.handle(record)
        
        if record.level >= logging.WARNING:
            self._app_handler.handle(record)
    
    def close(self) -> None:
        """关闭处理器"""
        self._app_handler.close()
        self._error_handler.close()
