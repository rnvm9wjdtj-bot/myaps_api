import json
# 兼容旧版本 NumPy
import numpy as np
istitle = np.char.istitle
import pandas as pd
import time
import threading
import asyncio
import inspect
from pathlib import Path
from functools import wraps
import subprocess
import sys
import re

from enum import Enum
from typing import List, Dict, Optional, Literal, Callable, Union, Any, Type
from collections import defaultdict
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel
import uuid
from dataclasses import dataclass, field


from core.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET, MAX_EVENTS_PER_SECOND


# 控制 T+ API 并发请求的信号量（根据 MAX_EVENTS_PER_SECOND 动态调整）
def _get_concurrency_limit() -> int:
    """获取并发限制数，建议不超过每秒事件数的一半，最小为1"""
    return max(1, MAX_EVENTS_PER_SECOND // 2)


# 全局信号量，限制同时进行的 API 请求数
_db_event_semaphore = None

def get_db_event_semaphore():
    """获取全局信号量实例（懒加载）"""
    global _db_event_semaphore
    if _db_event_semaphore is None:
        _db_event_semaphore = asyncio.Semaphore(_get_concurrency_limit())
    return _db_event_semaphore

    
from apps.data_opt.utils.common import get_session, get_async_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.utils.db_operation import db_exec_sql, DbResult, MultiDbResult
from apps.io_api.schemas import (
    model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm
)
from apps.io_api.models import TSupply, TDemand
from apps.io_api.utils.db_operation import db_query, db_update_by_index, db_query, db_delete, db_bupsert, call_dbprocdure
from apps.io_api.utils.common import standard_response
from globalobjects import globalconst, logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv, StaticString as ce
from globalobjects.json_manager import JSONManager



logger = log_config.get_logger(__name__)



class SyncTokenBucket:
    """
    同步令牌桶限流器

    使用条件变量实现高效的令牌等待，避免忙轮询。
    """

    def __init__(self, qps: float = 10.0, burst: int = 20):
        self.qps = qps
        self.burst = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._cond = threading.Condition()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.qps)
        self._last_update = now

    def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        deadline = time.monotonic() + timeout if timeout else float('inf')
        
        with self._cond:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._cond.notify()
                    return True
                
                if time.monotonic() >= deadline:
                    return False
                
                wait_time = min((tokens - self._tokens) / self.qps, 0.1)
                self._cond.wait(timeout=wait_time)

    def try_acquire(self, tokens: int = 1) -> bool:
        with self._cond:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._cond.notify()
                return True
            return False

    def release(self, tokens: int = 1):
        with self._cond:
            self._tokens = min(self.burst, self._tokens + tokens)
            self._cond.notify()


class AsyncTokenBucket:
    """
    异步令牌桶限流器

    使用 asyncio.Condition 实现高效的令牌等待。
    """

    def __init__(self, qps: float = 10.0, burst: int = 20):
        self.qps = qps
        self.burst = burst
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._cond = asyncio.Condition()

    async def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self.qps)
        self._last_update = now

    async def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        deadline = time.monotonic() + timeout if timeout else float('inf')
        
        async with self._cond:
            while True:
                await self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._cond.notify()
                    return True
                
                if time.monotonic() >= deadline:
                    return False
                
                wait_time = min((tokens - self._tokens) / self.qps, 0.1)
                await asyncio.sleep(wait_time)

    async def try_acquire(self, tokens: int = 1) -> bool:
        async with self._cond:
            await self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._cond.notify()
                return True
            return False

    async def release(self, tokens: int = 1):
        async with self._cond:
            self._tokens = min(self.burst, self._tokens + tokens)
            self._cond.notify()


class AdaptiveTokenBucket:
    """
    自适应令牌桶限流器（同步）

    根据请求延迟和错误率自动调整 QPS：
    - 延迟升高或错误增多 → 降低 QPS
    - 情况恢复 → 逐步恢复 QPS
    """

    def __init__(
        self,
        initial_qps: float = 10.0,
        burst: int = 20,
        min_qps: float = 1.0,
        max_qps: float = 100.0,
        slow_threshold_ms: float = 1000.0,
        error_penalty: float = 0.8,
        recovery_factor: float = 1.1,
        stats_window: int = 100
    ):
        self.initial_qps = initial_qps
        self.burst = burst
        self.min_qps = min_qps
        self.max_qps = max_qps
        
        self.slow_threshold_ms = slow_threshold_ms
        self.error_penalty = error_penalty
        self.recovery_factor = recovery_factor
        self.stats_window = stats_window
        
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._cond = threading.Condition()
        
        self._current_qps = initial_qps
        self._slow_count = 0
        self._error_count = 0
        self._success_count = 0
        self._recent_latencies = []
        self._recent_errors = []
        self._lock = threading.Lock()

    def _update_stats(self, latency_ms: float, is_error: bool):
        """更新统计信息"""
        with self._lock:
            self._recent_latencies.append(latency_ms)
            self._recent_errors.append(1 if is_error else 0)
            
            if len(self._recent_latencies) > self.stats_window:
                self._recent_latencies.pop(0)
                self._recent_errors.pop(0)
            
            if is_error:
                self._error_count += 1
            else:
                self._success_count += 1

    def _adjust_qps(self):
        """根据统计信息调整 QPS"""
        if len(self._recent_latencies) < 10:
            return
        
        avg_latency = sum(self._recent_latencies) / len(self._recent_latencies)
        error_rate = sum(self._recent_errors) / len(self._recent_errors)
        
        if avg_latency > self.slow_threshold_ms or error_rate > 0.2:
            self._current_qps = max(self.min_qps, self._current_qps * self.error_penalty)
            logger.debug(f"Adaptive QPS: 降低到 {self._current_qps:.2f} (延迟:{avg_latency:.0f}ms 错误率:{error_rate:.1%})")
        elif self._current_qps < self.initial_qps:
            self._current_qps = min(self.max_qps, self._current_qps * self.recovery_factor)
            logger.debug(f"Adaptive QPS: 恢复到 {self._current_qps:.2f}")

    def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        deadline = time.monotonic() + timeout if timeout else float('inf')
        
        with self._cond:
            while True:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._cond.notify()
                    return True
                
                if time.monotonic() >= deadline:
                    return False
                
                wait_time = min((tokens - self._tokens) / self._current_qps, 0.1)
                self._cond.wait(timeout=wait_time)

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self._current_qps)
        self._last_update = now

    def try_acquire(self, tokens: int = 1) -> bool:
        with self._cond:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._cond.notify()
                return True
            return False

    def release(self, tokens: int = 1):
        with self._cond:
            self._tokens = min(self.burst, self._tokens + tokens)
            self._cond.notify()

    @property
    def current_qps(self) -> float:
        return self._current_qps

    def record_request(self, latency_ms: float, is_error: bool = False):
        """
        记录请求结果，用于自适应调整

        Args:
            latency_ms: 请求延迟（毫秒）
            is_error: 是否出错
        """
        self._update_stats(latency_ms, is_error)
        self._adjust_qps()


