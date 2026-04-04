"""
事件聚合管理器 - 用于批量处理同类事件

主要功能：
1. 收集同类事件到缓冲区
2. 定时批量处理事件
3. 支持去重
4. 支持分组处理
"""
import os
import threading
import time
from collections import defaultdict
from typing import Callable, Any, List, Dict, Set
from concurrent.futures import ThreadPoolExecutor

from globalobjects import logger as log_config

import os
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"

logger = log_config.get_logger(__name__, level=LOG_LEVEL)

# 全局线程池，用于处理事件批次
# 根据系统CPU核心数设置线程池大小
import multiprocessing
CPU_COUNT = multiprocessing.cpu_count() or 4
GLOBAL_THREAD_POOL = ThreadPoolExecutor(max_workers=CPU_COUNT * 2)




class EventAggregator:
    """事件聚合管理器"""

    def __init__(self, 
                 handler: Callable[[List[Any]], None],
                 group_key: Callable[[Any], str] = None,
                 dedup_key: Callable[[Any], str] = None,
                 batch_size: int = 10000,
                 flush_interval: float = 5.0,
                 name: str = "unnamed"):
        """
        初始化事件聚合器
        
        Args:
            handler: 批量处理函数，接收事件列表
            group_key: 分组函数，返回分组键，用于将事件分组处理
            dedup_key: 去重函数，返回去重键，相同键的事件会被去重
            batch_size: 批量处理的最大事件数
            flush_interval: 定时刷新间隔（秒）
            name: 聚合器名称，用于日志和调试
        """
        self.handler = handler
        self.group_key = group_key
        self.dedup_key = dedup_key
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.name = name
        
        # 缓冲区：{group_key: {dedup_key: event}}
        self._buffer: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._running = False
        self._condition_thread = None
        
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
                # 达到批量大小，通知条件变量线程
                self._condition.notify()

    
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
        
        # 提交到全局线程池处理，实现批次间并行
        GLOBAL_THREAD_POOL.submit(self._process_batch, buffer_copy)
    
    def _process_batch(self, buffer_copy):
        """处理单个批次的事件"""
        try:
            for g_key, events_dict in buffer_copy.items():
                events = list(events_dict.values())
                if events:
                    logger.debug(f"处理分组{g_key}的{len(events)}个事件")
                    self.handler(events)
        except Exception as e:
            logger.fail("批量处理事件", "", str(e))
    
    def _condition_thread_func(self):
        """条件变量线程函数"""
        while self._running:
            with self._lock:
                # 等待直到有事件通知或超时
                # 计算当前缓冲区大小
                total_count = sum(len(events) for events in self._buffer.values())
                # 如果缓冲区为空，等待指定时间
                if total_count == 0:
                    # 等待指定的刷新间隔
                    self._condition.wait(timeout=self.flush_interval)
                # 无论是否有通知，检查是否需要刷新
                # 1. 缓冲区不为空
                # 2. 或者达到刷新间隔（即使缓冲区为空也刷新）
                if self._buffer:
                    self._flush()
    
    def start(self):
        """启动聚合器"""
        if not self._running:
            self._running = True
            # 启动条件变量线程
            self._condition_thread = threading.Thread(
                target=self._condition_thread_func,
                name=f"event-aggregator-{self.name}"
            )
            self._condition_thread.daemon = True
            self._condition_thread.start()
            logger.start(f"事件聚合器: {self.name}")
    
    def stop(self):
        """停止聚合器"""
        if self._running:
            self._running = False
            # 通知条件变量线程结束
            with self._lock:
                self._condition.notify()
            if self._condition_thread:
                logger.debug(f"等待事件聚合器线程结束: {self.name}")
                self._condition_thread.join(timeout=5.0)
                if self._condition_thread.is_alive():
                    logger.warning(f"事件聚合器线程未能正常结束: {self.name}")
                self._condition_thread = None
            # 停止前刷新剩余事件
            self._flush()
            logger.stop(f"事件聚合器: {self.name}")
    
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
                 batch_size: int = 10000,
                 flush_interval: float = 5.0) -> 'MultiEventAggregator':
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
            # 检查事件类型是否已经注册
            if event_type in self._aggregators:
                logger.warning(f"事件类型 {event_type} 已经注册，将停止并重新注册")
                self._aggregators[event_type].stop()
                del self._aggregators[event_type]
            
            aggregator = EventAggregator(
                handler=handler,
                group_key=group_key,
                dedup_key=dedup_key,
                batch_size=batch_size,
                flush_interval=flush_interval,
                name=event_type
            )
            self._aggregators[event_type] = aggregator
            aggregator.start()
            logger.success(f"事件聚合器注册", event_type, "")
            return self
    
    def add(self, event_type: str, event: Any):
        """添加事件到指定类型的聚合器"""
        with self._lock:
            if event_type in self._aggregators:
                logger.start(f"添加事件到聚合器，刷新间隔{self._aggregators[event_type].flush_interval}秒", event_type)
                logger.debug(f"{event}")
                self._aggregators[event_type].add(event)
    
    def add_batch(self, event_type: str, events: List[Any]):
        """批量添加事件到指定类型的聚合器"""
        with self._lock:
            if event_type in self._aggregators:
                logger.start(f"批量添加事件到聚合器，刷新间隔{self._aggregators[event_type].flush_interval}秒", event_type)
                logger.debug(f"{events}")
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
                    logger.start(f"立即刷新聚合器{event_type}，刷新间隔{self._aggregators[event_type].flush_interval}秒")
                    self._aggregators[event_type].flush_now()
            else:
                for aggregator in self._aggregators.values():
                    aggregator.flush_now()


