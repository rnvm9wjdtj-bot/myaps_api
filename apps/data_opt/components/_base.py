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


class BaseConnection(ABC):
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


    # @abstractmethod
    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        pass


    # @abstractmethod
    def pull_from_source(self, *args, **kwargs):
        """
        从目标系统获取数据
        """
        pass

    # @abstractmethod
    async def pull_from_source_async(self, *args, **kwargs):
        """
        异步从目标系统获取数据
        """
        pass

    # @abstractmethod
    def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass

    # @abstractmethod
    async def push_into_target_async(self, *args, **kwargs):
        """
        异步推送数据到目标系统
        """
        pass


class CacheItem(Enum):
    SUPPLY_MO = 'supply_mo'
    ORDER_WC = 'orderwc'
    DEMAND = 'demand'
    PEG = 'peg'
    MATERIAL = 'material'



MINI_PEG_SQL = """
    SELECT DISTINCT
        p.DemandNO AS DemandNo,
        s.SupplyNo AS S_SupplyNo
    FROM t_peg p
    LEFT JOIN t_demand d ON p.MaterialNo = d.MaterialNo 
        AND p.DemandNO = d.DemandNo 
        AND p.ItemNo = d.ItemNo
    LEFT JOIN t_supply s ON s.MaterialNo = p.MaterialNo 
        AND s.SupplyNo = p.S_SupplyNo 
        AND s.ItemNo = p.S_ItemNo
    INNER JOIN t_material m ON m.MaterialNo = p.MaterialNo
    -- 所有条件集中在这里
    WHERE {where_string}
    ORDER BY p.id, d.MaterialNo, d.Priority, s.Avail_Date, s.Avail_Qty;
"""