class AdaptiveAsyncTokenBucket:
    """
    自适应令牌桶限流器（异步）

    根据请求延迟和错误率自动调整 QPS：
    - 延迟升高或错误增多 → 降低 QPS
    - 情况恢复 → 逐步恢复 QPS
    """

    def __init__(
        self,
        initial_qps: float = 10.0,
        burst: int = 20,
        min_qps: float = 1.0,
        max_qps: float = 100.0,
        slow_threshold_ms: float = 1000.0,
        error_penalty: float = 0.8,
        recovery_factor: float = 1.1,
        stats_window: int = 100
    ):
        self.initial_qps = initial_qps
        self.burst = burst
        self.min_qps = min_qps
        self.max_qps = max_qps
        
        self.slow_threshold_ms = slow_threshold_ms
        self.error_penalty = error_penalty
        self.recovery_factor = recovery_factor
        self.stats_window = stats_window
        
        self._tokens = float(burst)
        self._last_update = time.monotonic()
        self._cond = asyncio.Condition()
        
        self._current_qps = initial_qps
        self._recent_latencies = []
        self._recent_errors = []
        self._lock = asyncio.Lock()

    async def _update_stats(self, latency_ms: float, is_error: bool):
        async with self._lock:
            self._recent_latencies.append(latency_ms)
            self._recent_errors.append(1 if is_error else 0)
            
            if len(self._recent_latencies) > self.stats_window:
                self._recent_latencies.pop(0)
                self._recent_errors.pop(0)

    async def _adjust_qps(self):
        if len(self._recent_latencies) < 10:
            return
        
        avg_latency = sum(self._recent_latencies) / len(self._recent_latencies)
        error_rate = sum(self._recent_errors) / len(self._recent_errors)
        
        async with self._lock:
            if avg_latency > self.slow_threshold_ms or error_rate > 0.2:
                self._current_qps = max(self.min_qps, self._current_qps * self.error_penalty)
                logger.debug(f"Adaptive QPS: 降低到 {self._current_qps:.2f} (延迟:{avg_latency:.0f}ms 错误率:{error_rate:.1%})")
            elif self._current_qps < self.initial_qps:
                self._current_qps = min(self.max_qps, self._current_qps * self.recovery_factor)
                logger.debug(f"Adaptive QPS: 恢复到 {self._current_qps:.2f}")

    async def acquire(self, tokens: int = 1, timeout: float = None) -> bool:
        deadline = time.monotonic() + timeout if timeout else float('inf')
        
        async with self._cond:
            while True:
                await self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self._cond.notify()
                    return True
                
                if time.monotonic() >= deadline:
                    return False
                
                wait_time = min((tokens - self._tokens) / self._current_qps, 0.1)
                await asyncio.sleep(wait_time)

    async def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.burst, self._tokens + elapsed * self._current_qps)
        self._last_update = now

    async def try_acquire(self, tokens: int = 1) -> bool:
        async with self._cond:
            await self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._cond.notify()
                return True
            return False

    async def release(self, tokens: int = 1):
        async with self._cond:
            self._tokens = min(self.burst, self._tokens + tokens)
            self._cond.notify()

    @property
    def current_qps(self) -> float:
        return self._current_qps

    async def record_request(self, latency_ms: float, is_error: bool = False):
        """
        记录请求结果，用于自适应调整
        """
        await self._update_stats(latency_ms, is_error)
        await self._adjust_qps()