# 全局多事件聚合管理器实例
_global_handler_aggregator = MultiEventAggregator()


def get_global_handler_aggregator() -> MultiEventAggregator:
    """获取全局处理事件聚合管理器"""
    return _global_handler_aggregator


# 使用示例
if __name__ == "__main__":
    import time
    
    # 示例1: 基本使用
    def basic_handler(events):
        print(f"基本处理: 收到 {len(events)} 个事件")
        for event in events:
            print(f"  - 事件: {event}")
    
    # 创建聚合器
    aggregator1 = EventAggregator(
        handler=basic_handler,
        batch_size=5,
        flush_interval=2.0
    )
    
    # 启动聚合器
    aggregator1.start()
    
    # 添加事件
    print("示例1: 基本使用")
    for i in range(7):
        aggregator1.add(f"事件{i}")
        time.sleep(0.5)
    
    # 等待一段时间让聚合器处理事件
    time.sleep(3)
    
    # 停止聚合器
    aggregator1.stop()
    
    print("\n" + "-" * 50 + "\n")
    
    # 示例2: 使用去重功能
    def dedup_handler(events):
        print(f"去重处理: 收到 {len(events)} 个事件")
        for event in events:
            print(f"  - 事件: {event}")
    
    # 去重函数: 使用事件内容作为去重键
    def dedup_key_func(event):
        return event
    
    aggregator2 = EventAggregator(
        handler=dedup_handler,
        dedup_key=dedup_key_func,
        batch_size=3,
        flush_interval=1.0
    )
    
    aggregator2.start()
    
    print("示例2: 使用去重功能")
    # 添加重复事件
    aggregator2.add("重复事件")
    aggregator2.add("唯一事件1")
    aggregator2.add("重复事件")  # 这个会被去重
    aggregator2.add("唯一事件2")
    aggregator2.add("重复事件")  # 这个会被去重
    
    time.sleep(2)
    aggregator2.stop()
    
    print("\n" + "-" * 50 + "\n")
    
    # 示例3: 使用分组功能
    def group_handler(events):
        print(f"分组处理: 收到 {len(events)} 个事件")
        for event in events:
            print(f"  - 事件: {event}")
    
    # 分组函数: 根据事件类型分组
    def group_key_func(event):
        return event["type"]
    
    aggregator3 = EventAggregator(
        handler=group_handler,
        group_key=group_key_func,
        batch_size=4,
        flush_interval=1.5
    )
    
    aggregator3.start()
    
    print("示例3: 使用分组功能")
    # 添加不同类型的事件
    aggregator3.add({"type": "user", "data": "用户1"})
    aggregator3.add({"type": "order", "data": "订单1"})
    aggregator3.add({"type": "user", "data": "用户2"})
    aggregator3.add({"type": "order", "data": "订单2"})
    aggregator3.add({"type": "user", "data": "用户3"})
    
    time.sleep(2)
    aggregator3.stop()
    
    print("\n" + "-" * 50 + "\n")
    
    # 示例4: 使用MultiEventAggregator
    def user_handler(events):
        print(f"用户事件处理: 收到 {len(events)} 个事件")
    
    def order_handler(events):
        print(f"订单事件处理: 收到 {len(events)} 个事件")
    
    multi_aggregator = MultiEventAggregator()
    
    # 注册不同类型的事件处理器
    multi_aggregator.register(
        event_type="user",
        handler=user_handler,
        batch_size=3,
        flush_interval=1.0
    ).register(
        event_type="order",
        handler=order_handler,
        batch_size=2,
        flush_interval=1.5
    )
    
    print("示例4: 使用MultiEventAggregator")
    # 添加不同类型的事件
    multi_aggregator.add("user", "用户事件1")
    multi_aggregator.add("order", "订单事件1")
    multi_aggregator.add("user", "用户事件2")
    multi_aggregator.add("order", "订单事件2")
    multi_aggregator.add("user", "用户事件3")
    
    time.sleep(2)
    multi_aggregator.stop()
    
    print("\n" + "-" * 50 + "\n")
    
    # 示例5: 使用全局聚合器
    def global_handler(events):
        print(f"全局处理: 收到 {len(events)} 个事件")
    
    global_aggregator = get_global_handler_aggregator()
    
    # 注册事件类型
    global_aggregator.register(
        event_type="global_event",
        handler=global_handler,
        batch_size=4,
        flush_interval=2.0
    )
    
    print("示例5: 使用全局聚合器")
    # 添加事件
    for i in range(6):
        global_aggregator.add("global_event", f"全局事件{i}")
        time.sleep(0.3)
    
    time.sleep(3)
    global_aggregator.stop("global_event")
    
    print("\n所有示例执行完成！")
