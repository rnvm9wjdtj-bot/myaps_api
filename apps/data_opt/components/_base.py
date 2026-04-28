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
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB

    _default_sync_qps: float = 10.0
    _default_sync_burst: int = 20
    _default_async_qps: float = 10.0
    _default_async_burst: int = 20

    _use_adaptive_rate_limiter: bool = True

    def __init__(self, sync_qps: float = None, sync_burst: int = None, async_qps: float = None, async_burst: int = None):
        self._sync_session = None
        self._async_session = None
        
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


    def _get_sync_session(self):
        """
        获取同步会话（复用会话对象，避免资源浪费）
        限流：每次获取会话前需要获取令牌
        """
        self._sync_rate_limiter.acquire(timeout=30.0)
        
        if self._sync_session is not None:
            try:
                if hasattr(self._sync_session, 'adapters'):
                    if 'http://' in self._sync_session.adapters and \
                       'https://' in self._sync_session.adapters:
                        return self._sync_session
                elif hasattr(self._sync_session, 'is_closed'):
                    if not self._sync_session.is_closed:
                        return self._sync_session
                else:
                    return self._sync_session
            except:
                pass
        
        from apps.data_opt.utils.common import get_session
        self._sync_session = get_session()
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
        获取异步会话（复用会话对象，避免资源浪费）
        限流：每次获取会话前需要获取令牌
        """
        await self._async_rate_limiter.acquire(timeout=30.0)
        
        if self._async_session is not None:
            try:
                if hasattr(self._async_session, '_client'):
                    transport = getattr(self._async_session._client, '_transport', None)
                    if transport and not getattr(transport, '_closed', False):
                        return self._async_session
                elif hasattr(self._async_session, 'is_closed'):
                    if not self._async_session.is_closed:
                        return self._async_session
                else:
                    return self._async_session
            except:
                pass
        
        self._async_session = await get_async_session()
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
    async def create(cls, event_data: dict, _aps, _erp, pydantic_model: Type[PydanticModel] = None):
        """
        创建凭证
        
        Raises:
            NotImplementedError: 子类必须实现create方法
        """
        raise NotImplementedError("子类必须实现create方法")


    @classmethod
    async def update(cls, event_data: dict, _erp):
        """
        更新凭证
        
        Raises:
            NotImplementedError: 子类必须实现update方法
        """
        raise NotImplementedError("子类必须实现update方法")
    

    @classmethod
    async def delete(cls, event_data: dict, _erp):
        """
        删除凭证
        
        Raises:
            NotImplementedError: 子类必须实现delete方法
        """
        raise NotImplementedError("子类必须实现delete方法")


    @classmethod
    async def approve(cls, event_data: dict, _erp):
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
        production_cache_items=None,
        pydantic_model: Type[PydanticModel] | Callable = None,
        remain_native_supplyno: bool = True,
    ):
        """
        批量创建生产加工单
        Args:
            event_data_list: 生产加工单数据列表
            _aps: ApsPayloadSponsor 实例
            pydantic_model: 生产加工单数据模型 或 能返回生产加工单数据模型的工厂函数，默认使用 cls._PUSH_PYDANTIC_MODEL
            production_cache_items: 生产缓存项
            remain_native_supplyno: 是否保留原生供应号
        Returns:
            None
        """
        from . import ApsPayloadSponsor, CacheItem
        
        if production_cache_items is None:
            production_cache_items = [CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL]

        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        await cls._CONNECTION.auth()

        supply_nos = [s['supplyno'] for s in event_data_list]
        await TSupply.filter(supplyno__in=supply_nos).update(memo=" 📤 正在推送...")
        _aps = ApsPayloadSponsor(production_cache_items=production_cache_items)
        await _aps.establish_production_cache(supplynos=supply_nos)

        if pydantic_model:
            if callable(pydantic_model):
                try:
                    pydantic_model = pydantic_model(_aps)
                except Exception as e:
                    pydantic_model = pydantic_model()
        else:
            pydantic_model = cls._PUSH_PYDANTIC_MODEL

        tasks = [
            cls.create(
                event_data=_,
                _aps=_aps,
                _erp=_erp,
                pydantic_model=pydantic_model,
                remain_native_supplyno=remain_native_supplyno
            )
            for _ in event_data_list
        ]
        await asyncio.gather(*tasks)
    


class RsVoucher(BaseVoucher):
    
    @classmethod
    async def create_batch(
        cls,
        event_data_list: list[dict],
        _erp,
        production_cache_items=None,
        pydantic_model: Type[PydanticModel] | Callable = None,
    ):
        """
        批量创建领料申请
        Args:
            event_data_list: 领料申请数据列表
            _aps: ApsPayloadSponsor 实例
            production_cache_items: 生产缓存项
            pydantic_model: 领料申请数据模型 或 能返回领料申请数据模型的工厂函数，默认使用 cls._PUSH_PYDANTIC_MODEL
        Returns:
            None
        """
        from . import ApsPayloadSponsor, CacheItem
        
        if production_cache_items is None:
            production_cache_items = [CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL]

        assert cls._CONNECTION, globalconst.StaticString.ASSERT_CONNECTION.value
        await cls._CONNECTION.auth()

        supply_nos = [s['supplyno'] for s in event_data_list]
        _aps = ApsPayloadSponsor(production_cache_items=production_cache_items)
        await _aps.establish_production_cache(supplynos=supply_nos)

        if pydantic_model:
            if callable(pydantic_model):
                try:
                    pydantic_model = pydantic_model(_aps)
                except Exception as e:
                    pydantic_model = pydantic_model()
        else:
            pydantic_model = cls._PUSH_PYDANTIC_MODEL

        tasks = [
            cls.create(
                event_data=event_data,
                _aps=_aps,
                _erp=_erp,
                pydantic_model=pydantic_model,
            )
            for event_data in event_data_list
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
    """外部ERP数据列表包装器"""

    def __init__(self, raw_data: List[dict], pydantic_model: Type[PydanticModel] = None):
        """
        初始化数据对象
        
        Args:
            raw_data: 初始数据
        """
        self._pydantic_model = pydantic_model
        self.raw_data = raw_data
        self._set = [ExternalData(raw_data=data, pydantic_model=pydantic_model) for data in self.raw_data]
        self._dumped_data = None
        

    def __getitem__(self, index: int):
        return self._set[index]


    @property
    def is_empty(self):
        return not self.raw_data


    async def dumps(self, pydantic_model: Type[PydanticModel] = None) -> List[dict]:
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"

        if pydantic_model:
            if self._dumped_data is None or pydantic_model is not self._pydantic_model:
                self._pydantic_model = pydantic_model
                self._dumped_data = [pydantic_model(**_).model_dump() for _ in self.raw_data]
        else:
            if self._dumped_data is None:
                self._dumped_data = [self._pydantic_model(**_).model_dump() for _ in self.raw_data]
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

