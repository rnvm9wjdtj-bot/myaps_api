"""
事件聚合管理器 - 用于批量处理同类事件

主要功能：
1. 收集同类事件到缓冲区
2. 定时批量处理事件
3. 支持去重
4. 支持分组处理
5. 支持独立线程池隔离

线程池策略：
- 每个事件类型拥有独立的线程池，避免争抢
- 线程池大小根据事件类型静态配置
- 支持线程池监控
"""
import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Any, List, Dict, Set, Optional
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from globalobjects import logger as log_config

import os
LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"

logger = log_config.get_logger(__name__, level=LOG_LEVEL)

import multiprocessing
CPU_COUNT = multiprocessing.cpu_count() or 4


class EventThreadPoolManager:
    """事件类型独立线程池管理器"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._pools: Dict[str, ThreadPoolExecutor] = {}
        self._pool_configs: Dict[str, Dict] = {}
        self._pool_locks: Dict[str, Lock] = {}
        self._global_lock = Lock()
        
        # 动态调整相关
        self._pool_stats: Dict[str, Dict] = {}  # 线程池运行时统计
        self._adjust_thread: Optional[threading.Thread] = None
        self._adjust_running = False
        self._adjust_interval = 10  # 调整检查间隔（秒）
        self._scale_up_threshold = 50  # 队列长度超过此值时扩容
        self._scale_down_threshold = 5  # 队列长度低于此值时缩容
        self._cooldown_time = 30  # 调整冷却时间（秒）
        
        self._initialized = True

        self._register_default_pools()
        self._start_adjust_thread()

    def _register_default_pools(self):
        """注册默认线程池配置"""
        default_configs = {
            'pl_status_a2e': {
                'min_workers': 3,
                'max_workers': 10,
                'description': 'PL状态变更A2E事件'
            },
            'pr_created': {
                'min_workers': 2,
                'max_workers': 6,
                'description': 'PR创建事件'
            },
            'pl_to_mo': {
                'min_workers': 2,
                'max_workers': 6,
                'description': 'PL变更为MO事件'
            },
            'pr_deleted': {
                'min_workers': 1,
                'max_workers': 4,
                'description': 'PR删除事件'
            },
            'default': {
                'min_workers': 2,
                'max_workers': 5,
                'description': '默认事件'
            }
        }

        for name, config in default_configs.items():
            self.register_pool(name, **config)

    def register_pool(self, name: str, min_workers: int = 2, max_workers: int = 5, description: str = ''):
        """注册一个事件类型的线程池"""
        with self._global_lock:
            if name in self._pools:
                logger.warning(f"线程池 {name} 已存在，将重新创建")
                self._pools[name].shutdown(wait=False)
                del self._pools[name]

            self._pool_configs[name] = {
                'min_workers': min_workers,
                'max_workers': max_workers,
                'description': description
            }
            self._pool_locks[name] = Lock()
            self._pools[name] = ThreadPoolExecutor(
                max_workers=min_workers,
                thread_name_prefix=f'event-{name}-'
            )
            logger.success(f"事件线程池注册", name, f"min={min_workers}, max={max_workers}")

    def get_pool(self, name: str) -> Optional[ThreadPoolExecutor]:
        """获取事件类型的线程池，如果不存在则自动注册"""
        with self._global_lock:
            if name not in self._pools:
                logger.info(f"线程池 {name} 不存在，自动注册独立线程池")
                self._pool_configs[name] = {
                    'min_workers': 2,
                    'max_workers': 5,
                    'description': f'自动注册的事件线程池: {name}'
                }
                self._pool_locks[name] = Lock()
                self._pools[name] = ThreadPoolExecutor(
                    max_workers=2,
                    thread_name_prefix=f'event-{name}-'
                )
                logger.success(f"事件线程池自动注册", name, "min=2, max=5")
            return self._pools.get(name)

    def get_pool_stats(self, name: str) -> Dict:
        """获取线程池统计信息"""
        with self._global_lock:
            if name not in self._pool_configs:
                return {}

            config = self._pool_configs[name]
            pool = self._pools.get(name)

            return {
                'name': name,
                'min_workers': config['min_workers'],
                'max_workers': config['max_workers'],
                'description': config['description'],
                'pool_active': pool is not None and not pool._shutdown,
            }

    def get_all_stats(self) -> Dict[str, Dict]:
        """获取所有线程池的统计信息"""
        return {name: self.get_pool_stats(name) for name in self._pool_configs.keys()}

    def shutdown_all(self):
        """关闭所有线程池"""
        self._stop_adjust_thread()
        with self._global_lock:
            for name, pool in self._pools.items():
                pool.shutdown(wait=True)
                logger.info(f"线程池已关闭", name)
            self._pools.clear()

    def _start_adjust_thread(self):
        """启动动态调整监控线程"""
        if self._adjust_thread is not None and self._adjust_thread.is_alive():
            return
        
        self._adjust_running = True
        self._adjust_thread = threading.Thread(
            target=self._adjust_loop,
            daemon=True,
            name='event-pool-adjuster'
        )
        self._adjust_thread.start()
        logger.info("✅ 事件线程池动态调整线程已启动")

    def _stop_adjust_thread(self):
        """停止动态调整监控线程"""
        self._adjust_running = False
        if self._adjust_thread and self._adjust_thread.is_alive():
            self._adjust_thread.join(timeout=5)
        logger.info("🛑 事件线程池动态调整线程已停止")

    def _adjust_loop(self):
        """动态调整循环"""
        while self._adjust_running:
            try:
                self._check_and_adjust_pools()
            except Exception as e:
                logger.error(f"线程池动态调整检查失败: {e}")
            
            time.sleep(self._adjust_interval)

    def _check_and_adjust_pools(self):
        """检查并调整所有线程池"""
        with self._global_lock:
            for name in list(self._pools.keys()):
                try:
                    self._adjust_pool_size(name)
                except Exception as e:
                    logger.warning(f"调整线程池 {name} 失败: {e}")

    def _adjust_pool_size(self, name: str):
        """
        调整单个线程池的大小
        
        扩容条件：队列长度 > scale_up_threshold
        缩容条件：队列长度 < scale_down_threshold 且持续一段时间
        """
        if name not in self._pools or name not in self._pool_configs:
            return
        
        pool = self._pools[name]
        config = self._pool_configs[name]
        
        if pool._shutdown:
            return
        
        # 获取队列长度
        queue_size = self._get_queue_size(pool)
        current_workers = getattr(pool, '_max_workers', config['min_workers'])
        min_workers = config['min_workers']
        max_workers = config['max_workers']
        
        # 初始化统计
        if name not in self._pool_stats:
            self._pool_stats[name] = {
                'last_adjust_time': 0,
                'low_queue_count': 0,
                'current_workers': current_workers
            }
        
        stats = self._pool_stats[name]
        now = time.time()
        
        # 检查冷却时间
        if now - stats['last_adjust_time'] < self._cooldown_time:
            return
        
        target_workers = current_workers
        
        # 扩容逻辑
        if queue_size > self._scale_up_threshold and current_workers < max_workers:
            target_workers = min(current_workers + 1, max_workers)
            logger.info(f"📈 线程池 {name} 队列堆积({queue_size})，扩容: {current_workers} → {target_workers}")
        
        # 缩容逻辑（需要连续多次检测队列都较低）
        elif queue_size < self._scale_down_threshold:
            stats['low_queue_count'] = stats.get('low_queue_count', 0) + 1
            if stats['low_queue_count'] >= 3 and current_workers > min_workers:
                target_workers = max(current_workers - 1, min_workers)
                logger.info(f"📉 线程池 {name} 队列空闲({queue_size})，缩容: {current_workers} → {target_workers}")
                stats['low_queue_count'] = 0
        else:
            stats['low_queue_count'] = 0
        
        # 执行调整
        if target_workers != current_workers:
            self._resize_pool(name, target_workers)
            stats['last_adjust_time'] = now
            stats['current_workers'] = target_workers

    def _get_queue_size(self, pool: ThreadPoolExecutor) -> int:
        """获取线程池工作队列大小"""
        try:
            if hasattr(pool, '_work_queue'):
                return pool._work_queue.qsize()
            return 0
        except Exception:
            return 0

    def _resize_pool(self, name: str, new_size: int):
        """
        调整线程池大小
        
        注意：Python ThreadPoolExecutor 不支持动态调整 max_workers
        这里采用创建新线程池的方式实现
        """
        if name not in self._pools:
            return
        
        old_pool = self._pools[name]
        config = self._pool_configs[name]
        
        # 创建新线程池
        new_pool = ThreadPoolExecutor(
            max_workers=new_size,
            thread_name_prefix=f'event-{name}-'
        )
        
        # 替换线程池（旧线程池会在现有任务完成后自动关闭）
        self._pools[name] = new_pool
        
        # 标记旧线程池为待关闭
        try:
            old_pool.shutdown(wait=False)
        except Exception:
            pass
        
        logger.success(f"线程池大小调整", name, f"workers={new_size}")

    def get_pool_detailed_stats(self, name: str) -> Dict:
        """获取线程池详细统计信息"""
        with self._global_lock:
            if name not in self._pool_configs:
                return {}

            config = self._pool_configs[name]
            pool = self._pools.get(name)
            stats = self._pool_stats.get(name, {})

            queue_size = 0
            active_count = 0
            
            if pool and not pool._shutdown:
                queue_size = self._get_queue_size(pool)
                if hasattr(pool, '_threads'):
                    active_count = len([t for t in pool._threads if t.is_alive()])

            return {
                'name': name,
                'min_workers': config['min_workers'],
                'max_workers': config['max_workers'],
                'current_workers': stats.get('current_workers', config['min_workers']),
                'active_threads': active_count,
                'queue_size': queue_size,
                'description': config['description'],
                'pool_active': pool is not None and not pool._shutdown,
                'last_adjust_time': stats.get('last_adjust_time', 0),
            }

    def get_all_detailed_stats(self) -> Dict[str, Dict]:
        """获取所有线程池的详细统计信息"""
        return {name: self.get_pool_detailed_stats(name) for name in self._pool_configs.keys()}

    def set_adjust_config(self, 
                          adjust_interval: int = None,
                          scale_up_threshold: int = None,
                          scale_down_threshold: int = None,
                          cooldown_time: int = None):
        """
        配置动态调整参数
        
        Args:
            adjust_interval: 调整检查间隔（秒）
            scale_up_threshold: 扩容阈值（队列长度）
            scale_down_threshold: 缩容阈值（队列长度）
            cooldown_time: 调整冷却时间（秒）
        """
        if adjust_interval is not None:
            self._adjust_interval = adjust_interval
        if scale_up_threshold is not None:
            self._scale_up_threshold = scale_up_threshold
        if scale_down_threshold is not None:
            self._scale_down_threshold = scale_down_threshold
        if cooldown_time is not None:
            self._cooldown_time = cooldown_time
        
        logger.info(f"动态调整参数已更新: interval={self._adjust_interval}s, "
                   f"scale_up={self._scale_up_threshold}, scale_down={self._scale_down_threshold}, "
                   f"cooldown={self._cooldown_time}s")


_event_pool_manager: Optional[EventThreadPoolManager] = None


def get_event_pool_manager() -> EventThreadPoolManager:
    """获取事件线程池管理器单例"""
    global _event_pool_manager
    if _event_pool_manager is None:
        _event_pool_manager = EventThreadPoolManager()
    return _event_pool_manager




class EventAggregator:
    """事件聚合管理器"""

    def __init__(self, 
                 handler: Callable[[List[Any]], None],
                 group_key: Callable[[Any], str] = None,
                 dedup_key: Callable[[Any], str] = None,
                 batch_size: int = 10000,
                 quiet_window: float = 10.0,
                 flush_interval: float = 5.0,
                 name: str = "unnamed"):
        """
        初始化事件聚合器
        
        Args:
            handler: 批量处理函数，接收事件列表
            group_key: 分组函数，返回分组键，用于将事件分组处理
            dedup_key: 去重函数，返回去重键，相同键的事件会被去重
            batch_size: 批量处理的最大事件数
            quiet_window: 安静窗口（秒），连续无新事件达到此时间后触发批量处理
            flush_interval: 定时刷新间隔（秒），仅在缓冲区为空时生效
            name: 聚合器名称，用于日志和调试
        """
        self.handler = handler
        self.group_key = group_key
        self.dedup_key = dedup_key
        self.batch_size = batch_size
        self.quiet_window = quiet_window
        self.flush_interval = flush_interval
        self.name = name

        self._last_event_time = 0.0
        self._last_flush_time = 0

        # 缓冲区：{group_key: {dedup_key: event}}
        self._buffer: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._running = False
        self._condition_thread = None
        
        # 统计数据
        self.stats = {
            'total_received': 0,
            'total_processed': 0,
            'total_failed': 0,
            'processing_latencies': deque(maxlen=1000),
            'received_timestamps': deque(maxlen=3600),
            'processed_timestamps': deque(maxlen=3600),
            'first_received_time': None,
            'last_activity_time': None,
        }
        
    def add(self, event: Any):
        """添加单个事件到缓冲区"""
        with self._lock:
            now = time.time()
            
            # 更新统计数据
            self.stats['total_received'] += 1
            self.stats['received_timestamps'].append(now)
            if self.stats['first_received_time'] is None:
                self.stats['first_received_time'] = now
            self.stats['last_activity_time'] = now
            
            # 重置安静窗口计时器
            self._last_event_time = now
            
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
                # 达到批量大小，立即刷新
                self._flush()
                self._last_flush_time = now
                self._last_event_time = now

    
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

        # 提交到事件专属线程池处理，实现批次间并行且隔离
        pool_manager = get_event_pool_manager()
        event_pool = pool_manager.get_pool(self.name)
        if event_pool:
            event_pool.submit(self._process_batch, buffer_copy)
        else:
            logger.warning(f"未找到事件线程池 {self.name}，使用默认线程池")
            default_pool = pool_manager.get_pool('default')
            if default_pool:
                default_pool.submit(self._process_batch, buffer_copy)
    
    def _process_batch(self, buffer_copy):
        """处理单个批次的事件"""
        start_time = time.time()
        total_events = sum(len(events_dict.values()) for events_dict in buffer_copy.values())
        
        try:
            for g_key, events_dict in buffer_copy.items():
                events = list(events_dict.values())
                if events:
                    logger.debug(f"处理分组{g_key}的{len(events)}个事件")
                    self.handler(events)
            
            # 更新成功统计
            end_time = time.time()
            with self._lock:
                self.stats['total_processed'] += total_events
                self.stats['processed_timestamps'].append(end_time)
                self.stats['processing_latencies'].append((end_time - start_time) * 1000)
                self.stats['last_activity_time'] = end_time
        except Exception as e:
            # 更新失败统计
            end_time = time.time()
            with self._lock:
                self.stats['total_failed'] += total_events
                self.stats['last_activity_time'] = end_time
            logger.fail("批量处理事件", "", str(e))
    
    def get_stats(self):
        """获取统计数据
        
        Returns:
            dict: 包含统计信息的字典
        """
        with self._lock:
            stats = self.stats.copy()
            now = time.time()
            
            # 计算待处理数
            pending_count = sum(len(events) for events in self._buffer.values())
            
            # 计算时间窗口统计
            one_minute_ago = now - 60
            one_hour_ago = now - 3600
            today_start = now - (now % 86400)
            
            events_last_minute = sum(1 for ts in stats['received_timestamps'] if ts >= one_minute_ago)
            events_last_hour = sum(1 for ts in stats['received_timestamps'] if ts >= one_hour_ago)
            events_today = sum(1 for ts in stats['received_timestamps'] if ts >= today_start)
            
            # 计算成功率
            total = stats['total_processed'] + stats['total_failed']
            success_rate = (stats['total_processed'] / total * 100) if total > 0 else 100.0
            
            # 计算平均延迟
            avg_latency = 0.0
            if stats['processing_latencies']:
                avg_latency = sum(stats['processing_latencies']) / len(stats['processing_latencies'])
            
            return {
                'total_received': stats['total_received'],
                'total_processed': stats['total_processed'],
                'total_failed': stats['total_failed'],
                'pending_count': pending_count,
                'success_rate': success_rate,
                'avg_processing_latency': avg_latency,
                'last_activity_time': stats['last_activity_time'],
                'first_received_time': stats['first_received_time'],
                'batch_size': self.batch_size,
                'flush_interval': self.flush_interval,
                'current_buffer_size': pending_count,
                'events_last_minute': events_last_minute,
                'events_last_hour': events_last_hour,
                'events_today': events_today,
            }
    
    def reset_stats(self):
        """重置统计数据"""
        with self._lock:
            self.stats = {
                'total_received': 0,
                'total_processed': 0,
                'total_failed': 0,
                'processing_latencies': deque(maxlen=1000),
                'received_timestamps': deque(maxlen=3600),
                'processed_timestamps': deque(maxlen=3600),
                'first_received_time': None,
                'last_activity_time': None,
            }
    
    def _condition_thread_func(self):
        """条件变量线程函数 - 惰性刷新：连续 quiet_window 无新事件时触发批量处理"""
        while self._running:
            with self._lock:
                total_count = sum(len(events) for events in self._buffer.values())

                if total_count == 0:
                    # 缓冲区为空，等待 flush_interval
                    self._condition.wait(timeout=self.flush_interval)
                else:
                    # 缓冲区有数据，等待安静窗口
                    wait_time = self.quiet_window
                    self._condition.wait(timeout=wait_time)

                # 检查是否需要刷新：缓冲区不为空且连续 quiet_window 无新事件
                if self._buffer:
                    elapsed_since_last_event = time.time() - self._last_event_time
                    if elapsed_since_last_event >= self.quiet_window:
                        self._last_flush_time = time.time()
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
        self._event_descriptions: Dict[str, str] = {}
        self._lock = threading.RLock()
    
    def register(self, 
                 event_type: str,
                 handler: Callable[[List[Any]], None],
                 group_key: Callable[[Any], str] = None,
                 dedup_key: Callable[[Any], str] = None,
                 batch_size: int = 10000,
                 quiet_window: float = 15.0,
                 flush_interval: float = 5.0,
                 description: str = None) -> 'MultiEventAggregator':
        """
        注册一个事件类型的聚合器
        
        Args:
            event_type: 事件类型标识
            handler: 批量处理函数
            group_key: 分组函数
            dedup_key: 去重函数
            batch_size: 批量大小
            quiet_window: 安静窗口（秒），连续无新事件达到此时间后触发批量处理
            flush_interval: 刷新间隔（秒），仅在缓冲区为空时生效
            description: 事件类型描述
        
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
                quiet_window=quiet_window,
                flush_interval=flush_interval,
                name=event_type
            )
            self._aggregators[event_type] = aggregator
            self._event_descriptions[event_type] = description or event_type
            aggregator.start()
            logger.success(f"事件聚合器注册", event_type, "")
            return self
    
    def add(self, event_type: str, event: Any):
        """添加事件到指定类型的聚合器"""
        description = self._event_descriptions.get(event_type, event_type)
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
                    if event_type in self._event_descriptions:
                        del self._event_descriptions[event_type]
            else:
                for aggregator in self._aggregators.values():
                    aggregator.stop()
                self._aggregators.clear()
                self._event_descriptions.clear()
    
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
    
    def get_all_stats(self):
        """获取所有事件类型的统计数据
        
        Returns:
            dict: 包含各事件类型统计数据的字典
        """
        with self._lock:
            stats = {}
            for event_type, aggregator in self._aggregators.items():
                stats[event_type] = aggregator.get_stats()
            return stats
    
    def get_event_types(self):
        """获取已注册的事件类型列表
        
        Returns:
            list: 事件类型列表
        """
        with self._lock:
            return list(self._aggregators.keys())
    
    def get_event_description(self, event_type: str) -> str:
        """获取事件类型的描述
        
        Args:
            event_type: 事件类型标识
        
        Returns:
            str: 事件类型描述，如果不存在则返回事件类型本身
        """
        with self._lock:
            return self._event_descriptions.get(event_type, event_type)
    
    def get_all_event_descriptions(self) -> Dict[str, str]:
        """获取所有事件类型的描述
        
        Returns:
            dict: 事件类型到描述的映射
        """
        with self._lock:
            return dict(self._event_descriptions)
    
    def reset_stats(self, event_type: str = None):
        """重置统计数据
        
        Args:
            event_type: 指定事件类型，None表示重置所有
        """
        with self._lock:
            if event_type:
                if event_type in self._aggregators:
                    self._aggregators[event_type].reset_stats()
            else:
                for aggregator in self._aggregators.values():
                    aggregator.reset_stats()


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