class ExternalBaseConnection(ABC):
    """
    外部系统连接基类 - 提供统一的连接管理、限流控制和会话复用机制
    
    ============================================
                    使用方法
    ============================================
    
    【1. 创建连接实例】
    conn = ExternalBaseConnection(
        async_qps=50,        # 异步请求QPS限制
        async_burst=100,     # 最大突发请求数
        pool_maxsize=50      # 连接池大小，建议与QPS匹配
    )
    
    【2. 获取会话】
    async_session = await conn._get_async_session()
    sync_session = conn._get_sync_session()
    
    【3. 带超时保护执行】
    result = await conn.execute_with_timeout_protection(
        coro=my_coroutine(),
        operation_name="操作描述"
    )
    
    【4. 监控状态】
    stats = conn.get_connection_stats()
    print(stats)
    
    【5. 动态调整连接池】
    conn.adjust_pool_size(100)
    
    ============================================
                    注意事项
    ============================================
    
    1. 连接池配置：
       - pool_maxsize 建议设置为 async_qps 的值或更大
       - 过小的连接池会导致请求排队超时
    
    2. 限流配置：
       - async_qps 控制每秒请求数
       - async_burst 控制突发请求上限
       - 自适应限流会根据响应时间动态调整
    
    3. 超时配置：
       - _connect_timeout: 连接超时（默认15秒）
       - _read_timeout: 读取超时（默认60秒）
       - _acquire_timeout: 令牌获取超时（默认30秒）
       - 实际超时会根据系统负载和网络质量动态调整

    4. 自适应超时（增强）：
       - 基于网络质量自动调整超时时间
       - 网络好时收紧超时（加快失败检测）
       - 网络差时放宽超时（提高容错性）
       - 可通过类属性自定义阈值和系数
       - 相关配置：_adaptive_success_threshold, _adaptive_failure_threshold 等

    5. 会话复用：
       - 会话会自动复用，最多复用 _max_session_reuse 次
       - 复用计数超过阈值时会自动重建会话
       - 避免手动关闭会话，由连接池管理

    6. 并发控制：
       - 信号量限制最大并发数（默认 MAX_EVENTS_PER_SECOND // 2）
       - 与全局 @async_rate_limit() 装饰器协同工作
       - 确保限流阈值与连接池大小匹配

    7. 增强重试策略：
       - 自动重试失败的请求（指数退避 + 抖动）
       - 重试条件：429(限流)、5xx(服务端错误)、超时、连接错误
       - 默认最多重试3次，延迟 1s → 2s → 4s
       - 可通过类属性自定义：_retry_max_attempts, _retry_base_delay 等
       - 零配置自动激活，可通过 _retry_enabled = False 禁用

    8. 子类实现：
       - 必须实现 auth() 方法进行认证
       - 建议重写 _ping_connection() 实现健康检查
       - 调用父类方法时使用 super()
    """
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB

    _default_sync_qps: float = 10.0
    _default_sync_burst: int = 20
    _default_async_qps: float = 10.0
    _default_async_burst: int = 20

    _use_adaptive_rate_limiter: bool = True
    
    # 连接池配置
    _pool_maxsize: int = 20
    _pool_connections: int = 50
    
    # 超时配置
    _connect_timeout: float = 15.0
    _read_timeout: float = 60.0
    _acquire_timeout: float = 30.0
    
    # 会话复用配置
    _max_session_reuse: int = 100
    
    # 监控指标
    _active_requests: int = 0
    _max_active_requests: int = 0
    _request_timeouts: int = 0

    _ping_endpoint: str = None

    # ============================================
    # 自适应超时配置参数
    # ============================================
    # 连续成功/失败次数阈值
    _adaptive_success_threshold: int = 10
    _adaptive_failure_threshold: int = 3
    # 超时调整系数（收紧/放宽倍数）
    _adaptive_scale_down_min: float = 0.8
    _adaptive_scale_up_max: float = 1.5
    # 超时值边界
    _adaptive_min_timeout: float = 30.0
    _adaptive_max_timeout: float = 180.0
    # 平滑调整系数（避免突变）
    _adaptive_smooth_factor: float = 0.3

    # ============================================
    # 增强重试策略配置参数
    # ============================================
    _retry_enabled: bool = True
    _retry_max_attempts: int = 3
    _retry_base_delay: float = 1.0
    _retry_max_delay: float = 30.0
    _retry_exponential_base: float = 2.0
    _retry_jitter_ratio: float = 0.1
    _retry_on_codes: tuple = (429, 500, 502, 503, 504)

    def __init__(self, sync_qps: float = None, sync_burst: int = None, 
                 async_qps: float = None, async_burst: int = None,
                 pool_maxsize: int = None):
        self._sync_session = None
        self._async_session = None
        
        # 动态调整连接池大小，确保与限流匹配
        if pool_maxsize is None:
            target_qps = async_qps if async_qps is not None else self._default_async_qps
            self._pool_maxsize = max(int(target_qps), self._pool_maxsize)
        else:
            self._pool_maxsize = pool_maxsize
        
        # 会话生命周期管理
        self._session_creation_time = None
        self._session_reuse_count = 0
        
        if self._use_adaptive_rate_limiter:
            self._sync_rate_limiter = AdaptiveTokenBucket(
                initial_qps=sync_qps if sync_qps is not None else self._default_sync_qps,
                burst=sync_burst if sync_burst is not None else self._default_sync_burst
            )
            self._async_rate_limiter = AdaptiveAsyncTokenBucket(
                initial_qps=async_qps if async_qps is not None else self._default_async_qps,
                burst=async_burst if async_burst is not None else self._default_async_burst
            )
        else:
            self._sync_rate_limiter = SyncTokenBucket(
                qps=sync_qps if sync_qps is not None else self._default_sync_qps,
                burst=sync_burst if sync_burst is not None else self._default_sync_burst
            )
            self._async_rate_limiter = AsyncTokenBucket(
                qps=async_qps if async_qps is not None else self._default_async_qps,
                burst=async_burst if async_burst is not None else self._default_async_burst
            )

        # 初始化自适应超时状态
        self._adaptive_state = {
            'success_count': 0,
            'failure_count': 0,
            'current_timeout': float(self._read_timeout),
            'network_quality': 'normal',
            'recent_response_times': [],
            'total_requests': 0,
            'total_successes': 0,
            'total_failures': 0,
        }

        # 初始化重试状态
        self._retry_state = {
            'total_retries': 0,
            'total_retry_successes': 0,
            'total_retry_failures': 0,
            'retry_by_code': {},
        }

    def _get_sync_session(self):
        """
        获取同步会话（真正复用，带连接池配置）
        
        限流：每次获取会话前需要获取令牌
        会话复用：最多复用 _max_session_reuse 次后自动重建
        """
        self._sync_rate_limiter.acquire(timeout=self._acquire_timeout)
        
        # 检查会话是否可用且未超过复用次数
        if self._sync_session is not None:
            try:
                if self._session_reuse_count < self._max_session_reuse:
                    if hasattr(self._sync_session, 'adapters'):
                        if 'http://' in self._sync_session.adapters and \
                           'https://' in self._sync_session.adapters:
                            self._session_reuse_count += 1
                            return self._sync_session
                    elif hasattr(self._sync_session, 'is_closed'):
                        if not self._sync_session.is_closed:
                            self._session_reuse_count += 1
                            return self._sync_session
                    else:
                        self._session_reuse_count += 1
                        return self._sync_session
            except Exception as e:
                logger.debug(f"会话复用检查失败: {str(e)}")
        
        # 创建新会话（带连接池配置）
        from apps.data_opt.utils.common import get_session
        self._sync_session = get_session(
            pool_maxsize=self._pool_maxsize,
            pool_connections=self._pool_connections,
            connect_timeout=self._connect_timeout,
            read_timeout=self._read_timeout
        )
        self._session_creation_time = datetime.now()
        self._session_reuse_count = 1
        return self._sync_session
    
    
    def _close_sync_session(self):
        """
        关闭同步会话
        """
        if self._sync_session:
            if hasattr(self._sync_session, 'close'):
                self._sync_session.close()
            self._sync_session = None


    async def _get_async_session(self):
        """
        获取异步会话（真正复用，带连接池配置）
        
        限流：每次获取会话前需要获取令牌
        会话复用：最多复用 _max_session_reuse 次后自动重建
        """
        await self._async_rate_limiter.acquire(timeout=self._acquire_timeout)
        
        # 检查会话是否可用且未超过复用次数
        if self._async_session is not None:
            try:
                if self._session_reuse_count < self._max_session_reuse:
                    if hasattr(self._async_session, '_client'):
                        transport = getattr(self._async_session._client, '_transport', None)
                        if transport and not getattr(transport, '_closed', False):
                            self._session_reuse_count += 1
                            return self._async_session
                    elif hasattr(self._async_session, 'is_closed'):
                        if not self._async_session.is_closed:
                            self._session_reuse_count += 1
                            return self._async_session
                    else:
                        self._session_reuse_count += 1
                        return self._async_session
            except Exception as e:
                logger.debug(f"异步会话复用检查失败: {str(e)}")
        
        # 创建新会话（带连接池配置）
        self._async_session = await get_async_session(
            pool_maxsize=self._pool_maxsize,
            pool_connections=self._pool_connections,
            connect_timeout=self._connect_timeout,
            read_timeout=self._read_timeout
        )
        self._session_creation_time = datetime.now()
        self._session_reuse_count = 1
        return self._async_session


    async def _close_async_session(self):
        """
        关闭异步会话
        """
        if self._async_session:
            if hasattr(self._async_session, 'aclose'):
                await self._async_session.aclose()
            elif hasattr(self._async_session, 'close'):
                self._async_session.close()
            self._async_session = None


    # ============ 增强重试策略 ============

    def _should_retry(self, attempt: int, exception: Exception = None, status_code: int = None) -> bool:
        """
        判断是否应该重试

        Args:
            attempt: 当前尝试次数（从1开始）
            exception: 异常对象
            status_code: HTTP 状态码

        Returns:
            bool: 是否应该重试
        """
        if not self._retry_enabled:
            return False

        if attempt >= self._retry_max_attempts:
            return False

        if status_code and status_code in self._retry_on_codes:
            return True

        if exception:
            retryable_exceptions = (
                ConnectionError,
                TimeoutError,
                asyncio.TimeoutError,
                ConnectionResetError,
                ConnectionAbortedError,
            )
            if isinstance(exception, retryable_exceptions):
                return True

        return False

    def _get_retry_delay(self, attempt: int, response_time: float = None) -> float:
        """
        计算重试延迟（指数退避 + 抖动）

        Args:
            attempt: 当前尝试次数（从1开始）
            response_time: 上次响应时间（可选，用于自适应调整）

        Returns:
            float: 延迟时间（秒）
        """
        import random

        base_delay = self._retry_base_delay
        if response_time and response_time > 0:
            base_delay = min(response_time * 2, self._retry_max_delay)

        delay = min(
            base_delay * (self._retry_exponential_base ** attempt),
            self._retry_max_delay
        )

        jitter_range = delay * self._retry_jitter_ratio
        delay = delay + random.uniform(-jitter_range, jitter_range)

        return max(0.1, delay)

    async def _execute_with_retry(self, coro_factory, operation_name: str):
        """
        带重试的异步执行

        Args:
            coro_factory: 协程工厂函数（每次重试时调用以获取新协程）
            operation_name: 操作名称

        Returns:
            协程执行结果

        Raises:
            最后一次尝试的异常
        """
        last_exception = None
        attempt = 0

        while attempt < self._retry_max_attempts:
            attempt += 1
            try:
                result = await coro_factory()
                if attempt > 1:
                    self._retry_state['total_retry_successes'] += 1
                    logger.info(
                        f"重试成功: {operation_name}, "
                        f"尝试次数: {attempt}, "
                        f"网络状态: {self.get_network_quality()}"
                    )
                return result

            except asyncio.TimeoutError as e:
                last_exception = e
                self._record_retry_failure(status_code=408)

                if not self._should_retry(attempt, exception=e, status_code=408):
                    raise

                delay = self._get_retry_delay(attempt)
                logger.warning(
                    f"请求超时准备重试: {operation_name}, "
                    f"尝试 {attempt}/{self._retry_max_attempts}, "
                    f"等待 {delay:.2f}s"
                )
                await asyncio.sleep(delay)

            except Exception as e:
                last_exception = e
                status_code = getattr(e, 'status_code', None) or getattr(e, 'status', None)

                self._record_retry_failure(status_code=status_code)

                if not self._should_retry(attempt, exception=e, status_code=status_code):
                    raise

                delay = self._get_retry_delay(attempt)
                logger.warning(
                    f"请求失败准备重试: {operation_name}, "
                    f"状态码: {status_code}, "
                    f"尝试 {attempt}/{self._retry_max_attempts}, "
                    f"等待 {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        self._retry_state['total_retry_failures'] += 1
        raise last_exception

    def _record_retry_failure(self, status_code: int = None):
        """
        记录重试失败

        Args:
            status_code: HTTP 状态码
        """
        self._retry_state['total_retries'] += 1

        if status_code:
            code_str = str(status_code)
            if code_str not in self._retry_state['retry_by_code']:
                self._retry_state['retry_by_code'][code_str] = 0
            self._retry_state['retry_by_code'][code_str] += 1

    # ============ 智能超时处理 ============

    def _adjust_timeout_on_success(self, response_time: float):
        """
        成功响应后调整超时（网络变好时收紧超时）

        策略：连续成功N次后，如果当前响应时间远低于超时值，则逐步收紧超时
        """
        state = self._adaptive_state
        state['success_count'] += 1
        state['failure_count'] = 0
        state['total_successes'] += 1
        state['total_requests'] += 1

        # 记录响应时间用于分析
        state['recent_response_times'].append(response_time)
        if len(state['recent_response_times']) > 20:
            state['recent_response_times'].pop(0)

        if state['success_count'] >= self._adaptive_success_threshold:
            # 计算平均响应时间
            avg_response_time = sum(state['recent_response_times']) / len(state['recent_response_times'])
            current_timeout = state['current_timeout']

            # 如果平均响应时间远低于当前超时（说明网络好），则收紧
            if avg_response_time < current_timeout * 0.6:
                # 收紧超时：乘以平滑系数，但不低于最小值
                new_timeout = max(
                    self._adaptive_min_timeout,
                    current_timeout * self._adaptive_scale_down_min
                )
                state['current_timeout'] = new_timeout
                state['network_quality'] = 'good'
                logger.debug(
                    f"网络质量改善: 超时 {current_timeout:.2f}s → {new_timeout:.2f}s, "
                    f"平均响应: {avg_response_time:.3f}s"
                )
            else:
                state['network_quality'] = 'normal'

            state['success_count'] = 0

    def _adjust_timeout_on_failure(self, timeout_occurred: bool = False):
        """
        失败响应后调整超时（网络变差时放宽超时）

        策略：连续失败N次后，逐步放宽超时限制

        Args:
            timeout_occurred: 是否发生了超时
        """
        state = self._adaptive_state
        state['failure_count'] += 1
        state['success_count'] = 0
        state['total_failures'] += 1
        state['total_requests'] += 1

        if timeout_occurred:
            state['failure_count'] += 2  # 超时算2次失败

        if state['failure_count'] >= self._adaptive_failure_threshold:
            current_timeout = state['current_timeout']

            # 放宽超时：乘以向上系数，但不超过最大值
            new_timeout = min(
                self._adaptive_max_timeout,
                current_timeout * self._adaptive_scale_up_max
            )

            if new_timeout != current_timeout:
                state['current_timeout'] = new_timeout
                state['network_quality'] = 'poor'
                logger.warning(
                    f"网络质量下降: 超时 {current_timeout:.2f}s → {new_timeout:.2f}s, "
                    f"连续失败: {state['failure_count']}次"
                )

            state['failure_count'] = 0

    def get_adaptive_timeout(self) -> float:
        """
        获取当前自适应超时值

        Returns:
            float: 当前计算的超时时间（秒）
        """
        return self._adaptive_state['current_timeout']

    def get_network_quality(self) -> str:
        """
        获取网络质量状态

        Returns:
            str: 网络质量状态 ('good', 'normal', 'poor')
        """
        return self._adaptive_state['network_quality']

    async def execute_with_timeout_protection(self, coro, operation_name: str):
        """
        带超时保护的异步执行包装

        综合考虑系统负载和网络质量两个因素动态调整超时时间
        支持自动重试（指数退避 + 抖动）

        Args:
            coro: 要执行的协程
            operation_name: 操作名称，用于日志记录

        Returns:
            协程执行结果

        Raises:
            asyncio.TimeoutError: 超时异常
        """
        import time

        async def run_with_timeout():
            # 因素1：系统负载（基于活跃请求数）
            load_factor = min(self._active_requests / self._pool_maxsize, 2.0)
            load_timeout = self._read_timeout * (1 + load_factor)

            # 因素2：网络质量（基于历史成功/失败率）
            network_timeout = self.get_adaptive_timeout()

            # 综合策略：取两者中更宽松的（保守策略），确保不会过快超时
            adjusted_timeout = max(load_timeout, network_timeout)

            self._active_requests += 1
            if self._active_requests > self._max_active_requests:
                self._max_active_requests = self._active_requests

            try:
                start_time = time.time()
                # 支持协程工厂函数（用于重试场景）
                if callable(coro):
                    coro_instance = coro()
                else:
                    coro_instance = coro
                result = await asyncio.wait_for(coro_instance, timeout=adjusted_timeout)
                response_time = time.time() - start_time

                # 成功：自动调整超时（网络好时收紧）
                self._adjust_timeout_on_success(response_time)

                return result, response_time

            except asyncio.TimeoutError:
                self._request_timeouts += 1
                # 失败：自动放宽超时（网络差时容忍）
                self._adjust_timeout_on_failure(timeout_occurred=True)
                logger.warning(
                    f"请求超时: {operation_name}, "
                    f"活跃请求: {self._active_requests}, "
                    f"网络状态: {self.get_network_quality()}, "
                    f"超时: {adjusted_timeout:.2f}s"
                )
                raise

            except Exception as e:
                # 其他异常也记录失败
                self._adjust_timeout_on_failure(timeout_occurred=False)
                raise

            finally:
                self._active_requests -= 1

        last_exception = None
        attempt = 0
        last_result = None

        while attempt < self._retry_max_attempts:
            attempt += 1
            try:
                result, response_time = await run_with_timeout()
                last_result = result
                if attempt > 1:
                    self._retry_state['total_retry_successes'] += 1
                    logger.info(
                        f"重试成功: {operation_name}, "
                        f"尝试次数: {attempt}, "
                        f"网络状态: {self.get_network_quality()}"
                    )
                return result

            except asyncio.TimeoutError as e:
                last_exception = e
                status_code = 408
                self._record_retry_failure(status_code=status_code)

                if not self._should_retry(attempt, exception=e, status_code=status_code):
                    raise

                delay = self._get_retry_delay(attempt)
                logger.warning(
                    f"请求超时准备重试: {operation_name}, "
                    f"尝试 {attempt}/{self._retry_max_attempts}, "
                    f"等待 {delay:.2f}s"
                )
                await asyncio.sleep(delay)

            except Exception as e:
                last_exception = e
                status_code = getattr(e, 'status_code', None) or getattr(e, 'status', None)

                self._record_retry_failure(status_code=status_code)

                if not self._should_retry(attempt, exception=e, status_code=status_code):
                    raise

                delay = self._get_retry_delay(attempt)
                logger.warning(
                    f"请求失败准备重试: {operation_name}, "
                    f"状态码: {status_code}, "
                    f"尝试 {attempt}/{self._retry_max_attempts}, "
                    f"等待 {delay:.2f}s"
                )
                await asyncio.sleep(delay)

        self._retry_state['total_retry_failures'] += 1
        raise last_exception

    # ============ 状态监控 ============

    def get_connection_stats(self) -> dict:
        """
        获取连接状态统计信息

        Returns:
            dict: 包含以下字段的统计信息
                - active_requests: 当前活跃请求数
                - max_active_requests: 历史最大活跃请求数
                - pool_maxsize: 连接池最大连接数
                - session_reuse_count: 当前会话复用次数
                - request_timeouts: 请求超时总次数
                - session_age_minutes: 当前会话存活时间（分钟）
                - network_quality: 网络质量状态 ('good', 'normal', 'poor')
                - adaptive_timeout: 当前自适应超时值（秒）
                - success_rate: 请求成功率
                - total_retries: 总重试次数
                - total_retry_successes: 重试成功次数
                - total_retry_failures: 重试失败次数
                - retry_rate: 重试率（%）
                - retry_by_code: 按状态码分布的重试次数
        """
        session_age = (datetime.now() - self._session_creation_time).total_seconds() / 60 \
                      if self._session_creation_time else None

        state = self._adaptive_state
        total = state['total_requests']
        success_rate = (state['total_successes'] / total * 100) if total > 0 else 0

        retry_state = self._retry_state
        total_retries = retry_state['total_retries']
        retry_rate = (total_retries / total * 100) if total > 0 else 0

        return {
            'active_requests': self._active_requests,
            'max_active_requests': self._max_active_requests,
            'pool_maxsize': self._pool_maxsize,
            'session_reuse_count': self._session_reuse_count,
            'request_timeouts': self._request_timeouts,
            'session_age_minutes': session_age,
            'network_quality': state['network_quality'],
            'adaptive_timeout': round(state['current_timeout'], 2),
            'success_rate': round(success_rate, 2),
            'total_requests': total,
            'total_successes': state['total_successes'],
            'total_failures': state['total_failures'],
            'total_retries': total_retries,
            'total_retry_successes': retry_state['total_retry_successes'],
            'total_retry_failures': retry_state['total_retry_failures'],
            'retry_rate': round(retry_rate, 2),
            'retry_by_code': retry_state['retry_by_code'],
        }


    def adjust_pool_size(self, new_size: int):
        """
        动态调整连接池大小
        
        Args:
            new_size: 新的连接池大小
        """
        if new_size > 0 and new_size != self._pool_maxsize:
            logger.info(f"连接池大小调整: {self._pool_maxsize} -> {new_size}")
            self._pool_maxsize = new_size
            # 强制重建会话以应用新配置
            if self._async_session:
                asyncio.create_task(self._close_async_session())
            if self._sync_session:
                self._close_sync_session()


    # ============ 连接池预热机制 ============
    
    # 类级别预热状态
    _warm_up_completed: bool = False
    _warm_up_time: datetime = None
    _warm_up_lock: asyncio.Lock = None
    _warm_up_count: int = 3
    
    def _get_warm_up_lock(self):
        """获取预热锁（延迟初始化）"""
        if self._warm_up_lock is None:
            self._warm_up_lock = asyncio.Lock()
        return self._warm_up_lock
    
    def _check_warm_up_status(self) -> bool:
        """检查预热状态"""
        return self._warm_up_completed
    
    def _mark_warm_up_completed(self):
        """标记预热完成"""
        self._warm_up_completed = True
        self._warm_up_time = datetime.now()
        logger.info(f"连接池预热完成，时间: {self._warm_up_time}")
    
    def _reset_warm_up_status(self):
        """重置预热状态（用于重新预热）"""
        self._warm_up_completed = False
        self._warm_up_time = None
        logger.info("连接池预热状态已重置")
    
    async def _warm_up_connection(self, connection_count: int = None) -> bool:
        """
        通用连接预热方法（异步）
        
        Args:
            connection_count: 预建立的连接数，默认使用类变量 _warm_up_count
        
        Returns:
            True: 预热成功
            False: 预热失败（但不阻塞业务）
        """
        if self._check_warm_up_status():
            return True
        
        if connection_count is None:
            connection_count = self._warm_up_count
        
        async with self._get_warm_up_lock():
            if self._check_warm_up_status():
                return True
            
            try:
                logger.info(f"开始预热连接池，目标连接数: {connection_count}")
                
                # 预热异步会话
                for i in range(connection_count):
                    session = await self._get_async_session()
                    # 可选：发送轻量级请求验证
                    ping_success = await self._ping_connection(session)
                    if not ping_success:
                        logger.warning(f"异步连接 #{i+1} 验证失败")
                
                # 预热同步会话
                for i in range(connection_count):
                    session = self._get_sync_session()
                    ping_success = self._ping_connection_sync(session)
                    if not ping_success:
                        logger.warning(f"同步连接 #{i+1} 验证失败")
                
                self._mark_warm_up_completed()
                return True
                
            except Exception as e:
                logger.warning(f"连接池预热失败: {str(e)}")
                return False
    
    async def _ping_connection(self, session) -> bool:
        """
        验证连接是否有效（异步）- 智能 ping 实现
        
        智能判断 _ping_endpoint 的类型：
        - URL（http:// 或 https:// 开头）：执行 HTTP GET 请求
        - IP 地址或域名：执行 ICMP ping 命令
        - 权限不足时降级处理（视为连接有效）
        
        Returns:
            True: 连接有效
            False: 连接无效或验证失败
        """
        if not self._ping_endpoint:
            return True
        
        endpoint = str(self._ping_endpoint).strip()
        
        # 判断 endpoint 类型
        if _is_url(endpoint):
            # URL 类型：执行 HTTP GET 请求
            logger.debug(f"执行 HTTP 健康检查: {endpoint}")
            try:
                response = await session.get(endpoint, timeout=10)
                if hasattr(response, 'status_code'):
                    return response.status_code == 200
                elif hasattr(response, 'status'):
                    return response.status == 200
                return True
            except Exception as e:
                logger.debug(f"HTTP 健康检查失败: {str(e)}")
                return False
        
        elif _is_ip_address(endpoint) or _is_domain(endpoint):
            # IP 地址或域名：执行 ICMP ping
            logger.debug(f"执行 ICMP ping: {endpoint}")
            return _execute_icmp_ping(endpoint)
        
        else:
            # 未知类型：尝试作为 URL 处理
            logger.debug(f"未知 endpoint 类型，尝试作为 URL: {endpoint}")
            try:
                response = await session.get(endpoint, timeout=10)
                if hasattr(response, 'status_code'):
                    return response.status_code == 200
                elif hasattr(response, 'status'):
                    return response.status == 200
                return True
            except Exception as e:
                logger.debug(f"未知类型 endpoint 验证失败: {str(e)}")
                return False
    
    def _ping_connection_sync(self, session) -> bool:
        """
        验证连接是否有效（同步）- 智能 ping 实现
        
        智能判断 _ping_endpoint 的类型：
        - URL（http:// 或 https:// 开头）：执行 HTTP GET 请求
        - IP 地址或域名：执行 ICMP ping 命令
        - 权限不足时降级处理（视为连接有效）
        
        Returns:
            True: 连接有效
            False: 连接无效或验证失败
        """
        if not getattr(self, '_ping_endpoint', None):
            return True
        
        endpoint = str(self._ping_endpoint).strip()
        
        # 判断 endpoint 类型
        if _is_url(endpoint):
            # URL 类型：执行 HTTP GET 请求
            logger.debug(f"执行同步 HTTP 健康检查: {endpoint}")
            try:
                response = session.get(endpoint, timeout=10)
                if hasattr(response, 'status_code'):
                    return response.status_code == 200
                elif hasattr(response, 'status'):
                    return response.status == 200
                return True
            except Exception as e:
                logger.debug(f"同步 HTTP 健康检查失败: {str(e)}")
                return False
        
        elif _is_ip_address(endpoint) or _is_domain(endpoint):
            # IP 地址或域名：执行 ICMP ping
            logger.debug(f"执行同步 ICMP ping: {endpoint}")
            return _execute_icmp_ping(endpoint)
        
        else:
            # 未知类型：尝试作为 URL 处理
            logger.debug(f"未知 endpoint 类型，尝试作为 URL: {endpoint}")
            try:
                response = session.get(endpoint, timeout=10)
                if hasattr(response, 'status_code'):
                    return response.status_code == 200
                elif hasattr(response, 'status'):
                    return response.status == 200
                return True
            except Exception as e:
                logger.debug(f"未知类型 endpoint 验证失败: {str(e)}")
                return False
    
    async def ensure_connection_warm(self) -> bool:
        """
        确保连接已预热（异步）
        
        如果连接未预热，则自动执行预热
        
        Returns:
            True: 已预热或预热成功
            False: 预热失败
        """
        if self._check_warm_up_status():
            return True
        return await self._warm_up_connection()


    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        raise NotImplementedError("auth method not implemented")


    def register_source(self, source):
        """
        注册数据源
        source: 数据源对象或数据源 class 列表
        """
        if not isinstance(source, list):
            source = [source]
        for s in source:
            s._CONNECTION = self
        return self




def _detect_os_type() -> str:
    """检测操作系统类型"""
    if sys.platform.startswith('win'):
        return 'windows'
    elif sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform == 'darwin':
        return 'macos'
    return 'unknown'


def _is_url(endpoint: str) -> bool:
    """判断是否为 URL"""
    url_pattern = re.compile(
        r'^https?://'  # http:// 或 https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # 域名
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP 地址
        r'(?::\d+)?'  # 端口
        r'(?:/?|[/?]\S+)$',  # 路径
        re.IGNORECASE
    )
    return bool(url_pattern.match(endpoint))


def _is_ip_address(endpoint: str) -> bool:
    """判断是否为 IP 地址"""
    ip_pattern = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    )
    return bool(ip_pattern.match(endpoint))


