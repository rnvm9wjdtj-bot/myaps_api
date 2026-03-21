"""
事件聚合管理器 - 用于批量处理同类事件

主要功能：
1. 收集同类事件到缓冲区
2. 定时批量处理事件
3. 支持去重
4. 支持分组处理
"""

import threading
import time
import logging
from collections import defaultdict
from typing import Callable, Any, List, Dict, Set

logger = logging.getLogger(__name__)


class EventAggregator:
    """事件聚合管理器"""

    def __init__(self, 
                 handler: Callable[[List[Any]], None],
                 group_key: Callable[[Any], str] = None,
                 dedup_key: Callable[[Any], str] = None,
                 batch_size: int = 100,
                 flush_interval: float = 1.0):
        """
        初始化事件聚合器
        
        Args:
            handler: 批量处理函数，接收事件列表
            group_key: 分组函数，返回分组键，用于将事件分组处理
            dedup_key: 去重函数，返回去重键，相同键的事件会被去重
            batch_size: 批量处理的最大事件数
            flush_interval: 定时刷新间隔（秒）
        """
        self.handler = handler
        self.group_key = group_key
        self.dedup_key = dedup_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        
        # 缓冲区：{group_key: {dedup_key: event}}
        self._buffer: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = threading.RLock()
        self._running = False
        self._timer = None
        
    def add(self, event: Any):
        """添加单个事件到缓冲区"""
        with self._lock:
            # 计算分组键
            g_key = self.group_key(event) if self.group_key else "__default__"
            
            # 计算去重键
            if self.dedup_key:
                d_key = self.dedup_key(event)
                self._buffer[g_key][d_key] = event
            else:
                # 无去重时，使用索引作为键
                idx = len(self._buffer[g_key])
                self._buffer[g_key][str(idx)] = event
            
            # 检查是否达到批量大小
            total_count = sum(len(events) for events in self._buffer.values())
            if total_count >= self.batch_size:
                self._flush()
    
    def add_batch(self, events: List[Any]):
        """批量添加事件"""
        for event in events:
            self.add(event)
    
    def _flush(self):
        """刷新缓冲区，处理所有事件"""
        with self._lock:
            if not self._buffer:
                return
            
            # 复制缓冲区数据
            buffer_copy = dict(self._buffer)
            self._buffer.clear()
        
        # 在锁外处理，避免阻塞
        try:
            for g_key, events_dict in buffer_copy.items():
                events = list(events_dict.values())
                if events:
                    logger.debug(f"处理分组 {g_key} 的 {len(events)} 个事件")
                    self.handler(events)
        except Exception as e:
            logger.error(f"批量处理事件失败: {e}")
    
    def _timer_callback(self):
        """定时器回调"""
        if self._running:
            self._flush()
            self._start_timer()
    
    def _start_timer(self):
        """启动定时器"""
        self._timer = threading.Timer(self.flush_interval, self._timer_callback)
        self._timer.daemon = True
        self._timer.start()
    
    def start(self):
        """启动聚合器"""
        if not self._running:
            self._running = True
            self._start_timer()
            logger.info("事件聚合器已启动")
    
    def stop(self):
        """停止聚合器"""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        # 停止前刷新剩余事件
        self._flush()
        logger.info("事件聚合器已停止")
    
    def flush_now(self):
        """立即刷新缓冲区"""
        self._flush()


class MultiEventAggregator:
    """多类型事件聚合管理器，管理多个不同类型的聚合器"""
    
    def __init__(self):
        self._aggregators: Dict[str, EventAggregator] = {}
        self._lock = threading.RLock()
    
    def register(self, 
                 event_type: str,
                 handler: Callable[[List[Any]], None],
                 group_key: Callable[[Any], str] = None,
                 dedup_key: Callable[[Any], str] = None,
                 batch_size: int = 100,
                 flush_interval: float = 5) -> 'MultiEventAggregator':
        """
        注册一个事件类型的聚合器
        
        Args:
            event_type: 事件类型标识
            handler: 批量处理函数
            group_key: 分组函数
            dedup_key: 去重函数
            batch_size: 批量大小
            flush_interval: 刷新间隔（秒）
        
        Returns:
            self，支持链式调用
        """
        with self._lock:
            aggregator = EventAggregator(
                handler=handler,
                group_key=group_key,
                dedup_key=dedup_key,
                batch_size=batch_size,
                flush_interval=flush_interval
            )
            self._aggregators[event_type] = aggregator
            aggregator.start()
            return self
    
    def add(self, event_type: str, event: Any):
        """添加事件到指定类型的聚合器"""
        with self._lock:
            if event_type in self._aggregators:
                self._aggregators[event_type].add(event)
    
    def add_batch(self, event_type: str, events: List[Any]):
        """批量添加事件到指定类型的聚合器"""
        with self._lock:
            if event_type in self._aggregators:
                self._aggregators[event_type].add_batch(events)
    
    def stop(self, event_type: str = None):
        """停止聚合器
        
        Args:
            event_type: 指定事件类型，None表示停止所有
        """
        with self._lock:
            if event_type:
                if event_type in self._aggregators:
                    self._aggregators[event_type].stop()
                    del self._aggregators[event_type]
            else:
                for aggregator in self._aggregators.values():
                    aggregator.stop()
                self._aggregators.clear()
    
    def flush_now(self, event_type: str = None):
        """立即刷新
        
        Args:
            event_type: 指定事件类型，None表示刷新所有
        """
        with self._lock:
            if event_type:
                if event_type in self._aggregators:
                    self._aggregators[event_type].flush_now()
            else:
                for aggregator in self._aggregators.values():
                    aggregator.flush_now()


# 全局多事件聚合管理器实例
_global_handler_aggregator = MultiEventAggregator()


def get_global_handler_aggregator() -> MultiEventAggregator:
    """获取全局处理事件聚合管理器"""
    return _global_handler_aggregator
