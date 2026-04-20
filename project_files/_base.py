"""
导入包和常量，供各项目文件使用
"""

# import threading
import os, asyncio, logging, json, requests, pandas as pd, threading
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise

from globalobjects.globalconst import OrderStatusEnum


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from core.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, SCHEDULER_MINUTE
from globalobjects import logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_supsert, db_update_by_index
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests, get_session
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components._base import ApsHelpers, get_production_cache
from apps.data_opt.components.simple_hap import HapConnection




CLIENT_LOGGER = log_config.get_logger(__name__)

CLIENT_SESSION = get_session()

def get_scheduler_minute(offset: int=0):

    minutes = []
    for m in SCHEDULER_MINUTE.split(','):
        minute = int(m) + offset
        minutes.append(str(minute % 60))
    return ','.join(minutes)



import time
import asyncio
from functools import wraps
from collections import namedtuple
from threading import Lock

# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from core.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, SCHEDULER_MINUTE, MAX_EVENTS_PER_SECOND

# 定义任务执行结果的具名元组
TaskResult = namedtuple('TaskResult', ['status', 'error'])


class AsyncTokenBucket:
    """轻量异步令牌桶限流器"""
    def __init__(self, rate: int, per: float = 1.0):
        self.rate = rate
        self.interval = 1.0 / rate if rate > 0 else 0
        self.tokens = float(rate)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(0)
        self._task = None

    async def _refill(self):
        while True:
            await asyncio.sleep(self.interval)
            async with self._lock:
                self.tokens = min(self.rate, self.tokens + 1)
                if self._semaphore._value == 0 and self.tokens >= 1:
                    self._semaphore.release()

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._refill())

    async def acquire(self, tokens: int = 1):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed / self.interval if self.interval > 0 else self.rate)
            self.last_update = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return
        for _ in range(tokens):
            await self._semaphore.acquire()

    async def acquire_immediately(self, tokens: int = 1) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed / self.interval if self.interval > 0 else self.rate)
            self.last_update = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
        return False


class SyncTokenBucket:
    """轻量同步令牌桶限流器"""
    def __init__(self, rate: int, per: float = 1.0):
        self.rate = rate
        self.interval = 1.0 / rate if rate > 0 else 0
        self.tokens = float(rate)
        self.last_update = time.time()
        self._lock = Lock()

    def acquire(self, tokens: int = 1):
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed / self.interval if self.interval > 0 else self.rate)
            self.last_update = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            wait_time = (tokens - self.tokens) * self.interval
            time.sleep(wait_time)
            self.tokens -= tokens
            return True

    def acquire_immediately(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed / self.interval if self.interval > 0 else self.rate)
            self.last_update = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


# 全局共享令牌桶实例（所有装饰的函数共享同一个限流器）
_global_async_bucket = None
_global_sync_bucket = None


def async_rate_limit(rate: int = None):
    """
    异步函数限流装饰器 - 所有装饰的函数共享同一个令牌桶
    
    用法:
        @async_rate_limit(MAX_EVENTS_PER_SECOND)
        async def handle_pl_status_a2e(supplyno_or_data):
            ...
    
    限流维度: 基于被装饰函数的 event_count 参数指定的事件数量进行限流
    """
    global _global_async_bucket
    if rate is None:
        rate = MAX_EVENTS_PER_SECOND
    
    if _global_async_bucket is None:
        _global_async_bucket = AsyncTokenBucket(rate)
        _global_async_bucket.start()
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            event_count = kwargs.pop('event_count', 1)
            await _global_async_bucket.acquire(event_count)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def sync_rate_limit(rate: int = None):
    """
    同步函数限流装饰器 - 所有装饰的函数共享同一个令牌桶
    
    用法:
        @sync_rate_limit(MAX_EVENTS_PER_SECOND)
        def handle_pl_status_a2e(supplyno_or_data):
            ...
    
    限流维度: 基于被装饰函数的 event_count 参数指定的事件数量进行限流
    """
    global _global_sync_bucket
    if rate is None:
        rate = MAX_EVENTS_PER_SECOND
    
    if _global_sync_bucket is None:
        _global_sync_bucket = SyncTokenBucket(rate)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            event_count = kwargs.pop('event_count', 1)
            _global_sync_bucket.acquire(event_count)
            return func(*args, **kwargs)
        return wrapper
    return decorator


