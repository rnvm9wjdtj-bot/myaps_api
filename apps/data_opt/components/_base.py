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

from enum import Enum
from typing import List, Dict, Optional, Literal, Callable, Union, Any, Type
from collections import defaultdict
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
from datetime import date, datetime
from pydantic import BaseModel as PydanticModel
import uuid
from dataclasses import dataclass, field


from core.settings import THIS_BASE_URL, MYAPS_MAIN_DB, MYAPS_DB_SET
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
from globalobjects import globalconst, logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv, ConstEnum as ce
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
        source: 数据源对象或数据源实例对象列表
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
    支持链式调用，如：tplus.mo(**{}).create()
    """
    from . import ApsPayloadSponsor, EventResultPoster
    
    _CREATE_ENDPOINT: str = None   # 创建接口路径
    _UPDATE_ENDPOINT: str = None   # 更新接口路径
    _DELETE_ENDPOINT: str = None   # 删除接口路径
    _APPROVE_ENDPOINT: str = None   # 审批接口路径
    _PUSH_PYDANTIC_MODEL: Type[PydanticModel] = None   # 推送数据的Pydantic模型
    
    def __init__(self, raw_data: dict, *args, **kwargs):
        self.raw_data = raw_data
        self.internal_data = None
        self.external_data = None
    

    async def create(
        self,
        _aps: ApsPayloadSponsor,
        _erp: EventResultPoster,
        pydantic_model: Type[PydanticModel] = None,

        *args,
        **kwargs,
    ):
        """
        创建凭证
        
        Raises:
            NotImplementedError: 子类必须实现create方法
        """
        raise NotImplementedError("子类必须实现create方法")
    

    async def update(self, _erp: EventResultPoster):
        """
        更新凭证
        
        Raises:
            NotImplementedError: 子类必须实现update方法
        """
        raise NotImplementedError("子类必须实现update方法")
    

    async def delete(self, _erp: EventResultPoster):
        """
        删除凭证
        
        Raises:
            NotImplementedError: 子类必须实现delete方法
        """
        raise NotImplementedError("子类必须实现delete方法")

    
    async def approve(self, _erp: EventResultPoster):
        """
        审批凭证
        
        Raises:
            NotImplementedError: 子类必须实现approve方法
        """
        raise NotImplementedError("子类必须实现approve方法")



class InternalData:
    """内部APS数据包装器"""

    def __init__(self, data: dict | List[dict], pydantic_model: Type[PydanticModel] = None):
        self._pydantic_model = pydantic_model
        self.data = data
        if isinstance(data, dict):
            self.data_list = [data]
        else:
            self.data_list = data


    def is_empty(self):
        """
        检查数据是否为空
        
        Returns:
            True: 数据为空
            False: 否则
        """
        return not self.data_list

    
    # def get(self, key: str, default=None):
    #     """
    #     获取数据列表第一条指定键的值
    #     """
    #     return self.data_list[0].get(key, default)


    # def gets(self, key: str, default=None):
    #     return [data.get(key, default) for data in self.data_list]
        

    async def dump(self, pydantic_model: Type[PydanticModel] = None) -> dict:
        """
        转换为外部数据格式，只转化数据列表第一条
        
        Args:
            pydantic_model: 转换模型
        """
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"
        if pydantic_model is None:
            pydantic_model = self._pydantic_model
        else:
            self._pydantic_model = pydantic_model

        return pydantic_model.model_dump(self.data_list[0])


    async def dumps(self, pydantic_model: Type[PydanticModel] = None) -> List[dict]:
        """
        转换为外部数据格式，转化数据列表所有数据
        
        Args:
            pydantic_model: 转换模型
        """
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"
        if pydantic_model is None:
            pydantic_model = self._pydantic_model
        else:
            self._pydantic_model = pydantic_model
        external_data_list = [pydantic_model.model_dump(data) for data in self.data_list]
        self.external_data_list = ExternalData(external_data_list, pydantic_model)
        return self.external_data_list



class ExternalData:
    """外部ERP数据包装器"""

    def __init__(self, data: dict | List[dict], pydantic_model: Type[PydanticModel] = None):
        """
        初始化数据对象
        
        Args:
            data: 初始数据
        """
        self._pydantic_model = pydantic_model
        self.data = data
        if isinstance(data, dict):
            self.data_list = [data]
        else:
            self.data_list = data
        

    def is_empty(self):
        """
        检查数据是否为空
        
        Returns:
            True: 数据为空
            False: 否则
        """
        return not self.data_list


    def first(self):
        """
        获取数据列表第一条数据
        
        Returns:
            dict: 第一条数据
        """
        return self.data_list[0]

    # def get(self, key: str, default=None):
    #     """
    #     获取数据列表第一条指定键的值
    #     """
    #     return self.data_list[0].get(key, default)


    # def gets(self, key: str, default=None):
    #     return [data.get(key, default) for data in self.data_list]


    async def load(self, pydantic_model: Type[PydanticModel] = None) -> dict:
        """
        转化为 APS 内部数据格式, 只转化数据列表第一条
        """
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"
        if pydantic_model is None:
            pydantic_model = self._pydantic_model
        else:
            self._pydantic_model = pydantic_model
        internal_data = pydantic_model.model_dump(self.data_list[0])
        return pydantic_model.model_validate(internal_data)



    async def loads(self, pydantic_model: Type[PydanticModel] = None) -> List[dict]:
        """
        转化为 APS 内部数据格式, 转化数据列表所有数据
        
        Args:
            pydantic_model: 外部数据模型
        """
        assert self._pydantic_model or pydantic_model, "未设置转换模型pydantic_model"
        if pydantic_model is None:
            pydantic_model = self._pydantic_model
        else:
            self._pydantic_model = pydantic_model
        internal_data_list = [pydantic_model.model_dump(data) for data in self.data_list]
        self.internal_data_list = InternalData(internal_data_list, pydantic_model)
        return self.internal_data_list
        
        