def _is_domain(endpoint: str) -> bool:
    """判断是否为域名"""
    domain_pattern = re.compile(
        r'^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,}$',
        re.IGNORECASE
    )
    return bool(domain_pattern.match(endpoint)) and not _is_url(endpoint)


def _execute_icmp_ping(host: str, timeout: int = 5) -> bool:
    """
    跨平台 ICMP ping
    
    Args:
        host: 目标主机名或 IP 地址
        timeout: 超时时间（秒）
    
    Returns:
        True: ping 成功
        False: ping 失败、超时或权限不足
    """
    os_type = _detect_os_type()
    
    try:
        if os_type == 'windows':
            # Windows: ping -n 1 -w <毫秒> hostname
            args = ['ping', '-n', '1', '-w', str(timeout * 1000), host]
        else:
            # Linux/macOS: ping -c 1 -W <秒> hostname
            args = ['ping', '-c', '1', '-W', str(timeout), host]
        
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout + 2,  # 额外2秒缓冲
            stderr=subprocess.DEVNULL
        )
        
        if result.returncode == 0:
            return True
        
        # 检查是否为权限问题
        stderr = result.stderr.lower() if hasattr(result, 'stderr') else ''
        stdout = result.stdout.lower() if hasattr(result, 'stdout') else ''
        
        if 'permission' in stderr or 'permission' in stdout:
            logger.debug(f"ICMP ping 权限不足: {host}")
            return True  # 权限不足时视为连接有效（降级处理）
        
        logger.debug(f"ICMP ping 失败: {host}, 返回码: {result.returncode}")
        return False
        
    except subprocess.TimeoutExpired:
        logger.debug(f"ICMP ping 超时: {host}")
        return False
    except PermissionError:
        logger.debug(f"ICMP ping 权限被拒绝: {host}")
        return True  # 权限不足时视为连接有效（降级处理）
    except Exception as e:
        logger.debug(f"ICMP ping 执行异常: {host}, 错误: {str(e)}")
        return True  # 未知异常时视为连接有效（降级处理）







