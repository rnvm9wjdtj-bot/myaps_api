"""
事件处理辅助模块 - 提供回调跟踪、DeadLetter队列和去重机制

功能特性：
1. 回调跟踪与重试机制 - 跟踪异步回调结果，失败时自动重试
2. 异步DeadLetter队列 - 事件处理失败时异步写入DeadLetter文件
3. 事件去重 - 基于事件键的去重机制

使用示例：
    from apps.common.utils.event_helpers import get_callback_tracker, get_dead_letter_queue, get_event_deduplicator

    # 回调跟踪
    tracker = get_callback_tracker()
    tracker.track(future, event_id)

    # DeadLetter队列
    dlq = get_dead_letter_queue()
    dlq.add_failed_event(event, error_msg)

    # 事件去重
    dedup = get_event_deduplicator(ttl=300)
    if dedup.is_duplicate(event_key):
        return  # 跳过重复事件
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from collections import deque
from concurrent.futures import Future
from threading import Lock

from globalobjects import logger as log_config

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'storage'
DEAD_LETTER_DIR = STORAGE_DIR / 'dead_letter'
DEAD_LETTER_FILE = DEAD_LETTER_DIR / 'failed_events.jsonl'


class CallbackTracker:
    """回调结果跟踪器 - 跟踪异步回调结果，失败时自动重试"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        初始化回调跟踪器

        Args:
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self._pending: Dict[str, Dict] = {}
        self._lock = Lock()
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._cleanup_interval = 3600
        self._last_cleanup_time = time.time()

    def track(self, future: Future, event_id: str, callback: Optional[Callable] = None, *callback_args):
        """
        跟踪一个回调

        Args:
            future: 要跟踪的 Future 对象
            event_id: 事件唯一标识
            callback: 可选的错误回调函数
            *callback_args: 回调函数参数
        """
        with self._lock:
            self._pending[event_id] = {
                'future': future,
                'submit_time': time.time(),
                'retry_count': 0,
                'callback': callback,
                'callback_args': callback_args
            }

        future.add_done_callback(lambda f: self._handle_result(f, event_id))

        self._cleanup_if_needed()

    def _handle_result(self, future: Future, event_id: str):
        """处理回调结果"""
        with self._lock:
            if event_id not in self._pending:
                return

            info = self._pending[event_id]

            if future.done():
                try:
                    future.result()
                    del self._pending[event_id]
                except Exception as e:
                    if info['retry_count'] < self._max_retries:
                        logger.warning(f"回调失败，准备重试 {event_id}: {e}")
                        info['retry_count'] += 1
                        self._retry(info, event_id)
                    else:
                        logger.error(f"回调失败，已达到最大重试次数 {event_id}: {e}")
                        if info['callback']:
                            try:
                                info['callback'](*info['callback_args'], error=e)
                            except Exception as callback_error:
                                logger.error(f"回调错误处理函数执行失败: {callback_error}")
                        del self._pending[event_id]

    def _retry(self, info: Dict, event_id: str):
        """重试失败的回调"""
        # 只有当提供了回调函数时才进行重试
        if not info['callback']:
            logger.warning(f"无回调函数，跳过重试 {event_id}")
            return

        def retry_task():
            # 计算延迟，初始延迟 1s，后续指数增长
            delay = self._retry_delay * (2 ** (info['retry_count'] - 1))
            time.sleep(delay)
            try:
                future = info['callback'](*info['callback_args'])
                if future:
                    future.add_done_callback(lambda f: self._handle_result(f, event_id))
            except Exception as e:
                logger.error(f"重试失败 {event_id}: {e}")

        thread = threading.Thread(target=retry_task, daemon=True)
        thread.start()

    def _cleanup_if_needed(self):
        """清理过期的跟踪记录"""
        current_time = time.time()
        if current_time - self._last_cleanup_time < self._cleanup_interval:
            return

        with self._lock:
            expired_keys = []
            for event_id, info in self._pending.items():
                if current_time - info['submit_time'] > 3600:
                    expired_keys.append(event_id)

            for key in expired_keys:
                del self._pending[key]

            if expired_keys:
                logger.debug(f"清理了 {len(expired_keys)} 个过期的回调跟踪记录")

        self._last_cleanup_time = current_time

    def get_pending_count(self) -> int:
        """获取待处理回调数量"""
        with self._lock:
            return len(self._pending)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            total_retries = sum(info['retry_count'] for info in self._pending.values())
            return {
                'pending_count': len(self._pending),
                'max_retries': self._max_retries,
                'total_pending_retries': total_retries
            }


