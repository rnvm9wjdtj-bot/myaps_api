"""
导入包和常量，供各项目文件使用
"""

# import threading
import os, asyncio, logging, json, requests, pandas as pd, threading, inspect
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional, Union
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise
from core.settings import MAX_EVENTS_PER_SECOND, SCHEDULER_MINUTE
from globalobjects.globalconst import OrderStatusEnum


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from core.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, PROJECT_JSON
from globalobjects import logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv, AlertType, QqEmailReminder, Reminder
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_supsert, db_update_by_index
from apps.io_api.models import TSupply
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests, get_session
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components._base import ApsPayloadSponsor, EventResultPoster, CacheItem
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

# 定义任务执行结果的具名元组
TaskResult = namedtuple('TaskResult', ['status', 'error'])

#################################################################################
# 令牌桶限流器
#################################################################################
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
db_event_async_bucket = None
db_event_sync_bucket = None


def async_rate_limit(rate: int = None):
    """
    异步函数限流装饰器 - 所有装饰的函数共享同一个令牌桶
    
    用法:
        @async_rate_limit(MAX_EVENTS_PER_SECOND)
        async def handle_pl_status_a2e(supplyno_or_data):
            ...
    
    限流维度: 基于被装饰函数的 event_count 参数指定的事件数量进行限流
    """
    global db_event_async_bucket
    if rate is None:
        rate = MAX_EVENTS_PER_SECOND
    
    if db_event_async_bucket is None:
        db_event_async_bucket = AsyncTokenBucket(rate)
        db_event_async_bucket.start()
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            event_count = kwargs.pop('event_count', 1)
            await db_event_async_bucket.acquire(event_count)
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
    global db_event_sync_bucket
    if rate is None:
        rate = MAX_EVENTS_PER_SECOND
    
    if db_event_sync_bucket is None:
        db_event_sync_bucket = SyncTokenBucket(rate)
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            event_count = kwargs.pop('event_count', 1)
            db_event_sync_bucket.acquire(event_count)
            return func(*args, **kwargs)
        return wrapper
    return decorator


#################################################################################
# 公共装饰器
#################################################################################