class BaseSource:
    """
    数据对象基类
    
    用于处理从ERP拉取的基础数据，如物料、工作中心、BOM等
    支持链式调用，如：tplus.material().query()
    """

    _CONNECTION: ExternalBaseConnection = None   # 连接对象，通过 ExternalBaseConnection 实例的 register_objects 方法注入
    _QUERY_ENDPOINT : str = None   # 查询接口路径
    _QUERY_BATCH_ENDPOINT : str = None   # 查询批量接口路径
    _PULL_PYDANTIC_MODEL : type[PydanticModel] = None   # 拉取数据的Pydantic模型
    _FIELD_HINTS : dict[str, str] = None   # 字段注解
    _DOCUMENTATION_URL : str = None   # 技术文档URL，无逻辑意义


    def __init__(self, raw_data: dict):
        self.raw_data = raw_data
        self.external_data = None
        self.internal_data = None
        # self._CONNECTION = self.__class__._CONNECTION
    

    async def query(self):
        """
        查询数据
        
        Raises:
            NotImplementedError: 子类必须实现query方法
        """
        raise NotImplementedError("子类必须实现query方法")

    
    async def query_batch(self):
        """
        异步查询数据
        
        Raises:
            NotImplementedError: 子类必须实现query_batch方法
        """
        raise NotImplementedError("子类必须实现query_batch方法")
    

    @property
    def documentation_url(self):
        return self._DOCUMENTATION_URL
    