class DeadLetterQueue:
    """异步DeadLetter队列 - 事件处理失败时异步写入DeadLetter文件"""

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

        self._queue: deque = deque(maxlen=10000)
        self._write_lock = Lock()
        self._write_thread: Optional[threading.Thread] = None
        self._running = False
        self._ensure_dir()
        self._initialized = True

    def _ensure_dir(self):
        """确保目录存在"""
        try:
            DEAD_LETTER_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"创建DeadLetter目录失败: {e}")

    def start(self):
        """启动DeadLetter队列处理线程"""
        if self._running:
            return

        self._running = True
        self._write_thread = threading.Thread(
            target=self._write_loop,
            daemon=True,
            name='dead-letter-writer'
        )
        self._write_thread.start()
        logger.success("DeadLetter队列", "", "已启动")

    def stop(self):
        """停止DeadLetter队列并写入所有待处理事件"""
        self._running = False
        if self._write_thread:
            self._write_thread.join(timeout=5)
        self._flush_all()
        logger.info("DeadLetter队列已停止")

    def add_failed_event(self, event: Any, error_msg: str, event_type: str = 'unknown'):
        """
        添加失败事件到DeadLetter队列

        Args:
            event: 失败的事件数据
            error_msg: 错误信息
            event_type: 事件类型
        """
        entry = {
            'event': event,
            'error': error_msg,
            'event_type': event_type,
            'timestamp': time.time(),
            'failed_at': time.strftime('%Y-%m-%d %H:%M:%S')
        }

        with self._write_lock:
            self._queue.append(entry)

        if not self._running:
            self.start()

    def _write_loop(self):
        """DeadLetter队列写入循环"""
        while self._running:
            try:
                batch = []
                with self._write_lock:
                    while self._queue and len(batch) < 100:
                        batch.append(self._queue.popleft())

                if batch:
                    self._write_batch(batch)

                time.sleep(1)
            except Exception as e:
                logger.error(f"DeadLetter队列写入循环出错: {e}")

    def _write_batch(self, batch):
        """批量写入DeadLetter事件"""
        try:
            with open(DEAD_LETTER_FILE, 'a', encoding='utf-8') as f:
                for entry in batch:
                    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
            logger.debug(f"DeadLetter队列写入 {len(batch)} 个事件")
        except Exception as e:
            logger.error(f"DeadLetter队列写入失败: {e}")

    def _flush_all(self):
        """写入所有待处理事件"""
        batch = []
        with self._write_lock:
            while self._queue:
                batch.append(self._queue.popleft())

        if batch:
            self._write_batch(batch)

    def get_pending_count(self) -> int:
        """获取待写入事件数量"""
        with self._write_lock:
            return len(self._queue)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        file_size = 0
        event_count = 0

        if DEAD_LETTER_FILE.exists():
            file_size = DEAD_LETTER_FILE.stat().st_size
            try:
                with open(DEAD_LETTER_FILE, 'r', encoding='utf-8') as f:
                    event_count = sum(1 for _ in f)
            except Exception:
                pass

        return {
            'pending_count': self.get_pending_count(),
            'total_file_size': file_size,
            'total_event_count': event_count,
            'running': self._running
        }

    def get_events(self, limit: int = 50) -> list:
        """
        获取DeadLetter事件列表

        Args:
            limit: 返回事件数量限制

        Returns:
            DeadLetter事件列表
        """
        events = []
        if DEAD_LETTER_FILE.exists():
            try:
                with open(DEAD_LETTER_FILE, 'r', encoding='utf-8') as f:
                    for line in reversed(list(f)):
                        if len(events) >= limit:
                            break
                        try:
                            event = json.loads(line.strip())
                            events.append(event)
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"读取DeadLetter文件失败: {e}")
        return events

    def clear(self):
        """
        清空DeadLetter队列
        """
        # 清空内存队列
        with self._write_lock:
            self._queue.clear()
        
        # 清空文件
        if DEAD_LETTER_FILE.exists():
            try:
                with open(DEAD_LETTER_FILE, 'w', encoding='utf-8') as f:
                    f.write('')
                logger.info("DeadLetter队列已清空")
            except Exception as e:
                logger.error(f"清空DeadLetter文件失败: {e}")