def start_event_batch_reminder(reminder: Reminder = None, error_handler: Union[callable, str] = None, final_handler: callable = None):
    """
    异步函数执行提示装饰器

    用法:
        @event_batch_start_reminder()
        async def batch_handle_pl_status_a2e(event_data: List[Dict]):
            ...

        @event_batch_start_reminder(reminder=qq_email_reminder)
        async def batch_handle_pl_status_a2e(event_data: List[Dict]):
            ...

    参数:
        reminder: Reminder 实例，函数开始运行时将调用其 remind 方法发送通知
        error_handler: 可选的错误处理函数或方法名
                      - 如果是字符串，如 "some_error_method"，将调用对应方法
                      - 如果是可调用对象，签名应为 func(exception, *args, **kwargs)
                      用于处理被装饰函数中未被捕获的异常
        final_handler: 可选的最终回调函数，在函数执行完成后调用
                      签名应为 func(result, *args, **kwargs) 或 async func(result, *args, **kwargs)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            event_data = None
            description = kwargs.get('description', None)
            if description is None:
                try:
                    sig = inspect.signature(func)
                    # 使用 bind_partial 绑定参数，避免缺少参数导致绑定失败
                    bound_args = sig.bind_partial(*args, **kwargs)
                    bound_args.apply_defaults()
                    description = bound_args.arguments.get('description')
                except:
                    pass
            if description is None:
                description = func.__name__

            if args and len(args) > 0:
                event_data = args[0]
            elif 'event_data' in kwargs:
                event_data = kwargs['event_data']

            if reminder is not None:
                if event_data is not None:
                    if isinstance(event_data, list):
                        count = len(event_data)
                        require_time_sec = 30 + count * 2 / MAX_EVENTS_PER_SECOND    # 预计耗时，单位秒，这个公式没什么道理
                        require_time_min = f"{int(require_time_sec / 60)} 分 {int(require_time_sec % 60)} 秒"
                        content = f"开始【{description}】，将处理【{count}】条数据，预计耗时【{require_time_min}】"
                    else:
                        content = f"开始【{description}】，处理数据：{str(event_data)[:1024]}"
                else:
                    content = f"开始【{description}】"

                content += f"\n 🚩 在收到完成提示前请耐心等待，⚠️ 请勿进行其他操作"
                await reminder.remind(content)

            pending_exception = None
            result = None
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                CLIENT_LOGGER.error(f"{description} 执行出错: {str(e)}")
                if error_handler is not None:
                    CLIENT_LOGGER.info(f"尝试使用 {error_handler} 进行错误捕获处理。。。")
                    if isinstance(error_handler, str):
                        if hasattr(func, '__self__'):
                            error_method = getattr(func.__self__, error_handler, None)
                        else:
                            error_method = None
                        if not error_method:
                            CLIENT_LOGGER.warning_msg(f"无法解析 {error_handler} 为有效的方法")
                            pending_exception = e
                        elif not callable(error_method):
                            CLIENT_LOGGER.warning_msg(f"{error_handler} 为不可调用对象")
                            pending_exception = e
                        else:
                            try:
                                if inspect.iscoroutinefunction(error_method):
                                    await error_method(msg=str(e), msg_from="API")
                                else:
                                    error_method(msg=str(e), msg_from="API")
                                CLIENT_LOGGER.info(f"已使用 {error_handler} 完成捕获处理")
                            except Exception as inner_e:
                                CLIENT_LOGGER.fail(f"使用 {error_handler} 处理异常", str(inner_e))
                                pending_exception = e
                    else:
                        if callable(error_handler):
                            try:
                                if inspect.iscoroutinefunction(error_handler):
                                    await error_handler(e, *args, **kwargs)
                                else:
                                    error_handler(e, *args, **kwargs)
                                CLIENT_LOGGER.info(f"已使用 {error_handler.__name__} 完成捕获处理")
                            except Exception as inner_e:
                                CLIENT_LOGGER.fail(f"使用 {error_handler.__name__} 处理异常", str(inner_e))
                                pending_exception = e
                        else:
                            CLIENT_LOGGER.warning_msg(f"{error_handler.__name__} 为不可调用对象")
                            pending_exception = e
                else:
                    pending_exception = e
            finally:
                end_time = time.time()
                execution_time = end_time - start_time
                log_message = f"{description} 执行完成，耗时: {execution_time:.2f} 秒"
                CLIENT_LOGGER.debug(log_message)
                
                # 调用最终回调函数
                if final_handler is not None:
                    if callable(final_handler):
                        try:
                            if inspect.iscoroutinefunction(final_handler):
                                await final_handler(result, *args, **kwargs)
                            else:
                                final_handler(result, *args, **kwargs)
                            CLIENT_LOGGER.info(f"已使用 {final_handler.__name__} 完成最终回调")
                        except Exception as inner_e:
                            CLIENT_LOGGER.fail(f"使用 {final_handler.__name__} 执行最终回调", str(inner_e))
                    else:
                        CLIENT_LOGGER.warning_msg(f"{final_handler} 为不可调用对象")

            if pending_exception is not None:
                raise pending_exception

        return wrapper
    return decorator


def finish_event_batch_reminder(description: str = None, reminder: Reminder = None):
    """
    带结果收集的装饰器，用于结果汇总

    用法:
        @event_batch_finish_reminder(reminder=qq_email_reminder)
        async def batch_handle_pl_status_a2e(event_data: List[Dict], description="PL 单据下达", _erp=None):
            @async_rate_limit()
            async def handle_pl_status_a2e(item):
                try:
                    # ... 业务逻辑
                    pass
                except Exception as e:
                    # 直接调用 _erp 方法记录错误
                    await _erp.pl_release_failed_async(msg=str(e), msg_from="API")
                    return

            tasks = [handle_pl_status_a2e(item) for item in event_data]
            await asyncio.gather(*tasks, return_exceptions=True)

    参数:
        description: 任务描述，用于日志和通知。如果为 None，则从被装饰函数的 description 参数提取
        reminder: 可选的 Reminder 实例，执行完成时将发送通知

    注意:
        被装饰的函数需要接受 _erp 参数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 先获取 description
            actual_description = description
            if not actual_description:
                actual_description = kwargs.get('description', None)
                if actual_description is None:
                    try:
                        sig = inspect.signature(func)
                        # 使用 bind_partial 绑定原始参数，避免缺少 _erp 参数导致绑定失败
                        bound_args = sig.bind_partial(*args, **kwargs)
                        bound_args.apply_defaults()
                        actual_description = bound_args.arguments.get('description')
                    except:
                        pass
                if actual_description is None:
                    actual_description = func.__name__
            
            # 然后创建并注入 _erp
            _erp = EventResultPoster()
            kwargs['_erp'] = _erp
            
            try:
                result = await func(*args, **kwargs)
            finally:
                # 使用之前获取的 actual_description
                summary = _erp.get_summary()     
                CLIENT_LOGGER.info(f"{actual_description} 执行完成，汇总结果: {json.dumps(summary, ensure_ascii=False)}")
                notification = _erp.format_notification(actual_description)
                CLIENT_LOGGER.info(f"通知内容: {notification}")
                
                if reminder is not None:
                    await reminder.remind(notification)
            
            return summary
        return wrapper
    return decorator