class BaseVoucher(BaseSource):
    """
    凭证基类
    
    用于处理需要创建、更新的ERP凭证，如生产加工单、领料申请、请购单等
    """

    _CREATE_ENDPOINT: str = None   # 创建接口路径
    _UPDATE_ENDPOINT: str = None   # 更新接口路径
    _DELETE_ENDPOINT: str = None   # 删除接口路径
    _APPROVE_ENDPOINT: str = None   # 审批接口路径
    _PUSH_PYDANTIC_MODEL: Type[PydanticModel] = None   # 推送数据的Pydantic模型


    @classmethod
    async def create(cls, event_data: dict, _aps, _erp, pydantic_model: Type[PydanticModel] = None, **kwargs):
        """
        创建凭证
        
        Raises:
            NotImplementedError: 子类必须实现create方法
        """
        raise NotImplementedError("子类必须实现create方法")


    @classmethod
    async def update(cls, event_data: dict, _erp, **kwargs):
        """
        更新凭证
        
        Raises:
            NotImplementedError: 子类必须实现update方法
        """
        raise NotImplementedError("子类必须实现update方法")
    

    @classmethod
    async def delete(cls, event_data: dict, _erp, **kwargs):
        """
        删除凭证
        
        Raises:
            NotImplementedError: 子类必须实现delete方法
        """
        raise NotImplementedError("子类必须实现delete方法")


    @classmethod
    async def approve(cls, event_data: dict, _erp, **kwargs):
        """
        审批凭证
        
        Raises:
            NotImplementedError: 子类必须实现approve方法
        """
        raise NotImplementedError("子类必须实现approve方法")



