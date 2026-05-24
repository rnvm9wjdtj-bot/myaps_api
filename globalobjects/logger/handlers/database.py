"""
统一日志系统 - 数据库处理器

支持批量写入、初始化等待、故障降级
"""

import os
import sys
import time
import logging
import threading
import asyncio
from datetime import datetime
from typing import Optional, List, Any

from ..models import LogRecord
from .base import Handler


class DatabaseHandler(Handler):
    """
    数据库处理器
    
    特性：
    - 异步批量写入
    - ORM初始化前的内存缓冲
    - 数据库故障降级
    - 批量提交优化性能
    """
    
    def __init__(
        self,
        level: int = logging.INFO,
        enabled: bool = True,
        batch_size: int = 100,
        flush_interval: float = 1.0,
        buffer_size: int = 1000
    ):
        """
        初始化数据库处理器
        
        Args:
            level: 最低日志级别
            enabled: 是否启用
            batch_size: 批量写入大小
            flush_interval: 刷新间隔（秒）
            buffer_size: 初始化前缓冲区大小
        """
        super().__init__(level, enabled)
        
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer_size = buffer_size
        
        self._batch: List[LogRecord] = []
        self._buffer: List[LogRecord] = []
        self._db_ready = False
        self._lock = threading.Lock()
        
        self._stats = {
            'total_written': 0,
            'total_failed': 0,
            'batch_writes': 0
        }
    
    def emit(self, record: LogRecord) -> None:
        """写入数据库（异步）"""
        if not self._enabled:
            return
        
        if not self._db_ready:
            with self._lock:
                if len(self._buffer) < self._buffer_size:
                    self._buffer.append(record)
                else:
                    self._buffer.pop(0)
                    self._buffer.append(record)
            return
        
        with self._lock:
            self._batch.append(record)
    
    async def emit_async(self, record: LogRecord) -> None:
        """异步写入"""
        self.emit(record)
        
        if len(self._batch) >= self._batch_size:
            await self._flush()
    
    def mark_db_ready(self) -> None:
        """标记数据库就绪"""
        self._db_ready = True
        
        with self._lock:
            if self._buffer:
                self._batch.extend(self._buffer)
                self._buffer.clear()
    
    def is_db_ready(self) -> bool:
        """数据库是否就绪"""
        return self._db_ready
    
    async def flush(self) -> None:
        """刷新批量日志到数据库"""
        await self._flush()
    
    async def _flush(self) -> None:
        """内部刷新方法"""
        if not self._batch:
            return
        
        records = self._batch
        self._batch = []
        
        try:
            await self._write_to_database(records)
            self._stats['total_written'] += len(records)
            self._stats['batch_writes'] += 1
        except Exception as e:
            self._stats['total_failed'] += len(records)
            sys.stderr.write(f"[DatabaseHandler] Write failed: {e}\n")
    
    async def _write_to_database(self, records: List[LogRecord]) -> None:
        """
        写入数据库
        
        Args:
            records: 日志记录列表
        """
        # 检查 Tortoise ORM 是否真正初始化完成
        try:
            from tortoise import Tortoise
            if not Tortoise._inited:
                # ORM 未就绪，将记录重新放入缓冲区，等待下次 flush
                with self._lock:
                    for r in records:
                        if len(self._buffer) < self._buffer_size:
                            self._buffer.append(r)
                return
        except ImportError:
            pass
        
        try:
            from apps.common.monitor.models import SystemLog
            from core.settings import SQLITE_FILE
        except Exception:
            return
        
        try:
            SystemLog._meta.default_connection = SQLITE_FILE
        except Exception:
            pass
        
        logs = []
        for r in records:
            try:
                log = SystemLog(
                    level=r.level_name,
                    module=r.module or '',
                    function=r.function or '',
                    line_number=r.line or 0,
                    message=r.message,
                    details=str(r.extra) if r.extra else None,
                    stack_trace=r.stack_trace,
                    process_id=os.getpid(),
                    thread_id=threading.get_ident(),
                    thread_name=threading.current_thread().name
                )
                logs.append(log)
            except Exception:
                continue
        
        if logs:
            try:
                await SystemLog.bulk_create(logs)
            except Exception as e:
                # 数据库写入失败，将记录重新放入缓冲区等待重试
                error_msg = str(e)
                if "not initialised" in error_msg.lower() or "configuration" in error_msg.lower():
                    with self._lock:
                        for r in records:
                            if len(self._buffer) < self._buffer_size:
                                self._buffer.append(r)
                else:
                    raise
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            **self._stats,
            'db_ready': self._db_ready,
            'batch_size': len(self._batch),
            'buffer_size': len(self._buffer)
        }
    
    def clear_buffer(self) -> int:
        """
        清空缓冲区
        
        Returns:
            int: 清空的记录数
        """
        with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
            return count
    
    def clear_batch(self) -> int:
        """
        清空批量队列
        
        Returns:
            int: 清空的记录数
        """
        with self._lock:
            count = len(self._batch)
            self._batch.clear()
            return count
    
    def close(self) -> None:
        """关闭处理器"""
        pass
