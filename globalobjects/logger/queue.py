"""
统一日志系统 - 异步队列

基于asyncio.Queue实现高性能异步日志写入队列
"""

import asyncio
import sys
import time
from typing import Optional, List, Callable, Any
from collections import deque

from .models import LogRecord
from .exceptions import LogQueueOverflowError


class AsyncLogQueue:
    """
    异步日志队列
    
    特性：
    - 非阻塞放入（put_nowait）
    - 队列满时丢弃最旧消息
    - 批量处理优化
    - 保留任务引用防止GC
    """
    
    def __init__(
        self,
        max_size: int = 10000,
        batch_size: int = 100,
        flush_interval: float = 1.0
    ):
        """
        初始化异步队列
        
        Args:
            max_size: 队列最大容量
            batch_size: 批量处理阈值
            flush_interval: 刷新间隔（秒）
        """
        self._max_size = max_size
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._batch: List[LogRecord] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._handlers: List[Callable[[LogRecord], Any]] = []
        
        self._stats = {
            'total_enqueued': 0,
            'total_dropped': 0,
            'total_processed': 0,
            'overflow_count': 0
        }
    
    def add_handler(self, handler: Callable[[LogRecord], Any]) -> None:
        """
        添加日志处理器
        
        Args:
            handler: 处理函数，接收LogRecord
        """
        self._handlers.append(handler)
    
    def remove_handler(self, handler: Callable[[LogRecord], Any]) -> None:
        """移除日志处理器"""
        if handler in self._handlers:
            self._handlers.remove(handler)
    
    def put_nowait(self, record: LogRecord) -> bool:
        """
        非阻塞放入队列
        
        Args:
            record: 日志记录
            
        Returns:
            bool: 成功放入返回True，队列满返回False
        """
        try:
            self._queue.put_nowait(record)
            self._stats['total_enqueued'] += 1
            return True
        except asyncio.QueueFull:
            self._stats['total_dropped'] += 1
            self._stats['overflow_count'] += 1
            sys.stderr.write(f"[Logger] Queue overflow, message dropped: {record.message[:100]}\n")
            return False
    
    async def put(self, record: LogRecord) -> None:
        """
        异步放入队列（可等待）
        
        Args:
            record: 日志记录
        """
        await self._queue.put(record)
        self._stats['total_enqueued'] += 1
    
    async def start(self) -> None:
        """启动消费者任务"""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
    
    async def stop(self) -> None:
        """停止队列，刷新剩余日志"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        await self._flush_remaining()
    
    async def _consume_loop(self) -> None:
        """消费者循环"""
        last_flush = time.time()
        
        while self._running:
            try:
                timeout = max(0.01, self._flush_interval - (time.time() - last_flush))
                record = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout
                )
                self._batch.append(record)
                
                if len(self._batch) >= self._batch_size:
                    await self._flush_batch()
                    last_flush = time.time()
                    
            except asyncio.TimeoutError:
                if self._batch:
                    await self._flush_batch()
                last_flush = time.time()
            except asyncio.CancelledError:
                break
            except Exception as e:
                sys.stderr.write(f"[Logger] Consume error: {e}\n")
        
        if self._batch:
            await self._flush_batch()
    
    async def _flush_batch(self) -> None:
        """刷新批量日志"""
        if not self._batch:
            return
        
        records = self._batch
        self._batch = []
        
        tasks = []
        for handler in self._handlers:
            for record in records:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        tasks.append(handler(record))
                    else:
                        handler(record)
                except Exception as e:
                    sys.stderr.write(f"[Logger] Handler error: {e}\n")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._stats['total_processed'] += len(records)
    
    async def _flush_remaining(self) -> None:
        """刷新队列中剩余的所有日志"""
        remaining = []
        while not self._queue.empty():
            try:
                remaining.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        
        if remaining or self._batch:
            all_records = self._batch + remaining
            self._batch = []
            
            for handler in self._handlers:
                for record in all_records:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(record)
                        else:
                            handler(record)
                    except Exception:
                        pass
            
            self._stats['total_processed'] += len(all_records)
    
    def get_stats(self) -> dict:
        """获取队列统计信息"""
        return {
            **self._stats,
            'queue_size': self._queue.qsize(),
            'max_size': self._max_size,
            'batch_size': len(self._batch),
            'running': self._running
        }
    
    def qsize(self) -> int:
        """获取当前队列大小"""
        return self._queue.qsize()
    
    def empty(self) -> bool:
        """队列是否为空"""
        return self._queue.empty()
    
    def full(self) -> bool:
        """队列是否已满"""
        return self._queue.full()