class EventDeduplicator:
    """事件去重器 - 基于事件键的去重机制"""

    def __init__(self, ttl: int = 300, max_entries: int = 100000):
        """
        初始化去重器

        Args:
            ttl: 键的生存时间（秒），默认 5 分钟
            max_entries: 最大缓存条目数
        """
        self._seen: Dict[str, float] = {}
        self._lock = Lock()
        self._ttl = ttl
        self._max_entries = max_entries
        self._cleanup_count = 0

    def is_duplicate(self, event_key: str) -> bool:
        """
        检查事件键是否重复

        Args:
            event_key: 事件唯一键

        Returns:
            True 如果是重复事件，False 如果是新事件
        """
        current_time = time.time()

        with self._lock:
            if event_key in self._seen:
                last_time = self._seen[event_key]
                if current_time - last_time < self._ttl:
                    return True
                else:
                    del self._seen[event_key]

            self._seen[event_key] = current_time
            self._cleanup_if_needed()
            return False

    def add_event(self, event_key: str):
        """手动添加事件键"""
        with self._lock:
            self._seen[event_key] = time.time()
            self._cleanup_if_needed()

    def _cleanup_if_needed(self):
        """清理过期和超限的条目"""
        self._cleanup_count += 1

        if self._cleanup_count < 1000 and len(self._seen) <= self._max_entries:
            return

        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self._seen.items()
            if current_time - timestamp >= self._ttl
        ]

        for key in expired_keys:
            del self._seen[key]

        if len(self._seen) > self._max_entries:
            sorted_keys = sorted(self._seen.items(), key=lambda x: x[1])
            keys_to_remove = len(self._seen) - self._max_entries
            for key, _ in sorted_keys[:keys_to_remove]:
                del self._seen[key]

        self._cleanup_count = 0

    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._seen.clear()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._lock:
            current_time = time.time()
            active_count = sum(
                1 for timestamp in self._seen.values()
                if current_time - timestamp < self._ttl
            )
            return {
                'total_entries': len(self._seen),
                'active_entries': active_count,
                'ttl': self._ttl,
                'max_entries': self._max_entries
            }


_callback_tracker: Optional[CallbackTracker] = None
_dead_letter_queue: Optional[DeadLetterQueue] = None
_event_deduplicator: Optional[EventDeduplicator] = None
_deduplicator_lock = Lock()


def get_callback_tracker() -> CallbackTracker:
    """获取回调跟踪器单例"""
    global _callback_tracker
    if _callback_tracker is None:
        _callback_tracker = CallbackTracker(max_retries=3, retry_delay=1.0)
    return _callback_tracker


def get_dead_letter_queue() -> DeadLetterQueue:
    """获取DeadLetter队列单例"""
    global _dead_letter_queue
    if _dead_letter_queue is None:
        _dead_letter_queue = DeadLetterQueue()
        _dead_letter_queue.start()
    return _dead_letter_queue


def get_event_deduplicator() -> EventDeduplicator:
    """获取事件去重器单例"""
    global _event_deduplicator
    if _event_deduplicator is None:
        with _deduplicator_lock:
            if _event_deduplicator is None:
                _event_deduplicator = EventDeduplicator(ttl=300, max_entries=100000)
    return _event_deduplicator


def shutdown_event_helpers():
    """关闭所有事件辅助模块"""
    global _dead_letter_queue
    if _dead_letter_queue:
        _dead_letter_queue.stop()