class MoVoucher(BaseVoucher):

    @classmethod
    async def create_batch(
        cls,
        event_data_list: list[dict],
        _erp,
        production_cache_items = None,
        pydantic_model: Type[PydanticModel] = None,
        remain_native_supplyno: bool = True,
        data_preprocessor = None,
        **kwargs
    ):
        """
        批量创建生产加工单
        Args:
            event_data_list: 生产加工单数据列表
            _aps: ApsPayloadSponsor 实例
            pydantic_model: 生产加工单数据模型，默认使用 cls._PUSH_PYDANTIC_MODEL
            production_cache_items: 生产缓存项
            remain_native_supplyno: 是否保留原生供应号
            data_preprocessor: 数据预处理器，签名 (data: dict, _aps: ApsPayloadSponsor) -> dict，
                               在构造 Pydantic 模型前对数据字典进行租户定制化补充
        Returns:
            None
        """
        from . import ApsPayloadSponsor, CacheItem
        

        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        # await cls._CONNECTION.auth()

        if production_cache_items is None:
            production_cache_items = [CacheItem.SUPPLY_MO]
        supply_nos = [s['supplyno'] for s in event_data_list]
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await TSupply.filter(supplyno__in=supply_nos).update(memo=f" {now} 📤 正在推送...")
        _aps = ApsPayloadSponsor(production_cache_items=production_cache_items)
        await _aps.establish_production_cache(supplynos=supply_nos)

        pydantic_model = pydantic_model or cls._PUSH_PYDANTIC_MODEL

        tasks = [
            cls.create(
                event_data=_,
                _aps=_aps,
                _erp=_erp,
                pydantic_model=pydantic_model,
                remain_native_supplyno=remain_native_supplyno,
                data_preprocessor=data_preprocessor,
                **kwargs
            )
            for _ in event_data_list
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
        # 最后兜底，更新所有状态为 A2E 的生产加工单为 CRE
        unknown_failed = await TSupply.filter(status='A2E', supplyno__in=supply_nos).values('supplyno')
        if unknown_failed:
            tasks = [
                _erp.mo_release_failed(native_plno=_["supplyno"], msg="推送失败，请重试")
                for _ in unknown_failed
            ]
            await asyncio.gather(*tasks, return_exceptions=True)



class RsVoucher(BaseVoucher):
    
    @classmethod
    async def create_batch(
        cls,
        event_data_list: list[dict],
        _erp,
        production_cache_items=None,
        pydantic_model: Type[PydanticModel] = None,
        data_preprocessor=None,
        **kwargs
    ):
        """
        批量创建领料申请
        Args:
            event_data_list: 领料申请数据列表
            _aps: ApsPayloadSponsor 实例
            production_cache_items: 生产缓存项
            pydantic_model: 领料申请数据模型，默认使用 cls._PUSH_PYDANTIC_MODEL
            data_preprocessor: 数据预处理器，签名 (data: dict, _aps: ApsPayloadSponsor) -> dict，
                               在构造 Pydantic 模型前对数据字典进行租户定制化补充
        Returns:
            None
        """
        from . import ApsPayloadSponsor, CacheItem
        

        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        # await cls._CONNECTION.auth()

        if production_cache_items is None:
            production_cache_items = [CacheItem.SUPPLY_MO, CacheItem.DEMAND]
        supply_nos = [s['supplyno'] for s in event_data_list]
        await TDemand.filter(demandno__in=supply_nos).update(status='A2E', memo=" 📤 正在推送...")

        _aps = ApsPayloadSponsor(production_cache_items=production_cache_items)
        await _aps.establish_production_cache(supplynos=supply_nos)

        pydantic_model = pydantic_model or cls._PUSH_PYDANTIC_MODEL

        tasks = [
            cls.create(
                event_data=_,
                _aps=_aps,
                _erp=_erp,
                pydantic_model=pydantic_model,
                data_preprocessor=data_preprocessor,
                **kwargs
            )
            for _ in event_data_list
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

        unknown_failed = await TDemand.filter(status='A2E', demandno__in=supply_nos).values('demandno')
        if unknown_failed:
            tasks = [
                _erp.rs_release_failed(rsno=_["demandno"], msg="推送失败，请重试")
                for _ in unknown_failed
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
    

class ExternalData:
    """外部ERP数据包装器"""
    def __init__(self, raw_data: dict, pydantic_model: Type[PydanticModel] = None):
        self.raw_data = raw_data
        self._pydantic_model = pydantic_model
        self._dumped_data = None


    @property
    def is_empty(self):
        return not self.raw_data


    def dumps(self, pydantic_model: Type[PydanticModel] = None) -> dict:
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"

        if pydantic_model:
            if self._dumped_data is None or pydantic_model is not self._pydantic_model:
                self._pydantic_model = pydantic_model
                self._dumped_data = pydantic_model.model_dump(self.raw_data)
        else:
            if self._dumped_data is None:
                self._dumped_data = self._pydantic_model.model_dump(self.raw_data)
        return self._dumped_data



class ExternalDataSet:
    """外部系统数据列表包装器"""

    def __init__(self, raw_data: List[dict], pydantic_model: Type[PydanticModel] = None):
        """
        初始化数据对象
        
        Args:
            raw_data: 初始数据
        """
        self._pydantic_model = pydantic_model
        self.raw_data = raw_data
        # self._set = [ExternalData(raw_data=data, pydantic_model=pydantic_model) for data in self.raw_data]
        self._dumped_data = None
        

    def __getitem__(self, index: int):
        return ExternalData(raw_data=self.raw_data[index], pydantic_model=self._pydantic_model)


    @property
    def is_empty(self):
        return not self.raw_data


    async def dumps(self, pydantic_model: Type[PydanticModel] = None, to_dbs: str | List[str] = MYAPS_DB_SET, to_dbtable: str = None) -> List[dict]:
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"

        if pydantic_model:
            if self._dumped_data is None or pydantic_model is not self._pydantic_model:
                self._pydantic_model = pydantic_model
                self._dumped_data = [pydantic_model(**_).model_dump() for _ in self.raw_data]
        else:
            if self._dumped_data is None:
                self._dumped_data = [self._pydantic_model(**_).model_dump() for _ in self.raw_data]

        if to_dbtable:
            # 写库前基于当前 raw_data 重新转换，避免命中转换缓存写入陈旧数据
            model = pydantic_model or self._pydantic_model
            write_data = [
                {key: (value.value if isinstance(value, Enum) else value)
                 for key, value in model(**_).model_dump().items()}
                for _ in self.raw_data
            ]
            result = await db_bupsert(db_names=to_dbs, model_or_tablename=to_dbtable, data_list=write_data)
            if result.meta.get('has_errors'):
                raise RuntimeError(f"写库 {to_dbtable} 失败: {result.message}")

        return self._dumped_data

        
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
    
    整合了令牌桶限流和信号量并发控制：
    - 令牌桶：控制每秒请求数
    - 信号量：控制最大并发数（避免瞬时并发过高）
    
    用法:
        @async_rate_limit(MAX_EVENTS_PER_SECOND)
        async def handle_pl_status_a2e(supplyno_or_data):
            ...
    
    限流维度: 基于被装饰函数的 event_count 参数指定的事件数量进行限流
    """
    global db_event_async_bucket
    if rate is None:
        rate = MAX_EVENTS_PER_SECOND
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 延迟初始化令牌桶，避免模块导入时没有事件循环的问题
            global db_event_async_bucket
            if db_event_async_bucket is None:
                db_event_async_bucket = AsyncTokenBucket(rate)
                db_event_async_bucket.start()
            
            event_count = kwargs.pop('event_count', 1)
            await db_event_async_bucket.acquire(event_count)
            semaphore = get_db_event_semaphore()
            async with semaphore:
                return await func(*args, **kwargs)
        return wrapper
    return decorator


def sync_rate_limit(rate: int = None):
    """
    同步函数限流装饰器 - 所有装饰的函数共享同一个令牌桶
    
    整合了令牌桶限流和信号量并发控制：
    - 令牌桶：控制每秒请求数
    - 信号量：控制最大并发数（避免瞬时并发过高）
    
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
            semaphore = get_db_event_semaphore()
            with semaphore:
                return func(*args, **kwargs)
        return wrapper
    return decorator


#################################################################################
# 异常处理和日志记录装饰器
#################################################################################

def generate_request_id() -> str:
    """生成唯一请求追踪ID"""
    return str(uuid.uuid4())


class ProjectLogger:
    """项目统一日志封装"""
    
    @staticmethod
    def success(module: str, operation: str, message: str, **kwargs):
        """记录成功日志"""
        logger.info(
            f"[SUCCESS] {module} - {operation}: {message}",
            extra=kwargs
        )
    
    @staticmethod
    def fail(module: str, operation: str, message: str, **kwargs):
        """记录失败日志"""
        logger.error(
            f"[FAIL] {module} - {operation}: {message}",
            extra=kwargs
        )
    
    @staticmethod
    def warning(module: str, operation: str, message: str, **kwargs):
        """记录警告日志"""
        logger.warning(
            f"[WARNING] {module} - {operation}: {message}",
            extra=kwargs
        )
    
    @staticmethod
    def debug(module: str, operation: str, message: str, **kwargs):
        """记录调试日志"""
        logger.debug(
            f"[DEBUG] {module} - {operation}: {message}",
            extra=kwargs
        )


def _get_operation_name(operation: Optional[str], func: Callable) -> str:
    """
    获取操作名称，优先级从高到低：
    1. 显式传入的 operation 参数
    2. 函数的 description 属性
    3. 函数的 description 参数默认值
    4. 模块名.类名.函数名（如果有类）或模块名.函数名

    Args:
        operation: 显式传入的操作名称
        func: 被装饰的函数

    Returns:
        操作名称字符串
    """
    if operation is not None:
        return operation

    # 尝试获取函数的 description 属性
    if hasattr(func, 'description') and func.description:
        return func.description

    # 尝试获取函数的 description 参数默认值
    try:
        sig = inspect.signature(func)
        if 'description' in sig.parameters:
            param = sig.parameters['description']
            if param.default is not inspect.Parameter.empty and param.default:
                return param.default
    except (ValueError, TypeError):
        pass

    # 构建兜底的操作名称
    parts = []

    # 添加模块名（只取最后一部分）
    if func.__module__:
        module_name = func.__module__.split('.')[-1]
        parts.append(module_name)

    # 解析 qualname 获取类名和函数名
    qualname_parts = func.__qualname__.split('.')
    if len(qualname_parts) > 1:
        # 有类名
        class_name = qualname_parts[-2]
        func_name = qualname_parts[-1]
        parts.append(class_name)
        parts.append(func_name)
    else:
        # 没有类名，只有函数名
        parts.append(qualname_parts[0])

    return '.'.join(parts)


def service_operation(module: str, operation: Optional[str] = None, **default_context):
    """
    统一日志和异常处理装饰器（同步版本）
    
    Args:
        module: 模块名称
        operation: 操作名称（可选，为None时自动推导）
        **default_context: 默认上下文参数
    
    operation 参数自动推导规则：
        1. 显式传入的 operation 参数
        2. 函数的 description 属性
        3. 模块名.类名.函数名（如果有类）或模块名.函数名
    
    用法:
        @service_operation(module="MO推送", operation="创建生产加工单")
        def create_mo(event_data, _aps, _erp):
            # 业务逻辑...
        
        # 或自动推导操作名称
        @service_operation(module="MO推送")
        def create_mo(event_data, _aps, _erp):
            # 业务逻辑...
    
    自动记录:
        - 请求ID追踪
        - 操作开始/成功/失败日志
        - 异常类型和堆栈信息
    """
    def decorator(func):
        # 在装饰时确定 operation 值，避免每次调用都计算
        resolved_operation = _get_operation_name(operation, func)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            request_id = generate_request_id()
            context = {"request_id": request_id, **default_context}
            
            # 提取关键字段作为上下文
            event_data = kwargs.get('event_data') or (args[1] if len(args) > 1 else None)
            if isinstance(event_data, dict):
                if 'supplyno' in event_data:
                    context['supplyno'] = event_data['supplyno']
                if 'demandno' in event_data:
                    context['demandno'] = event_data['demandno']
            
            ProjectLogger.debug(module, resolved_operation, "开始执行", **context)
            
            try:
                result = func(*args, **kwargs)
                ProjectLogger.success(module, resolved_operation, "执行成功", **context)
                return result
                
            except Exception as e:
                error_context = {
                    **context,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'traceback': inspect.trace()
                }
                ProjectLogger.fail(module, resolved_operation, str(e), **error_context)
                raise
        
        return wrapper
    return decorator


def async_service_operation(module: str, operation: Optional[str] = None, **default_context):
    """
    统一日志和异常处理装饰器（异步版本）
    
    Args:
        module: 模块名称
        operation: 操作名称（可选，为None时自动推导）
        **default_context: 默认上下文参数
    
    operation 参数自动推导规则：
        1. 显式传入的 operation 参数
        2. 函数的 description 属性
        3. 模块名.类名.函数名（如果有类）或模块名.函数名
    
    用法:
        @async_service_operation(module="MO推送", operation="创建生产加工单")
        async def create_mo(event_data, _aps, _erp):
            # 业务逻辑...
        
        # 或自动推导操作名称
        @async_service_operation(module="MO推送")
        async def create_mo(event_data, _aps, _erp):
            # 业务逻辑...
    
    自动记录:
        - 请求ID追踪
        - 操作开始/成功/失败日志
        - 异常类型和堆栈信息
    """
    def decorator(func):
        # 在装饰时确定 operation 值，避免每次调用都计算
        resolved_operation = _get_operation_name(operation, func)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request_id = generate_request_id()
            context = {"request_id": request_id, **default_context}
            
            # 提取关键字段作为上下文
            event_data = kwargs.get('event_data') or (args[1] if len(args) > 1 else None)
            if isinstance(event_data, dict):
                if 'supplyno' in event_data:
                    context['supplyno'] = event_data['supplyno']
                if 'demandno' in event_data:
                    context['demandno'] = event_data['demandno']
            
            ProjectLogger.debug(module, resolved_operation, "开始执行", **context)
            
            try:
                result = await func(*args, **kwargs)
                ProjectLogger.success(module, resolved_operation, "执行成功", **context)
                return result
                
            except Exception as e:
                error_context = {
                    **context,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'traceback': inspect.trace()
                }
                ProjectLogger.fail(module, resolved_operation, str(e), **error_context)
                raise
        
        return wrapper
    return decorator


def batch_service_operation(module: str, operation: Optional[str] = None, **default_context):
    """
    批量操作专用日志和异常处理装饰器（异步版本）
    
    适用于批量处理事件的场景，提供汇总统计日志。
    特别处理 asyncio.gather(return_exceptions=True) 返回的异常列表。
    
    Args:
        module: 模块名称
        operation: 操作名称（可选，为None时自动推导）
        **default_context: 默认上下文参数
    
    operation 参数自动推导规则：
        1. 显式传入的 operation 参数
        2. 函数的 description 属性
        3. 模块名.类名.函数名（如果有类）或模块名.函数名
    
    用法:
        @batch_service_operation(module="MO推送", operation="批量创建生产加工单")
        async def batch_create_mo(event_data_list, _erp):
            # 批量业务逻辑...
    
    自动记录:
        - 请求ID追踪
        - 批量大小统计
        - 操作开始/成功/失败日志
        - 异常汇总信息（支持 return_exceptions=True 的场景）
    """
    def decorator(func):
        # 在装饰时确定 operation 值，避免每次调用都计算
        resolved_operation = _get_operation_name(operation, func)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request_id = generate_request_id()
            
            # 提取批量数据列表
            event_data_list = kwargs.get('event_data_list') or kwargs.get('pr_data_list') or (args[1] if len(args) > 1 else None)
            batch_size = len(event_data_list) if isinstance(event_data_list, list) else 0
            
            context = {
                "request_id": request_id,
                "batch_size": batch_size,
                **default_context
            }
            
            if batch_size > 0 and isinstance(event_data_list, list) and event_data_list:
                first_item = event_data_list[0]
                if isinstance(first_item, dict):
                    if 'supplyno' in first_item:
                        context['first_supplyno'] = first_item['supplyno']
            
            ProjectLogger.debug(module, resolved_operation, f"开始批量执行，共 {batch_size} 条", **context)
            
            try:
                result = await func(*args, **kwargs)
                
                # 检查返回值中是否包含异常（处理 return_exceptions=True 的情况）
                if isinstance(result, list):
                    exceptions = [item for item in result if isinstance(item, Exception)]
                    if exceptions:
                        error_count = len(exceptions)
                        success_count = batch_size - error_count
                        error_context = {
                            **context,
                            'error_count': error_count,
                            'success_count': success_count,
                            'sample_errors': [str(e) for e in exceptions[:5]]  # 最多记录5个错误示例
                        }
                        
                        if error_count == batch_size:
                            ProjectLogger.fail(module, resolved_operation, f"全部 {error_count} 条记录执行失败", **error_context)
                        elif success_count == 0:
                            ProjectLogger.fail(module, resolved_operation, f"批量执行失败，无成功记录", **error_context)
                        else:
                            ProjectLogger.warning(module, resolved_operation, f"部分执行失败，成功 {success_count} 条，失败 {error_count} 条", **error_context)
                    else:
                        ProjectLogger.success(module, resolved_operation, f"批量执行完成，共 {batch_size} 条", **context)
                else:
                    ProjectLogger.success(module, resolved_operation, f"批量执行完成，共 {batch_size} 条", **context)
                
                return result
                
            except Exception as e:
                error_context = {
                    **context,
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'traceback': inspect.trace()
                }
                ProjectLogger.fail(module, resolved_operation, f"批量执行失败: {str(e)}", **error_context)
                raise
        
        return wrapper
    return decorator