class _ProductionDataCache:
    """生产数据缓存管理器"""
    
    DEFAULT_WAIT_TIMEOUT: float = 30.0  # 等待队列超时时间（秒）
    DEFAULT_LOAD_TIMEOUT: float = 120.0  # 缓存加载超时时间（秒）
    SECONDS_PER_HOUR: int = 3600  # 每小时的秒数
    DEFAULT_CACHE_EXPIRY_HOURS: int = 24  # 缓存过期时间（小时）
    DEFAULT_PAGE_SIZE: int = 1000  # 数据库查询默认页大小
    DEFAULT_PAGE_INDEX: int = 0  # 数据库查询默认页索引
    FULL_LOAD_CONDITION: str = "1=1"  # 全量加载的 SQL 条件
    PEG_DEMAND_TO_SUPPLY_KEY: str = "demand_to_supply"  # PEG 缓存中需求到供应的映射键
    PEG_SUPPLY_TO_DEMAND_KEY: str = "supply_to_demand"  # PEG 缓存中供应到需求的映射键
    FILTER_SUPPLY_NO: str = "`SupplyNo`"  # 数据库查询中的 SupplyNo 字段过滤
    FILTER_DEMAND_NO: str = "`DemandNo`"  # 数据库查询中的 DemandNo 字段过滤
    
    def __init__(self):
        self._initialized = False
        self._is_loading = False
        self._load_lock = asyncio.Lock()
        
        self._wait_queue: List[asyncio.Future] = []
        self._wait_lock = asyncio.Lock()
        
        self._pending_supplynos: set = set()
        self._pending_lock = asyncio.Lock()
        
        self.WAIT_TIMEOUT = self.DEFAULT_WAIT_TIMEOUT
        self.LOAD_TIMEOUT = self.DEFAULT_LOAD_TIMEOUT
        
        # 加载完成信号（用于跨协程通知）
        self._loading_complete = asyncio.Event()
        self._loading_complete.set()
        
        # 缓存项配置，包含所有可能的缓存项，用于依赖关系解析，可由 _set_cache_items 方法覆盖
        self.CACHE_ITEMS = [
            CacheItem.SUPPLY_MO.value,
            CacheItem.ORDER_WC.value,
            CacheItem.DEMAND.value,
            CacheItem.PEG.value,
            CacheItem.MATERIAL.value,
        ]
        
        # 缓存项依赖关系（声明式配置）
        # 格式：{ CacheItem: [依赖项列表] }
        # 如果声明加载某项，但其依赖基础未在 CACHE_ITEMS 中，则自动补充
        self.CACHE_ITEM_DEPS = {
            CacheItem.DEMAND: [CacheItem.PEG],
            CacheItem.ORDER_WC: [CacheItem.SUPPLY_MO],
            CacheItem.PEG: [CacheItem.SUPPLY_MO],
            CacheItem.MATERIAL: [CacheItem.SUPPLY_MO, CacheItem.DEMAND],
        }
        
        # 强制加载的缓存项（即使未在 CACHE_ITEMS 中也会加载）
        self.CACHE_ITEMS_FORCE = [CacheItem.SUPPLY_MO.value]
        
        # 解析后的有效缓存项（运行时计算）
        self._effective_cache_items: List[str] = []
        
        # 缓存过期配置
        self.CACHE_EXPIRY_HOURS = self.DEFAULT_CACHE_EXPIRY_HOURS  # 缓存过期时间（小时）
        
        # 缓存数据
        self._cache: Dict[str, Dict[Any, Any]] = {
            CacheItem.SUPPLY_MO.value: {},
            CacheItem.ORDER_WC.value: {},
            CacheItem.DEMAND.value: {},
            CacheItem.PEG.value: {},
            CacheItem.MATERIAL.value: {}
        }
        
        # 缓存时间戳（记录每个缓存项的加载时间）
        self._cache_timestamps: Dict[str, float] = {
            CacheItem.SUPPLY_MO.value: 0.0,
            CacheItem.ORDER_WC.value: 0.0,
            CacheItem.DEMAND.value: 0.0,
            CacheItem.PEG.value: 0.0,
            CacheItem.MATERIAL.value: 0.0
        }
    
        # 统计信息
        self._stats = {
            'total_hits': 0,
            'total_misses': 0,
            'total_refreshes': 0,
            'cache_size': 0,
            'total_expired': 0
        }


    def _set_cache_items(self, cache_items: List[Union[str, 'CacheItem']]):
        """设置缓存项配置
        
        允许使用字符串或 CacheItem 枚举对象来指定缓存项。
        会自动处理依赖关系并更新有效缓存项列表。
        
        Args:
            cache_items: 缓存项列表，可以是字符串或 CacheItem 枚举对象
        """
        # 处理输入，确保所有项都是字符串
        processed_items = []
        for item in cache_items:
            if isinstance(item, CacheItem):
                processed_items.append(item.value)
            elif isinstance(item, str):
                # 验证字符串是否是有效的缓存项
                valid_values = [e.value for e in CacheItem]
                if item in valid_values:
                    processed_items.append(item)
                else:
                    logger.warning("生产数据缓存", "", f"忽略无效的缓存项: {item}")
        
        # 更新缓存项配置
        self.CACHE_ITEMS = processed_items
        
        # 重新解析依赖关系，更新有效缓存项
        self._resolve_cache_items()
        logger.info("生产数据缓存", "", f"已设置缓存项: {self.CACHE_ITEMS}")


    async def ensure_initialized(self):
        """异步方式确保缓存已初始化
        
        [注意] 全量加载已禁用，请使用 load_on_demand 方法按需加载数据
        
        Args:
            db_name: 数据库名称（此参数在当前实现中不再使用）
        """
        if self._initialized:
            return
        
        # [已修改] 全量加载已禁用，提示用户使用按需加载
        logger.warning(
            "生产数据缓存", 
            "", 
            "全量加载已禁用。请使用 cache.load_on_demand(db_name, supplynos=[...]) 按需加载指定工单数据"
        )
        # 不执行任何加载操作，等待用户显式调用 load_on_demand
        return
    
    def _resolve_cache_items(self) -> List[str]:
        """解析缓存项配置，处理依赖补充和强制加载项
        
        依赖补充规则：
        - 如果声明加载某项，但其依赖基础未在 CACHE_ITEMS 中，则自动补充
        - 强制加载项（supply_mo, orderwc, peg）始终加载
        - 支持多层依赖传递（如 demand -> peg -> supply_mo）
        
        Returns:
            解析后的有效缓存项列表
        """
        def resolve_deps(item: CacheItem, resolved: set):
            """递归解析依赖项"""
            for dep in self.CACHE_ITEM_DEPS.get(item, []):
                if dep not in resolved:
                    resolved.add(dep.value)
                    resolve_deps(dep, resolved)
        
        effective = set()
        
        for item in self.CACHE_ITEMS:
            effective.add(item if isinstance(item, str) else item.value)
        
        for item in self.CACHE_ITEMS_FORCE:
            effective.add(item if isinstance(item, str) else item.value)
        
        for item in list(effective):
            item_enum = CacheItem(item) if item in [e.value for e in CacheItem] else None
            if item_enum:
                resolve_deps(item_enum, effective)
        
        self._effective_cache_items = list(effective)
        return self._effective_cache_items
    
    async def _initialize_on_needed(self, db_name: str, supplynos: list):
        """按需加载缓存，只加载指定 supplyno 相关的数据
        
        加载顺序：
        1. supply_mo - 只加载指定的 supplyno 数据
        2. orderwc - 只加载与指定 supplyno 相关的工序数据
        3. peg - 只加载与指定 supplyno 相关的匹配关系，并收集 demandno
        4. demand - 只加载 peg 中收集到的 demandno 数据
        5. material - 全量加载（或根据需要优化）
        
        Args:
            db_name: 数据库名称
            supplynos: supplyno 列表，指定需要加载的数据
        """
        if not supplynos:
            logger.warning("生产数据缓存", "", "传入的 supplyno 列表为空，跳过按需加载")
            return
        
        try:
            effective_items = self._resolve_cache_items()
            logger.info("生产数据缓存", "", f"开始按需加载，共 {len(supplynos)} 个 supplyno，缓存项: {effective_items}")
            
            # 1. 加载 supply_mo 缓存（核心数据）- 必须加载
            logger.info("生产数据缓存", "", "开始构建 supply_mo 缓存（按需）...")
            await self._build_supply_mo_cache(db_name, supplynos=supplynos)
            logger.success("生产数据缓存", "", f"{CacheItem.SUPPLY_MO.value} 缓存加载: {len(self._cache[CacheItem.SUPPLY_MO.value])} 条")
            
            # 2. 加载 orderwc 缓存（子表，通过 supplyno 关联）- 必须加载
            logger.info("生产数据缓存", "", "开始构建 orderwc 缓存（按需）...")
            await self._build_orderwc_cache(db_name, supplynos=supplynos)
            total_orderwc = sum(len(items) for items in self._cache[CacheItem.ORDER_WC.value].values())
            logger.success("生产数据缓存", "", f"{CacheItem.ORDER_WC.value} 缓存加载: {total_orderwc} 条")
            
            # 3. 加载 peg 缓存（多对多关系），并收集 demandno - 必须加载
            logger.info("生产数据缓存", "", "开始构建 peg 缓存（按需）...")
            demand_nos = await self._build_peg_cache(db_name, supplynos=supplynos)
            logger.success("生产数据缓存", "", f"{CacheItem.PEG.value} 缓存加载: {len(self._cache[CacheItem.PEG.value]['demand_to_supply'])} 条 DemandNo")
            
            # 4. 加载 demand 缓存（根据 peg 中收集的 demandno + 全部 supplyno）
            if CacheItem.DEMAND.value in effective_items:
                logger.info("生产数据缓存", "", "开始构建 demand 缓存（按需）...")
                extended_demandnos = list(set(demand_nos + supplynos))
                await self._build_demand_cache(db_name, demandnos=extended_demandnos)
                logger.success("生产数据缓存", "", f"{CacheItem.DEMAND.value} 缓存加载: {len(self._cache[CacheItem.DEMAND.value])} 条")
            else:
                logger.info("生产数据缓存", "", "跳过 demand 缓存（未启用）")
            
            # 5. 加载 material 缓存（收集 supply_mo 和 demand 中的 materialno 并集）
            if CacheItem.MATERIAL.value in effective_items:
                material_nos_from_supply = {item.get('materialno') for item in self._cache[CacheItem.SUPPLY_MO.value].values() if item.get('materialno')}
                material_nos_from_demand = {subitem.get('materialno') for items in self._cache[CacheItem.DEMAND.value].values() for subitem in items if subitem.get('materialno')}
                material_nos = list(material_nos_from_supply | material_nos_from_demand)
                logger.info("生产数据缓存", "", f"开始构建 material 缓存（按需），共 {len(material_nos)} 个物料号）...")
                await self._build_material_cache(db_name, material_nos=material_nos)
                logger.success("生产数据缓存", "", f"{CacheItem.MATERIAL.value} 缓存加载: {len(self._cache[CacheItem.MATERIAL.value])} 条")
            else:
                logger.info("生产数据缓存", "", "跳过 material 缓存（未启用）")
            
            self._stats['total_refreshes'] += 1
            self._stats['cache_size'] = sum(
                len(v) for v in self._cache.values() if isinstance(v, dict)
            )
            logger.success("生产数据缓存", "", f"按需加载完成，共 {self._stats['cache_size']} 条数据")
                
        except Exception as e:
            logger.fail("生产数据缓存", "", f"按需加载失败: {e}")
            raise
    

    async def _build_cache(self, db_name: str, table_name: str, cache_name: str, cache_factory, process_item, filter_string: str = ''):
        """通用的缓存构建方法"""
        cache = cache_factory()
        
        try:
            # 直接从数据库获取数据，不分页，因为 db_query 已经处理了分页
            result: DbResult = await db_query(
                db_name=db_name,
                model_or_tablename=table_name,
                filter_string=filter_string,
                page_size=self.DEFAULT_PAGE_SIZE,
                page_index=self.DEFAULT_PAGE_INDEX
            )
            data_list = result.data
            
            for item in data_list:
                process_item(item, cache)
            
            self._cache[cache_name] = cache
            self._update_cache_timestamp(cache_name)  # 更新缓存时间戳
            return data_list
        except Exception as e:
            logger.fail("生产数据缓存", f"构建 {cache_name} 缓存", f"{e}")
            raise e
    

    async def _build_supply_mo_cache(self, db_name: str, supplynos: list = None):
        """使用数据库查询方式构建 supply_mo 缓存
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 的数据
        """
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no] = item
        
        # 构建过滤条件
        filter_string = ''
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            filter_string = f"`SupplyNo` IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_supply_mo",
            cache_name=CacheItem.SUPPLY_MO.value,
            cache_factory=dict,
            process_item=process_item,
            filter_string=filter_string
        )
    

    async def _build_orderwc_cache(self, db_name: str, supplynos: list = None):
        """使用数据库查询方式构建 orderwc 缓存（以 supplyno 为索引）
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 的数据
        """
        def process_item(item, cache):
            supply_no = item.get('supplyno', '')
            if supply_no:
                cache[supply_no].append(item)
        
        # 构建过滤条件
        filter_string = ''
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            filter_string = f"`SupplyNo` IN ({formatted_nos})"
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_orderwc",
            cache_name=CacheItem.ORDER_WC.value,
            cache_factory=lambda: defaultdict(list),
            process_item=process_item,
            filter_string=filter_string
        )
    

    async def _build_demand_cache(self, db_name: str, demandnos: list = None):
        """使用数据库查询方式构建 demand 缓存
        
        Args:
            db_name: 数据库名称
            demandnos: 可选，demandno 列表，如果提供则只加载这些 demandno 的数据
        """
        def process_item(item, cache):
            demand_no = item.get('demandno', '')
            if demand_no:
                cache[demand_no].append(item)
        
        # 构建过滤条件
        filter_string = ''
        if demandnos:
            formatted_nos = ','.join([f"'{d}'" for d in demandnos])
            filter_string = f"`DemandNo` IN ({formatted_nos})"
        else:
            # 如果没有指定 demandnos，跳过查询，避免全量查询
            logger.info("生产数据缓存", "", "没有指定 demandnos，跳过 demand 缓存构建")
            self._cache[CacheItem.DEMAND.value] = defaultdict(list)
            return
        
        await self._build_cache(
            db_name=db_name,
            table_name="v_demand",
            cache_name=CacheItem.DEMAND.value,
            cache_factory=lambda: defaultdict(list),
            process_item=process_item,
            filter_string=filter_string
        )


    async def _build_peg_cache(self, db_name: str, supplynos: list = None):
        """使用直接 SQL 方式构建 peg 缓存（双向索引），加快构建速度
        
        Args:
            db_name: 数据库名称
            supplynos: 可选，supplyno 列表，如果提供则只加载这些 supplyno 相关的 peg 数据
            
        Returns:
            list: 收集到的所有 demandno 列表
        """

        demand_nos = set()
        
        # 构建 peg 缓存结构
        peg_cache = {
            self.PEG_DEMAND_TO_SUPPLY_KEY: defaultdict(list),
            self.PEG_SUPPLY_TO_DEMAND_KEY: defaultdict(list)
        }
        
        # 构建 WHERE 子句
        if supplynos:
            formatted_nos = ','.join([f"'{s}'" for s in supplynos])
            where_string = f"s.SupplyNo IN ({formatted_nos})"
        else:
            where_string = "1=1"  # 全量获取
        
        # 填充 SQL 语句
        sql = MINI_PEG_SQL.format(where_string=where_string)
        
        # 执行 SQL 查询
        try:
            logger.info("生产数据缓存", "", f"开始执行 PEG SQL 查询，{'全量' if not supplynos else f'按需({len(supplynos)}个)'}模式")
            result: DbResult = await db_exec_sql(
                db_name=db_name,
                sql=sql,
                description="构建 PEG 缓存"
            )
            
            # 处理查询结果
            data_list = result.data
            
            # 处理查询结果
            for item in data_list:
                demand_no = item.get('demandno', '')
                s_supply_no = item.get('s_supplyno', '')
                
                if demand_no and s_supply_no:
                    # 收集 demandno
                    demand_nos.add(demand_no)
                    
                    # 构建双向索引
                    if s_supply_no not in peg_cache[self.PEG_DEMAND_TO_SUPPLY_KEY][demand_no]:
                        peg_cache[self.PEG_DEMAND_TO_SUPPLY_KEY][demand_no].append(s_supply_no)
                    if demand_no not in peg_cache[self.PEG_SUPPLY_TO_DEMAND_KEY][s_supply_no]:
                        peg_cache[self.PEG_SUPPLY_TO_DEMAND_KEY][s_supply_no].append(demand_no)
            
            # 更新缓存
            self._cache[CacheItem.PEG.value] = peg_cache
            self._update_cache_timestamp(CacheItem.PEG.value)  # 更新缓存时间戳
            logger.success("生产数据缓存", "", f"PEG 缓存加载: {len(peg_cache[self.PEG_DEMAND_TO_SUPPLY_KEY])} 条 DemandNo")
            
        except Exception as e:
            logger.fail("生产数据缓存", "", f"PEG 缓存构建失败: {e}")
            raise e
        
        return list(demand_nos)
    

    async def _build_material_cache(self, db_name: str, material_nos: list = None):
        """使用数据库查询方式构建 material 缓存
        
        Args:
            db_name: 数据库名称
            material_nos: 可选，materialno 列表，如果提供则只加载这些物料号的数据
        """
        def process_item(item, cache):
            material_no = item.get('materialno', '')
            if material_no:
                cache[material_no] = item
        
        filter_string = ''
        if material_nos:
            formatted_nos = ','.join([f"'{m}'" for m in material_nos])
            filter_string = f"`MaterialNo` IN ({formatted_nos})"
        else:
            # 如果没有指定 material_nos，跳过查询，避免全量查询
            logger.info("生产数据缓存", "", "没有指定 material_nos，跳过 material 缓存构建")
            self._cache[CacheItem.MATERIAL.value] = {}
            return
        
        await self._build_cache(
            db_name=db_name,
            table_name="t_material",
            cache_name=CacheItem.MATERIAL.value,
            cache_factory=dict,
            process_item=process_item,
            filter_string=filter_string
        )


    async def _wait_for_loading(self, timeout: float = None) -> bool:
        """等待缓存加载完成
        
        Args:
            timeout: 等待超时时间（秒），默认使用 self.WAIT_TIMEOUT
            
        Returns:
            bool: True 表示等待成功（加载完成），False 表示超时
        """
        if timeout is None:
            timeout = self.WAIT_TIMEOUT
        
        try:
            await asyncio.wait_for(self._loading_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning("生产数据缓存", "", f"等待缓存加载超时（{timeout}秒）")
            return False


    async def _merge_pending_supplynos(self, new_supplynos: list) -> list:
        """合并待加载的 supplynos
        
        Args:
            new_supplynos: 新的 supplyno 列表
            
        Returns:
            list: 合并后的完整 supplyno 列表
        """
        async with self._pending_lock:
            self._pending_supplynos.update(new_supplynos)
            return list(self._pending_supplynos.copy())


    def _clear_pending_supplynos(self):
        """清除待加载的 supplynos"""
        self._pending_supplynos.clear()
    
    def _is_cache_expired(self, cache_name: str) -> bool:
        """检查缓存是否过期
        
        Args:
            cache_name: 缓存项名称
            
        Returns:
            bool: True 表示缓存已过期，False 表示缓存有效
        """
        import time
        current_time = time.time()
        cache_time = self._cache_timestamps.get(cache_name, 0.0)
        expiry_seconds = self.CACHE_EXPIRY_HOURS * self.SECONDS_PER_HOUR
        
        if cache_time == 0:
            return True  # 未加载过，视为过期
        
        if current_time - cache_time > expiry_seconds:
            return True  # 已过期
        
        return False  # 未过期
    
    def _update_cache_timestamp(self, cache_name: str):
        """更新缓存时间戳
        
        Args:
            cache_name: 缓存项名称
        """
        import time
        self._cache_timestamps[cache_name] = time.time()
    
    def _clear_expired_cache(self):
        """清理过期的缓存
        
        Returns:
            int: 清理的缓存项数量
        """
        import time
        expired_count = 0
        current_time = time.time()
        expiry_seconds = self.CACHE_EXPIRY_HOURS * self.SECONDS_PER_HOUR
        
        for cache_name in self._cache:
            cache_time = self._cache_timestamps.get(cache_name, 0.0)
            if cache_time > 0 and current_time - cache_time > expiry_seconds:
                # 清理过期缓存
                self._cache[cache_name].clear()
                self._cache_timestamps[cache_name] = 0.0
                expired_count += 1
                self._stats['total_expired'] += 1
                logger.info("生产数据缓存", "", f"清理过期缓存: {cache_name}")
        
        return expired_count


    async def establish_production_cache(self, supplynos: list, db_name: str = MYAPS_MAIN_DB, cache_items: List[Union[str, CacheItem]] = None):
        """PL 状态变更事件处理
        
        重新构建缓存：丢弃旧缓存，按需加载全新缓存。
        支持多批次并发时的等待机制和增量合并。
        
        Args:
            db_name: 数据库名称
            supplynos: supplyno 列表，指定需要加载的数据
            cache_items: 可选，指定需要加载的缓存项，若为None则加载所有缓存项
        """
        if not supplynos:
            logger.warning("生产数据缓存", "", "传入的 supplyno 列表为空，跳过按需加载")
            return

        # 设置缓存项，根据传入的 cache_items 覆盖默认配置
        if cache_items:
            self._set_cache_items(cache_items)
        
        async with self._load_lock:
            if self._is_loading:
                logger.info("生产数据缓存", "", f"缓存正在加载中（{len(supplynos)}个supplyno等待中）...")
                wait_success = await self._wait_for_loading()
                
                if not wait_success:
                    logger.warning("生产数据缓存", "", "等待缓存加载超时")
                    # 超时后，检查是否真的初始化完成
                    if not self._initialized:
                        logger.warning("生产数据缓存", "", "缓存加载未完成，需要重新加载")
                    else:
                        logger.info("生产数据缓存", "", "缓存已就绪，无需重新加载")
                        return
                else:
                    logger.info("生产数据缓存", "", "等待的缓存加载已完成")
                
                if self._initialized:
                    logger.info("生产数据缓存", "", "缓存已就绪，无需重新加载")
                    return
            
            merged_supplynos = await self._merge_pending_supplynos(supplynos)
            all_supplynos = list(set(merged_supplynos) | set(supplynos))
            
            logger.info("生产数据缓存", "", f"开始按需加载 {len(all_supplynos)} 个 supplyno 的数据...")
            self._is_loading = True
            self._loading_complete.clear()
            
            try:
                await asyncio.wait_for(
                    self._initialize_on_needed(db_name, all_supplynos),
                    timeout=self.LOAD_TIMEOUT
                )
                self._initialized = True
                self._clear_pending_supplynos()
                logger.success("生产数据缓存", "", f"按需加载完成，共 {len(all_supplynos)} 个 supplyno")
                
            except asyncio.TimeoutError:
                logger.fail("生产数据缓存", "", f"按需加载超时（{self.LOAD_TIMEOUT}秒）")
                self._is_loading = False
                self._loading_complete.set()
                self._initialized = False
                raise
            except Exception as e:
                logger.fail("生产数据缓存", "", f"按需加载失败: {e}")
                self._loading_complete.set()
                raise
            finally:
                if self._is_loading:
                    self._is_loading = False
                    self._loading_complete.set()


    def get_supply_mo(self, supply_no: str) -> Dict:
        """获取工单数据（按供应号查找）"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.SUPPLY_MO.value):
            self._stats['total_misses'] += 1
            return {}
        
        data = self._cache[CacheItem.SUPPLY_MO.value].get(supply_no)
        if data:
            self._stats['total_hits'] += 1
            return data
        
        self._stats['total_misses'] += 1
        return {}
    

    def batch_get_supply_mo(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工单数据"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.SUPPLY_MO.value):
            for _ in supplynos:
                self._stats['total_misses'] += 1
            return []
        
        results = []
        for supply_no in supplynos:
            data = self._cache[CacheItem.SUPPLY_MO.value].get(supply_no)
            if data:
                results.append(data)
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_orderwc(self, supply_no: str) -> List[Dict]:
        """获取工序数据（按供应号查找）"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.ORDER_WC.value):
            self._stats['total_misses'] += 1
            return []
        
        data = self._cache[CacheItem.ORDER_WC.value].get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_orderwc(self, supplynos: List[str]) -> List[Dict]:
        """批量获取工序数据（按供应号查找）"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.ORDER_WC.value):
            for _ in supplynos:
                self._stats['total_misses'] += 1
            return []
        
        results = []
        for supply_no in supplynos:
            data_list = self._cache[CacheItem.ORDER_WC.value].get(supply_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_demand(self, demand_no: str) -> List[Dict]:
        """获取需求数据"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.DEMAND.value):
            self._stats['total_misses'] += 1
            return []
        
        data = self._cache[CacheItem.DEMAND.value].get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_demand(self, demandnos: List[str]) -> List[Dict]:
        """批量获取需求数据"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.DEMAND.value):
            for _ in demandnos:
                self._stats['total_misses'] += 1
            return []
        
        results = []
        for demand_no in demandnos:
            data_list = self._cache[CacheItem.DEMAND.value].get(demand_no, [])
            results.extend(data_list)
            if data_list:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_peg_by_demand(self, demand_no: str) -> List[str]:
        """根据 DemandNo 获取对应的 S_SupplyNo 列表"""
        if self._is_cache_expired(CacheItem.PEG.value):
            self._stats['total_misses'] += 1
            return []
        
        cache = self._cache[CacheItem.PEG.value][self.PEG_DEMAND_TO_SUPPLY_KEY]
        data = cache.get(demand_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def get_peg_by_supply(self, supply_no: str) -> List[str]:
        """根据 S_SupplyNo 获取对应的 DemandNo 列表"""
        if self._is_cache_expired(CacheItem.PEG.value):
            self._stats['total_misses'] += 1
            return []
        
        cache = self._cache[CacheItem.PEG.value][self.PEG_SUPPLY_TO_DEMAND_KEY]
        data = cache.get(supply_no, [])
        if data:
            self._stats['total_hits'] += 1
        else:
            self._stats['total_misses'] += 1
        return data
    

    def batch_get_peg_by_demand(self, demandnos: List[str]) -> Dict[str, List[str]]:
        """批量根据 DemandNo 获取 S_SupplyNo 列表"""
        if self._is_cache_expired(CacheItem.PEG.value):
            results = {}
            for demand_no in demandnos:
                results[demand_no] = []
                self._stats['total_misses'] += 1
            return results
        
        cache = self._cache[CacheItem.PEG.value][self.PEG_DEMAND_TO_SUPPLY_KEY]
        results = {}
        for demand_no in demandnos:
            data = cache.get(demand_no, [])
            results[demand_no] = data
            if data:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def batch_get_peg_by_supply(self, supplynos: List[str]) -> Dict[str, List[str]]:
        """批量根据 S_SupplyNo 获取 DemandNo 列表"""
        if self._is_cache_expired(CacheItem.PEG.value):
            results = {}
            for supply_no in supplynos:
                results[supply_no] = []
                self._stats['total_misses'] += 1
            return results
        
        cache = self._cache[CacheItem.PEG.value][self.PEG_SUPPLY_TO_DEMAND_KEY]
        results = {}
        for supply_no in supplynos:
            data = cache.get(supply_no, [])
            results[supply_no] = data
            if data:
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_material(self, material_no: str) -> List[Dict]:
        """获取物料数据"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.MATERIAL.value):
            self._stats['total_misses'] += 1
            return []
        
        data = self._cache[CacheItem.MATERIAL.value].get(material_no)
        if data:
            self._stats['total_hits'] += 1
            return [data]
        
        self._stats['total_misses'] += 1
        return []
    

    def batch_get_material(self, materialnos: List[str]) -> List[Dict]:
        """批量获取物料数据"""
        # 检查缓存是否过期
        if self._is_cache_expired(CacheItem.MATERIAL.value):
            for _ in materialnos:
                self._stats['total_misses'] += 1
            return []
        
        results = []
        for material_no in materialnos:
            data = self._cache[CacheItem.MATERIAL.value].get(material_no)
            if data:
                results.append(data)
                self._stats['total_hits'] += 1
            else:
                self._stats['total_misses'] += 1
        return results
    

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        # 计算当前缓存大小
        self._stats['cache_size'] = sum(
            len(v) for v in self._cache.values() if isinstance(v, dict)
        )
        # 添加详细的缓存大小信息
        return {
            **self._stats,
            'cache_sizes': {
                CacheItem.SUPPLY_MO.value: len(self._cache[CacheItem.SUPPLY_MO.value]),
                CacheItem.ORDER_WC.value: len(self._cache[CacheItem.ORDER_WC.value]),
                CacheItem.DEMAND.value: len(self._cache[CacheItem.DEMAND.value]),
                CacheItem.PEG.value: len(self._cache[CacheItem.PEG.value].get(self.PEG_DEMAND_TO_SUPPLY_KEY, {})),
                CacheItem.MATERIAL.value: len(self._cache[CacheItem.MATERIAL.value])
            },
            'expiry_hours': self.CACHE_EXPIRY_HOURS,
            'cache_timestamps': self._cache_timestamps
        }



def async_aps_error_handler(operation_name: str):
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            target_obj = args[0] if args else "未知"
            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                logger.fail(operation_name, target_obj, f"{operation_name}时发生错误：{e}")
                raise
        return wrapper
    return decorator


class ApsPayloadSponsor:
    def __init__(self, production_cache_items: List[CacheItem] = None):
        """
        初始化APS数据存储类
        
        Args:
            production_cache_items: 要缓存的生产数据项，默认所有项
        """
        self._is_closed = False

        self._production_cache = _ProductionDataCache()
        if production_cache_items:
            self._production_cache._set_cache_items(cache_items=production_cache_items)
        
        # 导入必要的模块
        from apps.data_opt.utils.common import get_session
        from concurrent.futures import ThreadPoolExecutor
        
        # 创建标准的 requests 会话（避免 httpx 可能的事件循环冲突）
        self._http_session_sync = get_session(
            retries=3,
            pool_connections=50,
            pool_maxsize=100,
            connect_timeout=5.0,
            read_timeout=15.0,
            enable_monitor=False  # 禁用监控包装器，避免可能的冲突
        )
        
        # 创建线程池
        import os
        cpu_count = os.cpu_count() or 4
        max_workers = min(cpu_count * 5, 50)  # 最多50个线程
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        """关闭并释放资源"""
        if self._is_closed:
            return
        
        self._is_closed = True
        
        if hasattr(self, '_http_session_sync') and self._http_session_sync:
            try:
                self._http_session_sync.close()
            except Exception:
                pass
        
        if hasattr(self, '_executor') and self._executor:
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


    @async_aps_error_handler("建立生产缓存")
    async def establish_production_cache(self, supplynos: List[str]) -> _ProductionDataCache:
        """
        建立生产缓存
        
        Args:
            supplynos: S_SupplyNo 列表
        """
        await self._production_cache.establish_production_cache(supplynos=supplynos)
        return self._production_cache


    @classmethod
    async def _call_api(cls, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """
        异步通用 API 调用方法，包含错误处理、超时设置和重试机制
        
        Args:
            method: HTTP 方法，如 'GET', 'POST', 'PATCH', 'PUT'
            url: API 地址
            **kwargs: 其他参数，如 json, timeout 等
        
        Returns:
            API 返回的 JSON 数据
        
        Raises:
            Exception: API 调用失败
        """
        from apps.data_opt.utils.common import get_async_session
        
        max_retries = 3
        retry_count = 0
        timeout = kwargs.pop('timeout', (30, 60))
        
        while retry_count < max_retries:
            # 每次重试都获取新的异步会话
            async_session = await get_async_session()
            
            try:
                # 直接使用原始的 httpx.AsyncClient 方法
                if hasattr(async_session, 'client') and hasattr(async_session.client, 'request'):
                    # 使用包装的客户端
                    response = await async_session.client.request(method, url, timeout=timeout, **kwargs)
                elif hasattr(async_session, 'request'):
                    # 使用直接的客户端
                    response = await async_session.request(method, url, timeout=timeout, **kwargs)
                else:
                    # 尝试使用 get_async 等方法
                    # 获取对应的异步方法
                    if method.upper() == 'GET':
                        method_func = getattr(async_session, 'get_async', None)
                    elif method.upper() == 'POST':
                        method_func = getattr(async_session, 'post_async', None)
                    elif method.upper() == 'PATCH':
                        method_func = getattr(async_session, 'patch_async', None)
                    elif method.upper() == 'PUT':
                        method_func = getattr(async_session, 'put_async', None)
                    elif method.upper() == 'DELETE':
                        method_func = getattr(async_session, 'delete_async', None)
                    else:
                        raise ValueError(f"不支持的 HTTP 方法: {method}")
                    
                    # 检查方法是否存在且可调用
                    if not method_func:
                        raise Exception(f"异步会话没有 {method.upper()}_async 方法")
                    if not callable(method_func):
                        raise Exception(f"{method.upper()}_async 不是可调用对象，类型: {type(method_func)}")
                    
                    # 调用方法获取响应
                    response = await method_func(url, timeout=timeout, **kwargs)
                
                # 检查 HTTP 状态码
                if hasattr(response, 'raise_for_status'):
                    response.raise_for_status()
                elif hasattr(response, 'status_code') and response.status_code >= 400:
                    raise Exception(f"HTTP 错误: {response.status_code}")
                
                # 获取响应数据
                # 检查 response 是否是字符串
                if isinstance(response, str):
                    # 如果是字符串，尝试解析为 JSON
                    try:
                        return json.loads(response)
                    except json.JSONDecodeError:
                        raise Exception(f"响应是字符串但不是有效的 JSON: {response}")
                
                # 检查 response 是否是 None
                if response is None:
                    raise Exception("响应对象为 None")
                
                # 检查 response 是否有 json 方法
                if hasattr(response, 'json'):
                    if callable(response.json):
                        if inspect.iscoroutinefunction(response.json):
                            return await response.json()
                        else:
                            return response.json()
                    else:
                        # 如果 json 不是可调用对象，尝试直接返回它
                        return response.json
                # 检查 response 是否有 text 方法
                elif hasattr(response, 'text'):
                    if callable(response.text):
                        text = await response.text() if inspect.iscoroutinefunction(response.text) else response.text()
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError:
                            raise Exception(f"响应文本不是有效的 JSON: {text}")
                    else:
                        # 如果 text 不是可调用对象，尝试直接返回它
                        try:
                            return json.loads(response.text)
                        except json.JSONDecodeError:
                            raise Exception(f"响应文本不是有效的 JSON: {response.text}")
                # 检查 response 是否是字典
                elif isinstance(response, dict):
                    return response
                # 检查 response 是否是列表
                elif isinstance(response, list):
                    return response
                else:
                    raise Exception(f"无法获取响应数据，响应类型: {type(response)}")
                    
            except (Exception) as e:
                retry_count += 1
                logger.warning(f"API 调用失败，第{retry_count}次重试: {str(e)}")
                if retry_count >= max_retries:
                    logger.fail("API 调用", url, str(e))
                    raise
                await asyncio.sleep(1 * retry_count)  # 指数退避策略
            finally:
                # 关闭异步会话
                if hasattr(async_session, 'aclose'):
                    await async_session.aclose()
                elif hasattr(async_session, 'close'):
                    async_session.close()
        
        # 理论上不会走到这里
        raise Exception("API 调用失败：达到最大重试次数")


    @classmethod
    async def mto_workreport_to_virtual_stock(cls, db_name:str=MYAPS_MAIN_DB):
        """
        异步将报工数据 转化为 虚拟库存 数据，只处理MTO报工
        🅰 db: 账套名称，默认MYAPS_MAIN_DB
        """
        try:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            response_json: DbResult = await db_query(db_name=db_name, model_or_tablename="v_supply_complete")
            mo_complete_data = response_json.data
            df_mto_vir_st = None
            if mo_complete_data:
                df_mo_complete = pd.DataFrame(mo_complete_data)
                df_mto_vir_st = (df_mo_complete[df_mo_complete['category'] == 'MTO']
                        [['materialno', 'vendorno', 'finalopqty', 'category', 'avail_date']]
                        .groupby('vendorno', as_index=False)
                        .agg({
                            'finalopqty': 'sum',
                            'materialno': 'first',
                            'category': 'first',
                            'avail_date': 'first',
                        }))
                df_mto_vir_st['supplyno'] = df_mto_vir_st['materialno'] + '-' + df_mto_vir_st['vendorno']
                df_mto_vir_st['type'] = 'ST'
                df_mto_vir_st['priority'] = 0
                df_mto_vir_st['status'] = 'NEW'
                df_mto_vir_st['dt_req'] = df_mto_vir_st['avail_date']
                df_mto_vir_st['create_date'] = now
                df_mto_vir_st['itemno'] = pdv.ITEMNO
                df_mto_vir_st.rename(columns={'finalopqty': 'avail_qty'}, inplace=True)
            return df_mto_vir_st
        except Exception as e:
            logger.fail("MTO报工转虚拟库存", "", f"{e}")
            raise e


    @classmethod
    async def refresh_supply(cls, supply_data:Union[List[Dict[str, Any]], pd.DataFrame], type_:Literal['ST', 'PO']='ST', dbs:str=MYAPS_DB_SET):
        try:
            from apps.io_api.schemas import AcceptSupply

            if isinstance(supply_data, pd.DataFrame):
                supply_data = supply_data.to_dict('records')
            supply_data = [AcceptSupply(**item).model_dump(exclude_none=True) for item in supply_data]
            
            # 首先删除该类型的所有供应记录
            delete_result: MultiDbResult = await db_delete(db_names=dbs, model_or_tablename="t_supply", filter_string=f"`Type`='{type_}'")
            
            # 然后新增这些供应记录
            if supply_data:
                create_result: MultiDbResult = await db_bupsert(db_names=dbs, model_or_tablename="t_supply", data_list=supply_data)
                if create_result.success:
                    logger.success("刷新供应数据", f"type_{type_}", f"账套{dbs}")
                else:
                    logger.fail("刷新供应数据", f"type_{type_}", create_result.message)
            else:
                if delete_result.success:
                    logger.success("刷新供应数据", f"type_{type_}", f"账套{dbs}")
                else:
                    logger.fail("刷新供应数据", f"type_{type_}", delete_result.message)
        except Exception as e:
            logger.fail("刷新供应数据", f"type_{type_}", f"{e}")
            raise e


    @classmethod
    async def confirm_workreport(cls, db_name:str=MYAPS_MAIN_DB):
        """
        异步确认 工作报工 数据
        🅰 workreport_data: 工作报工数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        """
        try:
            logger.start("确认报工记录任务")
            response_json: MultiDbResult = await call_dbprocdure(db_names=db_name, procedure_name="UpdateConfirmQtyToOrderWC")
            logger.success("确认报工记录任务")
            return response_json
        except Exception as e:
            logger.fail("确认报工记录任务", "", f"{e}")
            raise e


    @classmethod
    async def get_new_pr_data(cls):
        try:
            result: DbResult = await db_query(
                db_name=MYAPS_MAIN_DB,
                model_or_tablename="v_supply",
                filter_string="`Type`='PR' AND `Status`='NEW'"
            )
            return result.data
        except Exception as e:
            logger.fail("获取新PR数据", "", f"{e}")
            return []


    @classmethod
    async def aggregate_pr_data(cls, pr_data_list: list[dict]=None, group_by: list=['materialno', 'avail_date', 'vendorno']) -> list[dict]:
        """
        聚合 PR avail_qty 字段
        Args:
            pr_data_list: PR 数据列表，若为None则查询主账套中状态为 NEW 的 PR 数据
            group_by: 分组字段，默认['materialno', 'avail_date', 'vendorno']
        Returns:
            聚合后的 PR 数据列表
        """
        import pandas as pd

        if not pr_data_list:
            pr_data_list = await cls.get_new_pr_data()
            if not pr_data_list:
                return []

        pr_datetime_fields = ('avail_date', 'create_date', 'avail_end_date', 'sys_date', 'sys_stamp')

        df = pd.DataFrame(pr_data_list)
        
        keep_cols = ['materialno', 'category', 'avail_qty', 'create_date', 'avail_date', 'vendorno']
        df = df[[col for col in keep_cols if col in df.columns]]
        
        for field in group_by:
            if field in pr_datetime_fields and field in df.columns:
                df[field] = pd.to_datetime(df[field], errors='coerce').dt.date
        
        agg_dict = {'avail_qty': 'sum'}
        other_cols = [col for col in df.columns if col not in group_by and col != 'avail_qty']
        for col in other_cols:
            agg_dict[col] = 'last'
        
        result_df = df.groupby(group_by, dropna=False).agg(agg_dict).reset_index()
        
        result_df = result_df.replace({pd.NA: None, pd.NaT: None, float('nan'): None})
        
        return result_df.to_dict('records')


    @classmethod
    async def get_dategrouped_pr(cls, db_name: str=None, period: int|str=30, groupdates: Optional[str]=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认MYAPS_MAIN_DB
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        db_name = db_name or MYAPS_MAIN_DB
        url = f"{THIS_BASE_URL}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}"
        response_json = await cls._call_api('GET', url)
        data = response_json.get('data', [])
        field_map = field_map or {
            'materialno': '料号',
            'datestr': '交期',
            'groupdate': '日期',
            'qty': '数量',
        }
        if not field_map:
            return data
        # 转换数据，确保所有日期对象都被转换为字符串
        result = []
        for item in data:
            mapped_item = {}
            for k, v in item.items():
                # 转换日期对象为字符串
                if isinstance(v, (date, datetime)):
                    v = str(v)
                mapped_item[field_map.get(k, k)] = v
            result.append(mapped_item)
        return result


    def _process_materialnos_and_get_cache(self, materialnos: str | list[str]) -> tuple[list, list, list]:
        """
        处理物料编号参数并从缓存获取数据
        Args:
            materialnos: 物料编号（多个用半角逗号分隔）或物料编号列表
        Returns:
            (material_list, cached_data, missing_materials)
        """
        if isinstance(materialnos, list):
            material_list = [m.strip() for m in materialnos if m.strip()]
        else:
            material_list = [m.strip() for m in materialnos.split(',') if m.strip()]
        
        if not material_list:
            return [], [], []

        # 批量从缓存获取
        cached_data = self._production_cache.batch_get_material(material_list)
        
        # 检查缓存命中情况
        cached_keys = {item['materialno'] for item in cached_data}
        missing_materials = [m for m in material_list if m not in cached_keys]
        
        return material_list, cached_data, missing_materials

    @async_aps_error_handler("查询物料信息")
    async def query_material(self, materialnos: str | list[str]) -> list:
        """
        异步查询物料信息（优先从缓存获取，缓存未命中则访问数据库并加入缓存）
        Args:
            materialnos: 物料编号（多个用半角逗号分隔）或物料编号列表
        Returns:
            物料信息列表
        """
        material_list, cached_data, missing_materials = self._process_materialnos_and_get_cache(materialnos)
        
        if not material_list:
            return []
        
        if missing_materials:
            materialnos_str = ','.join([f"'{m}'" for m in missing_materials])
            filter_string = f"`MaterialNo` IN ({materialnos_str})"
            response_json: DbResult = await db_query(
                db_name=MYAPS_MAIN_DB,
                model_or_tablename="t_material",
                select="MaterialNo, Free1, Free2, Free3",
                filter_string=filter_string
            )
            api_data = response_json.get('data', [])
            
            # 补充缓存
            for item in api_data:
                material_no = item.get('materialno', '')
                if material_no:
                    self._production_cache._cache[CacheItem.MATERIAL.value][material_no] = item
            
            # 合并结果
            cached_data.extend(api_data)
        
        return cached_data


    def _fetch_materials_http(self, missing_materials):
        """
        通过 HTTP API 获取物料信息
        Args:
            missing_materials: 缺失的物料编号列表
        Returns:
            物料信息列表
        """
        materialnos_str = ','.join(missing_materials)
        api_url = f"{THIS_BASE_URL}/api/t_material/{materialnos_str}?db_name={MYAPS_MAIN_DB}"

        try:
            response = self._http_session_sync.get(api_url, timeout=(5, 15))
            response.raise_for_status()
            response_json = response.json()
            return response_json.get('data', [])
        except Exception as e:
            error_msg = f"查询物料信息时发生HTTP请求错误：{str(e)}"
            logger.fail("查询物料信息", ','.join(missing_materials), error_msg)
            return []


    def query_material_sync(self, materialnos: str | list[str]) -> list:
        """
        同步查询物料信息（优先从缓存获取，缓存未命中则通过HTTP API获取并加入缓存）
        Args:
            materialnos: 物料编号（多个用半角逗号分隔）或物料编号列表
        Returns:
            物料信息列表
        """
        material_list, cached_data, missing_materials = self._process_materialnos_and_get_cache(materialnos)

        if not material_list:
            return []

        if missing_materials:
            # 使用线程池执行 HTTP 请求
            # future = self._executor.submit(self._fetch_materials_http, missing_materials)
            # api_data = future.result()  # 获取结果
            api_data = self._fetch_materials_http(missing_materials)
            
            # 补充缓存
            for item in api_data:
                material_no = item.get('materialno', '')
                if material_no:
                    self._production_cache._cache[CacheItem.MATERIAL.value][material_no] = item

            # 合并结果
            cached_data.extend(api_data)

        return cached_data


    @async_aps_error_handler("获取工单计划单详情")
    async def get_supplymo_detaildata(self, supplyno: str, get_prev_mo:bool=False, get_next_mo:bool=False, get_origin_so:bool=False):
        """
        异步获取工单的工序详情、及MTO销售订单信息
        Args:
            supplyno: 工单号
            get_prev_mo: 是否查询前 前置 工单
            get_next_mo: 是否查询后 后置 工单
        Returns:
            工单计划单详情
        """
        mo_data = self._production_cache.get_supply_mo(supplyno)

        if mo_data:
            mo_data['orderwc'] = self._production_cache.get_orderwc(supplyno)
            
            if get_origin_so:
                vendorno = mo_data.get('vendorno', '')
                if vendorno:
                    mo_data['so'] = await self.get_demand_datalist(vendorno)

            if get_prev_mo:
                related_demand = self._production_cache.get_demand(demand_no=supplyno)
                demands_data = [_ for _ in related_demand if _.get('type') != 'SO']
                if demands_data:
                    demands_no = [_['demandno'] for _ in demands_data]
                    peg_query_result = self._production_cache.batch_get_peg_by_demand(demands_no)
                    mo_data['prev_mo'] = self._production_cache.batch_get_supply_mo(peg_query_result)
                
            if get_next_mo:
                demands_no = self._production_cache.get_peg_by_supply(supplyno)
                mo_data['next_mo'] = self._production_cache.batch_get_supply_mo(demands_no)
            return mo_data
        else:
            supply_response_json = await self.get_mo_by_supplyno(supplyno, db_name=MYAPS_MAIN_DB, prev_mo=get_prev_mo, next_mo=get_next_mo, origin_so=get_origin_so)
            if supply_response_json.get('success') != 0 and supply_response_json.get('data'):
                mo_data = supply_response_json['data'][0]
                self._production_cache._cache[CacheItem.SUPPLY_MO.value][supplyno] = mo_data
                return mo_data
            else:
                logger.fail("获取工单计划单详情", supplyno, f"API返回错误: {supply_response_json.get('message', '未知错误')}")


    @classmethod
    async def get_mo_by_supplyno(cls, supplyno: str, db_name: str=MYAPS_MAIN_DB, prev_mo:bool=False, next_mo:bool=False, origin_so:bool=False) -> List[Dict]:
        """
        异步获取工单的工序详情、及MTO销售订单信息
        Args:
            supplyno: 工单号
            db_name: 数据库名称
            prev_mo: 是否查询前 前置 工单
            next_mo: 是否查询后 后置 工单
            origin_so: 是否查询原始销售订单信息
        Returns:
            工单计划单详情
        """
        try:
            async def get_orderwc(mono: str):
                orderwc: DbResult = await db_query(db_name=db_name, model_or_tablename="v_orderwc", filter_string=f"`SupplyNo`='{mono}'")
                return orderwc.data

            async def get_prev_mo(mono: str):
                """
                通过工单 supplyno 号查询前 前置 工单
                """
                for_demands: DbResult = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=f"`DemandNo`='{mono}' AND `Type` IN ('DM', 'RS', 'PR', 'PO')")
                demands_data = for_demands.data
                prev_mo = []
                if demands_data:
                    demands_no = ','.join([f"'{i['demandno']}'" for i in demands_data])
                    peg_query_result: DbResult = await db_exec_sql(
                        db_name=db_name,
                        sql=MINI_PEG_SQL.format(where_string=f"p.DemandNO IN ({demands_no}) AND p.S_Type IN ('PL', 'MO')"),
                        description=f"查询{demands_no}匹配的PL和MO"
                    )
                    if peg_query_result.data:
                        supplies_no = ','.join([f"'{i['s_supplyno']}'" for i in peg_query_result.data])
                        # prev_mo_query_result = await db_exec_sql(db_name=db_name, sql=V_SUPPLY_MO_SQL.format(supplynos=supplies_no), description=f"查询{supplies_no}的前置工单信息")
                        prev_mo_query_result: DbResult = await db_query(
                            db_name=db_name,
                            model_or_tablename="v_supply_mo",
                            select="`SupplyNo`",
                            filter_string=f"`SupplyNo` IN ({supplies_no})"
                        )
                        prev_mo = prev_mo_query_result.data
                return prev_mo

            async def get_next_mo(mono: str): 
                """
                通过工单 supplyno 号查询后 后置 工单
                """
                in_pegs: DbResult = await db_exec_sql(db_name=db_name, sql=MINI_PEG_SQL.format(where_string=f"p.S_SupplyNo='{mono}' AND p.Type IN ('DM', 'RS')"), description=f"查询{mono}匹配的DM和RS")
                pegs_data = in_pegs.data
                next_mo = []
                if pegs_data:
                    demands_no = ','.join([f"'{i['demandno']}'" for i in pegs_data])
                    # next_mo_query_result = await db_exec_sql(db_name=db_name, sql=V_SUPPLY_MO_SQL.format(supplynos=demands_no), description=f"查询{mono}的后续置工单信息")
                    next_mo_query_result: DbResult = await db_query(
                        db_name=db_name,
                        model_or_tablename="v_supply_mo",
                        select="`SupplyNo`",
                        filter_string=f"`SupplyNo` IN ({demands_no})"
                    )
                    next_mo = next_mo_query_result.data
                return next_mo

            async def get_so(so_demandno: str):
                """
                通过工单 supplyno 号查询销售订单
                """
                so_query_result: DbResult = await db_query(
                    db_name=db_name,
                    model_or_tablename="v_demand",
                    filter_string=f"`DemandNo`='{so_demandno}' AND `Type`='SO'"
                )
                so_data = so_query_result.data
                if so_data:
                    return so_data[0]

            db_name = db_name.replace(" ", "")

            result: DbResult = await db_query(
                db_name=db_name,
                model_or_tablename="v_supply_mo",
                filter_string=f"`SupplyNo`='{supplyno}'"
            )
            
            if result.success and result.meta.get('total') == 1:  # 筛选到唯一的工单，则补充工序信息（v_orderwc）
                result.data[0]['orderwc'] = await get_orderwc(mono=supplyno)

                vendorno = result.data[0].get('vendorno')
                if origin_so and result.data[0].get('category') == 'MTO' and vendorno:
                    result.data[0]['so'] = await get_so(vendorno)
                        
                if prev_mo:
                    result.data[0]['prev_mo'] = await get_prev_mo(supplyno)
                if next_mo:
                    result.data[0]['next_mo'] = await get_next_mo(supplyno)

            return result
        except Exception as e:
            logger.fail("获取工单详情", supplyno, f"{e}")
            raise


    @async_aps_error_handler("获取需求数据")
    async def get_demand_datalist(self, demandno: str) -> List[Dict]:
        """
        异步获取需求信息（优先从缓存获取，缓存未命中则访问API并加入缓存）
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        result_data = self._production_cache.get_demand(demandno)
        
        if result_data:
            return result_data
        
        filter_string = f"`DemandNo`='{demandno}'"
        demand_response_json: DbResult = await db_query(db_name=MYAPS_MAIN_DB, model_or_tablename="v_demand", filter_string=filter_string)
        api_data = demand_response_json.data
        
        if api_data:
            self._production_cache._cache[CacheItem.DEMAND.value][demandno] = api_data
        
        return api_data



@dataclass
class ExecutionResult:
    success: bool
    raw_data: Any = None
    msg: str = None
    mono: str = None
    push_data: Dict = None
    timestamp: datetime = field(default_factory=datetime.now)



class _ResultCollector:
    """结果收集器，用于收集异步函数执行结果"""

    def __init__(self):
        self.results: List[ExecutionResult] = []
        self._lock = asyncio.Lock()
        self.batch_id = str(uuid.uuid4())[:8]
        self.start_time = time.time()
    

    async def add_result(self, result: ExecutionResult):
        async with self._lock:
            self.results.append(result)
    

    def get_summary(self) -> Dict[str, Any]:
        success_count = sum(1 for r in self.results if r.success)
        total_time = time.time() - self.start_time
        failed_results = [r for r in self.results if not r.success]
        failed_details = []
        for r in failed_results:
            detail = {}
            if r.raw_data is not None:
                detail["raw_data"] = r.raw_data
            if r.msg is not None:
                detail["msg"] = r.msg
            if r.push_data is not None:
                detail["push_data"] = r.push_data
            if r.timestamp is not None:
                detail["timestamp"] = r.timestamp.isoformat()
            failed_details.append(detail)
        
        # 转换 ExecutionResult 对象为字典
        details = []
        for r in self.results:
            detail = {
                "success": r.success,
                "raw_data": r.raw_data,
                "msg": r.msg,
                "mono": r.mono,
                "push_data": r.push_data,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None
            }
            # 过滤掉 None 值
            detail = {k: v for k, v in detail.items() if v is not None}
            details.append(detail)
        
        # 按错误信息分类汇总失败记录
        failed_by_msg = {}
        for r in failed_results:
            error_msg = r.msg or "Unknown error"
            if error_msg not in failed_by_msg:
                failed_by_msg[error_msg] = 0
            failed_by_msg[error_msg] += 1
        
        # 按错误信息升序排序
        failed_by_msg = dict(sorted(failed_by_msg.items(), key=lambda x: x[0]))
        
        return {
            "batch_id": self.batch_id,
            "total": len(self.results),
            "success": success_count,
            "failed": len(self.results) - success_count,
            "total_time_sec": round(total_time, 2),
            "avg_time_per_item_sec": round(total_time / len(self.results), 2) if self.results else 0,
            "details": details,
            "failed_details": failed_details,
            "failed_by_msg": failed_by_msg
        }
    
    def format_notification(self, description: str = "任务") -> str:
        summary = self.get_summary()
        
        # 转换总耗时为友好格式
        total_seconds = summary['total_time_sec']
        if total_seconds < 60:
            time_str = f"{total_seconds:.1f} 秒"
        elif total_seconds < 3600:
            minutes = total_seconds / 60
            time_str = f"{minutes:.1f} 分钟"
        else:
            hours = total_seconds / 3600
            time_str = f"{hours:.1f} 小时"
        
        notification = (
            f"【{description}】执行完成！\n"
            f"批次ID: {summary['batch_id']}\n"
            f"总计处理: {summary['total']} 条\n"
            f"\t✅ 成功: {summary['success']} 条\n"
            f"\t🚫 失败: {summary['failed']} 条\n"
            f"总耗时: {time_str}\n"
            f"平均每条: {summary['avg_time_per_item_sec']} 秒"
        )
        
        if summary.get('failed_by_msg'):
            notification += "\n\n📊失败原因汇总\n"
            for error_msg, count in summary['failed_by_msg'].items():
                notification += f"\t🔴 {error_msg}: 【{count}】 条\n"
        
        return notification



def async_error_handler(operation_name):
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # 尝试获取操作对象（通常是第一个参数）
            target_obj = args[0] if args else kwargs.get(list(kwargs.keys())[0], "未知")
            try:
                return await func(self, *args, **kwargs)
            except Exception as e:
                logger.fail(operation_name, target_obj, f"{operation_name}时发生错误：{e}")
                raise
        return wrapper
    return decorator


class EventResultPoster:

    def __init__(self, db_name: str=MYAPS_MAIN_DB):
        self.db_name = db_name
        self._collector = _ResultCollector()
        self._results = self._collector.results


    def get_summary(self) -> Dict[str, Any]:
        return self._collector.get_summary()


    def format_notification(self, description: str = "任务") -> str:
        return self._collector.format_notification(description)


    @async_error_handler("MO发布成功")
    async def mo_release_success(
        self,
        native_plno: str,
        mono: str = None,
        to_status: Literal['E2A', 'REL'] = 'E2A',
        msg: str = None,
        msg_from: str = 'SYSTEM',
        _id: str = None,
        _entryid: str = None
    ):
        """
        修改PL的Status、SupplyNo、Memo等字段
        🅰 native_plno: 原生PL计划单编号
        🅰 mono: MO号，可选，若传值则更改PL的原生SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        🅰 _id: 外部系统返回的 MO ID
        🅰 _entryid: 外部系统返回的 MO 详情 ID（对于某些有表头的ERP，具体的 MO 是存在于子表中的，有单独的行记录id
        """
        mono = mono or native_plno
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memo = f"{now} {ce.RELEASE_SUCCESS.value} {msg_from}: '{msg}' @ {native_plno}"
        
        logger.update("PL状态", native_plno, f"目标状态{to_status}，MO单号{mono}")
        
        response_json: MultiDbResult = await call_dbprocdure(
            db_names=self.db_name,
            procedure_name="SupplyConvertMOByE2A",
            params_list=[[native_plno, mono, to_status, str(_id or ""), str(_entryid or ""), memo[:255]]]
        )
        
        logger.info(f"更新PL状态响应：成功")

        await self._collector.add_result(ExecutionResult(
            success=True,
            raw_data=native_plno,
            msg=f"{msg_from}: {msg}" if msg else None,
            mono=mono
        ))
        
        return response_json


    @async_error_handler("MO发布失败")
    async def mo_release_failed(
        self,
        native_plno: str,
        to_status: Literal['NEW', 'CRE'] = 'CRE',
        msg: str = None,
        raw_data: dict = None,
        push_data: dict = None,
        msg_from: str = 'SYSTEM'
    ):
        logger.warning_msg(f"推送 MO {msg}", json.dumps(push_data, ensure_ascii=False), to_file=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass

        memo = f"{now} {ce.RELEASE_FAILED.value} {msg_from}: '{msg}'"
        
        patch_data = {
            'Status': to_status,
            'Memo': memo[:255],
        }
        
        response_json: MultiDbResult = await db_update_by_index(
            db_names=self.db_name,
            model_or_tablename="t_supply",
            index_dict={"SupplyNo": native_plno},
            new_values_dict=patch_data,
            not_found_behavior="skip"
        )
        
        await self._collector.add_result(ExecutionResult(
            success=False,
            raw_data=native_plno,
            msg=f"{msg_from}: {msg}" if msg else None,
            push_data=push_data
        ))
        
        return response_json


    @async_error_handler("RS发布成功")
    async def rs_release_success(
        self,
        rsno: str,
        to_status: Literal['E2A', 'REL'] = 'E2A',
        msg: str = None,
        msg_from: str = 'SYSTEM',
        _code: str = None,
        _id: str = None,
        _entryid: str = None
    ):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memo = f"{now} {ce.RELEASE_SUCCESS.value} {msg_from}: '{msg}' @ {rsno}"
        
        logger.update("RS状态", rsno, f"目标状态{to_status}")
        
        patch_data = {
            'Status': to_status,
            'Memo': memo[:255],
            'ApiEx_SN': _code or "",
            'ApiEx_ID': _id or "",
            'ApiEx_EntryID': _entryid or "",
        }
        
        response_json: MultiDbResult = await db_update_by_index(
            db_names=self.db_name,
            model_or_tablename="t_demand",
            index_dict={"DemandNo": rsno},
            new_values_dict=patch_data,
            not_found_behavior="skip"
        )
        
        logger.info(f"更新RS状态响应：成功")
        
        await self._collector.add_result(ExecutionResult(
            success=True,
            raw_data=rsno,
            msg=f"{msg_from}: {msg}" if msg else None,
            mono=_code
        ))
        
        return response_json


    @async_error_handler("RS发布失败")
    async def rs_release_failed(
        self,
        rsno: str,
        to_status: Literal['NEW', 'CRE'] = 'CRE',
        msg: str = None,
        msg_from: str = 'SYSTEM',
        push_data: dict | list = None,
        raw_data: dict | list = None
    ):
        logger.warning_msg(f"推送 RS {msg}", json.dumps(push_data, ensure_ascii=False), to_file=True)
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memo = f"{now} {ce.RELEASE_FAILED.value} {msg_from}: '{msg}'"

        patch_data = {
            'Status': to_status,
            'Memo': memo[:255],
        }
        
        response_json: MultiDbResult = await db_update_by_index(
            db_names=self.db_name,
            model_or_tablename="t_demand",
            index_dict={"DemandNo": rsno},
            new_values_dict=patch_data,
            not_found_behavior="skip"
        )
        
        await self._collector.add_result(ExecutionResult(
            success=False,
            raw_data=rsno,
            msg=f"{msg_from}: {msg}" if msg else None,
            push_data=push_data
        ))
        
        return response_json


    @async_error_handler("PR发布成功")
    async def pr_release_success(
        self,
        prno: Union[str, List[str]],
        to_status: Literal['E2A', 'REL'] = 'E2A',
        msg: str = None,
        msg_from: str = 'SYSTEM',
        _code: str = None,
        _id: str = None,
        _entryid: str = None
    ):
        # 处理 prno 参数，支持列表和逗号分隔的字符串
        prno_list = []
        if isinstance(prno, str):
            # 处理逗号分隔的字符串
            prno_list = [p.strip() for p in prno.split(',') if p.strip()]
        elif isinstance(prno, list):
            # 处理列表
            prno_list = [p.strip() for p in prno if isinstance(p, str) and p.strip()]
        
        if not prno_list:
            logger.warning("PR发布成功：未提供有效的PR编号")
            return MultiDbResult(success=True, data={}, message="未提供有效的PR编号")
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        results = {}
        
        for p in prno_list:
            memo = f"{now} {ce.RELEASE_SUCCESS.value} {msg_from}: '{msg}' @ {p}"
            logger.update("PR状态", p, "")
            
            patch_data = {
                'Status': to_status,
                'Memo': memo[:255],
                'ApiEx_SN': _code or "",
                'ApiEx_ID': _id or "",
                'ApiEx_EntryID': _entryid or "",
            }
            
            response_json: MultiDbResult = await db_update_by_index(
                db_names=self.db_name,
                model_or_tablename="t_supply",
                index_dict={"SupplyNo": p},
                new_values_dict=patch_data,
                not_found_behavior="skip"
            )
            
            results[p] = response_json
            
            await self._collector.add_result(ExecutionResult(
                success=True,
                raw_data=p,
                msg=f"{msg_from}: {msg}" if msg else None,
                mono=_code
            ))
        
        logger.info(f"更新PR状态响应：成功，共处理 {len(prno_list)} 个PR")
        
        # 合并结果
        merged_result = MultiDbResult(
            success=all(r.success for r in results.values()),
            data=results,
            message=f"成功处理 {len(prno_list)} 个PR"
        )
        
        return merged_result


    @async_error_handler("PR发布失败")
    async def pr_release_failed(
        self,
        prno: str,
        to_status: Literal['E2A', 'REL'] = 'E2A',
        msg: str = None,
        msg_from: str = 'SYSTEM',
        push_data: dict | list = None,
        raw_data: dict | list = None
    ):
        if msg:
            try:
                msg = str(msg)[:64]
            except Exception as e:
                pass
        logger.warning_msg(f"推送 PR {msg}", json.dumps(push_data, ensure_ascii=False), to_file=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        memo = f"{now} {ce.RELEASE_FAILED.value} {msg_from}: '{msg}'"
        
        patch_data = {
            'Status': to_status,
            'Memo': memo[:255],
        }
        
        response_json: MultiDbResult = await db_update_by_index(
            db_names=self.db_name,
            model_or_tablename="t_supply",
            index_dict={"SupplyNo": prno},
            new_values_dict=patch_data,
            not_found_behavior="skip"
        )
        
        await self._collector.add_result(ExecutionResult(
            success=False,
            raw_data=prno,
            msg=f"{msg_from}: {msg}" if msg else None,
            push_data=push_data
        ))
        
        return response_json

