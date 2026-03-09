"""
异步处理组件

HAP API v3 的异步包装器，使用线程池将同步操作转换为异步操作，
避免在 FastAPI 等异步框架中阻塞事件循环。

使用方式：
    1. 后端直接调用：await async_hap.rows(Models).upsert(data_list)
    2. API 接口触发：通过 FastAPI 路由调用

示例：
    >>> from apps.data_opt.components.async_hap import AsyncHapConnection
    >>> from apps.data_opt.components.hap import hap_conn, MyModel
    >>> async_hap = AsyncHapConnection(hap_conn)
    >>> result = await async_hap.upsert(MyModel, [{"name": "test"}])
"""

import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import (
    List, Dict, Any, Optional, Type, TypeVar, Generic, 
    Callable, Union, Literal, Generator, AsyncGenerator
)

from .hap import (
    CACHE_JSON, console_log,
    HapConfig, HapConnection, HapQuerySet, HapRowSet, Model, Q, Field,
    StrField, NumField, RelationField, SubtableField, ChoiceField,
)


# 最大并发数
_MAX_CONCURRENCY:int = CACHE_JSON.get("hap", {}).get("max_concurrency", os.cpu_count() * 3)
# 初始缓冲区大小（默认 200）
_DEFAULT_BUFFER_SIZE:int = CACHE_JSON.get("hap", {}).get("default_buffer_size", 200)
# 自适应速率控制器配置（高优先级）
_ADAPTIVE_MIN_BUFFER_SIZE:int = CACHE_JSON.get("hap", {}).get("adaptive_min_buffer_size", 50)
_ADAPTIVE_SCALE_UP_FAST:float = CACHE_JSON.get("hap", {}).get("adaptive_scale_up_fast", 1.5)
_ADAPTIVE_SCALE_UP_SLOW:float = CACHE_JSON.get("hap", {}).get("adaptive_scale_up_slow", 1.3)
_ADAPTIVE_SCALE_DOWN:float = CACHE_JSON.get("hap", {}).get("adaptive_scale_down", 0.8)
_ADAPTIVE_SCALE_DOWN_FAST:float = CACHE_JSON.get("hap", {}).get("adaptive_scale_down_fast", 0.5)
_DEFAULT_MAX_RETRIES:int = CACHE_JSON.get("hap", {}).get("default_max_retries", 3)
_DEFAULT_RETRY_DELAY:float = CACHE_JSON.get("hap", {}).get("default_retry_delay", 1.0)


def hap_async_timer(func: Callable = None, *, operation_name: str = None):
    """统计 HAP 异步操作执行时间的装饰器
    
    用于装饰 async 函数，记录其执行时间、操作名称、数据条数等信息。
    
    Args:
        func: 被装饰的函数
        operation_name: 操作名称，默认使用函数名
    
    Returns:
        装饰后的函数
    
    Example:
        >>> @hap_async_timer()
        >>> async def my_operation():
        >>>     pass
        >>>
        >>> @hap_async_timer(operation_name="自定义操作")
        >>> async def my_operation():
        >>>     pass
    """
    def decorator(fn: Callable) -> Callable:
        import time
        import logging
        import functools
        
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or fn.__name__
            start_time = time.time()
            result = None
            error = None
            data_count = 0
            
            try:
                result = await fn(*args, **kwargs)
                
                if hasattr(result, 'count'):
                    data_count = result.count()
                elif hasattr(result, '__len__'):
                    data_count = len(result)
                elif isinstance(result, int):
                    data_count = result
                
                return result
            except Exception as e:
                error = e
                raise
            finally:
                elapsed_time = time.time() - start_time
                
                log_info = {
                    "operation": op_name,
                    "elapsed_time": f"{elapsed_time:.3f}s",
                    "data_count": data_count,
                }
                
                if elapsed_time > 0:
                    data_rate_per_second = data_count / elapsed_time
                    log_info["data_rate_per_second"] = f"{data_rate_per_second:.2f}条/秒"
                else:
                    log_info["data_rate_per_second"] = "N/A"
                
                if error:
                    log_info["status"] = "FAILED"
                    log_info["error"] = str(error)
                    console_log.warning(f"HAP异步操作统计 | {log_info}")
                else:
                    log_info["status"] = "SUCCESS"
                    console_log.info(f"HAP异步操作统计 | {log_info}")
        
        return wrapper
    
    if func is None:
        return decorator
    else:
        return decorator(func)



ModelType = TypeVar("ModelType", bound=Model)


class HapApiMonitor:
    """HAP API 请求监控器
    
    记录所有向 HAP 发起的 API 请求，包括：
    - 请求时间、方法、URL
    - 请求参数、响应时间
    - 成功/失败状态
    - 错误信息
    """
    
    def __init__(self):
        """初始化监控器"""
        import threading
        self._lock = threading.Lock()
        self._requests = []
        self._max_records = 1000  # 最多保留 1000 条记录
    
    def record_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        data: dict = None,
        response_time: float = 0.0,
        success: bool = True,
        status_code: int = None,
        error: str = None
    ):
        """记录 API 请求
        
        Args:
            method: HTTP 方法（GET, POST, PATCH, DELETE）
            endpoint: API 端点
            params: 请求参数
            data: 请求体数据
            response_time: 响应时间（秒）
            success: 是否成功
            status_code: HTTP 状态码
            error: 错误信息
        """
        import time
        
        record = {
            "timestamp": time.time(),
            "method": method,
            "endpoint": endpoint,
            "params": params,
            "data": data,
            "response_time": response_time,
            "success": success,
            "status_code": status_code,
            "error": error
        }
        
        with self._lock:
            self._requests.append(record)
            # 限制记录数量
            if len(self._requests) > self._max_records:
                self._requests = self._requests[-self._max_records:]
    
    def get_stats(self, last_n: int = 100) -> dict:
        """获取统计数据
        
        Args:
            last_n: 统计最近 N 条记录
            
        Returns:
            dict: 统计信息
        """
        with self._lock:
            records = self._requests[-last_n:] if last_n else self._requests
            
            if not records:
                return {
                    "total": 0,
                    "success": 0,
                    "failure": 0,
                    "success_rate": 0.0,
                    "avg_response_time": 0.0,
                    "requests": []
                }
            
            total = len(records)
            success = sum(1 for r in records if r["success"])
            failure = total - success
            avg_response_time = sum(r["response_time"] for r in records) / total
            
            # 按端点统计
            endpoint_stats = {}
            for r in records:
                endpoint = r["endpoint"]
                if endpoint not in endpoint_stats:
                    endpoint_stats[endpoint] = {
                        "count": 0,
                        "success": 0,
                        "avg_response_time": 0.0
                    }
                endpoint_stats[endpoint]["count"] += 1
                if r["success"]:
                    endpoint_stats[endpoint]["success"] += 1
                endpoint_stats[endpoint]["avg_response_time"] += r["response_time"]
            
            # 计算每个端点的平均响应时间
            for stats in endpoint_stats.values():
                stats["success_rate"] = stats["success"] / stats["count"] if stats["count"] > 0 else 0
                stats["avg_response_time"] /= stats["count"]
            
            return {
                "total": total,
                "success": success,
                "failure": failure,
                "success_rate": success / total if total > 0 else 0,
                "avg_response_time": avg_response_time,
                "endpoint_stats": endpoint_stats,
                "requests": records[-10:]  # 最近 10 条记录
            }
    
    def get_recent_errors(self, limit: int = 10) -> list:
        """获取最近的错误记录
        
        Args:
            limit: 返回的记录数
            
        Returns:
            list: 错误记录列表
        """
        with self._lock:
            errors = [r for r in self._requests if not r["success"]]
            return errors[-limit:]
    
    def clear(self):
        """清空所有记录"""
        with self._lock:
            self._requests.clear()


class AdaptiveRateController:
    """自适应速率控制器
    
    根据网络状况和 QPS 动态调整 buffer_size 和 max_concurrency。
    
    核心机制：
    1. 监控请求成功率和响应时间
    2. 根据成功率动态调整并发数
    3. 根据响应时间动态调整缓冲区大小
    4. 遇到错误时自动降速
    """
    
    def __init__(
        self,
        initial_buffer_size: int = None,
        initial_concurrency: int = None,
        min_buffer_size: int = None,
        max_buffer_size: int = None,
        min_concurrency: int = 1,
        max_concurrency: int = None,
        target_qps: float = 10.0,
        adjustment_interval: int = 5,
    ):
        """
        初始化自适应速率控制器
        
        Args:
            initial_buffer_size: 初始缓冲区大小，None 时根据 QPS 自动计算
            initial_concurrency: 初始并发数，None 时根据 QPS 自动计算
            min_buffer_size: 最小缓冲区大小，None 时使用配置默认值
            max_buffer_size: 最大缓冲区大小，None 时根据 QPS 自动计算
            min_concurrency: 最小并发数
            max_concurrency: 最大并发数，None 时根据 QPS 自动计算
            target_qps: 目标 QPS（每秒请求数）
            adjustment_interval: 调整间隔（每 N 个请求调整一次）
        """
        # 使用配置的默认值
        if min_buffer_size is None:
            min_buffer_size = _ADAPTIVE_MIN_BUFFER_SIZE
        
        # 根据 QPS 自动计算参数
        if initial_buffer_size is None:
            initial_buffer_size = min(500, max(100, int(target_qps * 5)))
        if initial_concurrency is None:
            initial_concurrency = min(10, max(_MAX_CONCURRENCY, int(target_qps / 10)))
        if max_buffer_size is None:
            max_buffer_size = min(1000, max(300, int(target_qps * 10)))
        if max_concurrency is None:
            max_concurrency = min(20, max(_MAX_CONCURRENCY, int(target_qps / 5)))
        
        self.buffer_size = initial_buffer_size
        self.concurrency = initial_concurrency
        
        self.min_buffer_size = min_buffer_size
        self.max_buffer_size = max_buffer_size
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.target_qps = target_qps
        self.adjustment_interval = adjustment_interval
        
        # 统计数据
        self.request_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.total_response_time = 0.0
        self.recent_response_times = []
        self.recent_failures = []
        
        import threading
        self._lock = threading.Lock()
    
    def record_request(self, success: bool, response_time: float):
        """记录请求结果"""
        with self._lock:
            self.request_count += 1
            if success:
                self.success_count += 1
                self.total_response_time += response_time
                self.recent_response_times.append(response_time)
                # 保留最近 20 次响应时间
                if len(self.recent_response_times) > 20:
                    self.recent_response_times.pop(0)
            else:
                self.failure_count += 1
                self.recent_failures.append(response_time)
                # 保留最近 10 次失败
                if len(self.recent_failures) > 10:
                    self.recent_failures.pop(0)
    
    def adjust(self) -> tuple:
        """根据统计数据调整参数
        
        Returns:
            tuple: (new_buffer_size, new_concurrency)
        """
        with self._lock:
            # 每隔一定请求数才调整
            if self.request_count % self.adjustment_interval != 0:
                return self.buffer_size, self.concurrency
            
            # 计算成功率
            total = self.success_count + self.failure_count
            success_rate = self.success_count / total if total > 0 else 1.0
            
            # 计算平均响应时间
            avg_response_time = (
                sum(self.recent_response_times) / len(self.recent_response_times)
                if self.recent_response_times else 1.0
            )
            
            # 计算当前 QPS
            current_qps = 1.0 / avg_response_time if avg_response_time > 0 else 1.0
            
            # 调整策略
            new_buffer_size = self.buffer_size
            new_concurrency = self.concurrency
            
            # 成功率高且 QPS 低于目标 -> 激进提速
            if success_rate > 0.90 and current_qps < self.target_qps:
                # 大幅增加缓冲区（减少请求次数）
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_UP_FAST))
                # 大幅增加并发（提高吞吐量）
                new_concurrency = min(self.max_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_UP_FAST))
            
            # 成功率一般但 QPS 远低于目标 -> 温和提速
            elif success_rate > 0.85 and current_qps < self.target_qps * 0.5:
                # 增加缓冲区
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_UP_SLOW))
                # 增加并发
                new_concurrency = min(self.max_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_UP_SLOW))
            
            # 成功率低或响应时间过长 -> 降速
            elif success_rate < 0.75 or avg_response_time > 10.0:
                # 减小缓冲区（更频繁但更小的请求）
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_DOWN))
                # 减少并发（降低服务器压力）
                new_concurrency = max(self.min_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_DOWN))
            
            # 连续失败 -> 大幅降速
            elif len(self.recent_failures) >= 3:
                # 大幅减小缓冲区（更多失败时）
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * _ADAPTIVE_SCALE_DOWN_FAST))
                # 大幅减少并发（失败时降低服务器压力）
                new_concurrency = max(self.min_concurrency, int(self.concurrency * _ADAPTIVE_SCALE_DOWN_FAST))
            
            # 更新参数
            self.buffer_size = new_buffer_size
            self.concurrency = new_concurrency
            
            return new_buffer_size, new_concurrency
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        with self._lock:
            total = self.success_count + self.failure_count
            return {
                "request_count": self.request_count,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "success_rate": self.success_count / total if total > 0 else 1.0,
                "buffer_size": self.buffer_size,
                "concurrency": self.concurrency,
                "avg_response_time": (
                    sum(self.recent_response_times) / len(self.recent_response_times)
                    if self.recent_response_times else 0
                ),
            }


class AsyncHapConnection:
    """HAP 连接的异步包装器
    
    通过线程池将同步 HAP 操作转换为异步操作，保持与同步版本相同的 API 接口。
    复用 HapConnection 的线程池，避免资源重复创建。
    
    Attributes:
        _sync_conn: 原始的同步 HAP 连接
        _executor: 线程池执行器（复用自 sync_conn）
        _max_workers: 最大工作线程数
    
    Example:
        >>> hap_conn = HapConnection(app_key="xxx", sign="yyy")
        >>> async_hap = AsyncHapConnection(hap_conn)
        >>> 
        >>> # 方式一：直接调用 upsert
        >>> result = await async_hap.upsert(MyModel, data_list)
        >>> 
        >>> # 方式二：使用查询集
        >>> query = async_hap.query(MyModel).filter(status="active")
        >>> results = await query.all()
    """
    
    def __init__(
        self, 
        sync_conn: HapConnection, 
        enable_monitor: bool = True
    ):
        """
        初始化异步 HAP 连接
        
        Args:
            sync_conn: 同步 HAP 连接实例
            enable_monitor: 是否启用 API 监控，默认 True
        """
        self._sync_conn = sync_conn
        self._executor = sync_conn.executor
        self._max_workers = sync_conn.max_workers
        self._func_cache = {}
        self._monitor = HapApiMonitor() if enable_monitor else None
        self._connection_warmer = getattr(sync_conn, '_connection_warmer', None)
    
    def _run_in_executor(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """在线程池中执行同步函数
        
        Args:
            func: 要执行的同步函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            asyncio.Future: 异步 Future 对象
        """
        loop = asyncio.get_event_loop()
        if kwargs:
            # 对于有关键字参数的情况，使用闭包避免 functools.partial
            def wrapper():
                return func(*args, **kwargs)
            return loop.run_in_executor(self._executor, wrapper)
        else:
            # 对于只有位置参数的情况，直接传递
            return loop.run_in_executor(self._executor, func, *args)
    
    def _run_with_monitor(
        self, 
        func: Callable, 
        method: str,
        endpoint: str,
        *args, 
        **kwargs
    ) -> asyncio.Future:
        """在线程池中执行同步函数并监控
        
        Args:
            func: 要执行的同步函数
            method: HTTP 方法
            endpoint: API 端点
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            asyncio.Future: 异步 Future 对象
        """
        import time
        
        async def monitored_wrapper():
            start_time = time.time()
            success = True
            error = None
            status_code = None
            
            try:
                result = await self._run_in_executor(func, *args, **kwargs)
                return result
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                response_time = time.time() - start_time
                
                # 记录监控数据
                if self._monitor:
                    self._monitor.record_request(
                        method=method,
                        endpoint=endpoint,
                        params=kwargs,
                        response_time=response_time,
                        success=success,
                        error=error
                    )
        
        return monitored_wrapper()
    
    # ==================== 监控相关方法 ====================
    
    def get_monitor_stats(self, last_n: int = 100) -> dict:
        """获取 API 监控统计数据
        
        Args:
            last_n: 统计最近 N 条记录
            
        Returns:
            dict: 统计信息
        """
        if not self._monitor:
            return {"error": "监控未启用"}
        return self._monitor.get_stats(last_n)
    
    def get_recent_errors(self, limit: int = 10) -> list:
        """获取最近的错误记录
        
        Args:
            limit: 返回的记录数
            
        Returns:
            list: 错误记录列表
        """
        if not self._monitor:
            return []
        return self._monitor.get_recent_errors(limit)
    
    def clear_monitor(self):
        """清空监控数据"""
        if self._monitor:
            self._monitor.clear()
    
    def is_monitor_enabled(self) -> bool:
        """检查监控是否启用
        
        Returns:
            bool: 是否启用监控
        """
        return self._monitor is not None
    
    # ==================== 模型注册与管理 ====================
    
    async def register_model(self, model: Type[ModelType]) -> None:
        """异步注册模型
        
        Args:
            model: 模型类
        """
        await self._run_in_executor(self._sync_conn.register_model, model)
    
    async def register_models(self, models: List[Type[ModelType]]) -> None:
        """异步批量注册模型
        
        Args:
            models: 模型类列表
        """
        await self._run_in_executor(self._sync_conn.register_models, models)
    
    def get_model(self, model_name: str) -> Type[ModelType]:
        """获取模型（同步，不涉及 IO）
        
        Args:
            model_name: 模型名称或 worksheet_id
            
        Returns:
            Type[ModelType]: 模型类
        """
        return self._sync_conn.get_model(model_name)
    
    # ==================== 核心数据操作方法 ====================
    
    @hap_async_timer()
    async def upsert(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        exclude_none: bool = True,
        trigger_workflow: bool = True,
        when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
    ) -> HapRowSet[ModelType]:
        """异步 upsert 操作
        
        根据主键或冲突字段判断是更新还是创建记录。
        
        Args:
            model: 模型类
            data_list: 要 upsert 的数据列表
            exclude_none: 是否排除值为 None 的字段，默认 True
            trigger_workflow: 是否触发工作流，默认 True
            when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
                - 'jumpover': 跳过不更新
                - 'update': 强制更新
                
        Returns:
            HapRowSet[ModelType]: 包含 upsert 后模型实例的行集合
            
        Example:
            >>> result = await async_hap.upsert(
            ...     MyModel,
            ...     [{"id": "1", "name": "test"}, {"id": "2", "name": "test2"}],
            ...     trigger_workflow=False
            ... )
            >>> print(f"处理了 {result.count()} 条记录")
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.upsert,
            data_list=data_list,
            exclude_none=exclude_none,
            trigger_workflow=trigger_workflow,
            when_value_equal_then=when_value_equal_then
        )
    
    @hap_async_timer()
    async def bulk_create(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量创建
        
        Args:
            model: 模型类
            data_list: 要创建的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 创建的模型实例列表
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.bulk_create,
            data_list=data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def bulk_update(
        self,
        model: Type[ModelType],
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量更新
        
        Args:
            model: 模型类
            data_list: 要更新的数据列表（必须包含 row_id 或主键）
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 更新的模型实例列表
        """
        query_set = self._sync_conn.rows(model)
        return await self._run_in_executor(
            query_set.bulk_update,
            data_list=data_list,
            trigger_workflow=trigger_workflow
        )
    
    # ==================== 批量处理优化（针对生成器）====================
    
    @hap_async_timer()
    async def upsert_from_generator(
        self,
        model: Type[ModelType],
        data_source,
        buffer_size: int = None,
        max_concurrency: int = None,
        max_retries: int = None,
        retry_delay: float = None,
        adaptive: bool = True,
        target_qps: float = None,
        **kwargs
    ) -> int:
        """从生成器函数批量 upsert 数据（高性能版本）[已废弃]
        
        .. deprecated::
            请使用新的调用方式：await async_hap.rows(Model).upsert_from_generator(data_generator_func)
        针对 `pull_incremental_data` 等场景优化，支持批量收集和并发处理。
        包含错误处理、重试机制和自适应速率控制。
        
        Args:
            model: 模型类
            data_source: 数据生成器函数，每次调用返回一个数据列表的生成器
            buffer_size: 缓冲区大小，None 时使用自适应调节
            max_concurrency: 最大并发数，None 时使用自适应调节
            max_retries: 最大重试次数，None 时使用配置默认值
            retry_delay: 重试延迟（秒），None 时使用配置默认值
            adaptive: 是否启用自适应速率控制，默认 True
            target_qps: 目标 QPS（每秒请求数），None 时自动从 HapConfig 获取
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
            
        Example:
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(data_gen_func)
        """
        from typing import Callable, Generator
        import logging
        import time
        
        if callable(data_source):
            data_generator = data_source()
        else:
            raise ValueError("data_source 必须是生成器函数，请传递函数名而非函数调用结果")
        
        # 使用配置的默认值
        if max_retries is None:
            max_retries = _DEFAULT_MAX_RETRIES
        if retry_delay is None:
            retry_delay = _DEFAULT_RETRY_DELAY
        
        # 自动从 HapConfig 获取 QPS 限制
        if target_qps is None:
            target_qps = getattr(self._sync_conn, 'qps_limit', 10.0)
            console_log.info(f"从 HapConfig 自动获取 QPS 限制: {target_qps}")
        
        # 使用智能批处理大小计算器（如果同步版本已配置）
        smart_batch_calculator = getattr(self._sync_conn, '_batch_size_calculator', None)
        
        # 初始化自适应控制器
        if adaptive:
            # 如果提供了 buffer_size，使用提供的值；否则使用智能计算
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值初始化，后续根据实际数据量调整
                initial_buffer = _DEFAULT_BUFFER_SIZE
            else:
                initial_buffer = buffer_size or _DEFAULT_BUFFER_SIZE
            
            controller = AdaptiveRateController(
                initial_buffer_size=initial_buffer,
                initial_concurrency=max_concurrency or _MAX_CONCURRENCY,
                target_qps=target_qps,
            )
            current_buffer_size = controller.buffer_size
            current_concurrency = controller.concurrency
        else:
            # 非自适应模式，使用智能批处理大小
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值，后续根据实际数据调整
                current_buffer_size = _DEFAULT_BUFFER_SIZE
            else:
                current_buffer_size = buffer_size or _DEFAULT_BUFFER_SIZE
            current_concurrency = max_concurrency or _MAX_CONCURRENCY
        
        buffer = []
        total_count = 0
        semaphore = asyncio.Semaphore(current_concurrency)
        tasks = []
        
        async def do_upsert_with_retry(data_batch, batch_index):
            """带重试和性能监控的 upsert"""
            nonlocal current_buffer_size, current_concurrency, semaphore
            
            async with semaphore:
                start_time = time.time()
                for attempt in range(max_retries):
                    try:
                        result = await self.upsert(model, data_batch, **kwargs)
                        response_time = time.time() - start_time
                        
                        # 记录成功请求到自适应控制器
                        if adaptive:
                            controller.record_request(True, response_time)
                        
                        # 记录到监控器
                        if self._monitor:
                            # 安全获取 worksheet_id
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=True
                            )
                        
                        return result.count()
                    except Exception as e:
                        response_time = time.time() - start_time
                        console_log.warning(f"批次 {batch_index} 第 {attempt + 1} 次尝试失败: {e}")
                        
                        # 记录失败请求到自适应控制器
                        if adaptive:
                            controller.record_request(False, response_time)
                        
                        # 记录到监控器
                        if self._monitor:
                            # 安全获取 worksheet_id
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=False,
                                error=str(e)
                            )
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                        else:
                            console_log.error(f"批次 {batch_index} 最终失败，跳过 {len(data_batch)} 条数据")
                            return 0
                return 0
        
        batch_index = 0
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= current_buffer_size:
                batch_index += 1
                
                # 自适应调整参数
                if adaptive and batch_index % 5 == 0:
                    new_buffer_size, new_concurrency = controller.adjust()
                    
                    if new_concurrency != current_concurrency:
                        # 更新信号量
                        current_concurrency = new_concurrency
                        semaphore = asyncio.Semaphore(current_concurrency)
                        console_log.info(f"自适应调整: 并发数 -> {current_concurrency}")
                    
                    if new_buffer_size != current_buffer_size:
                        current_buffer_size = new_buffer_size
                        console_log.info(f"自适应调整: 缓冲区 -> {current_buffer_size}")
                    
                    # 定期输出统计信息
                    if batch_index % 20 == 0:
                        stats = controller.get_stats()
                        console_log.info(
                            f"统计: 成功率={stats['success_rate']:.2%}, "
                            f"平均响应={stats['avg_response_time']:.2f}s, "
                            f"当前参数: buffer={current_buffer_size}, concurrency={current_concurrency}"
                        )
                
                # 提交当前缓冲区的数据
                tasks.append(asyncio.create_task(
                    do_upsert_with_retry(buffer[:], batch_index)
                ))
                buffer = []
                
                # 控制并发数量，避免内存溢出
                if len(tasks) >= current_concurrency * 2:
                    done, pending = await asyncio.wait(
                        tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        try:
                            total_count += await task
                        except Exception as e:
                            console_log.error(f"任务执行失败: {e}")
                    tasks = list(pending)
        
        # 处理剩余数据
        if buffer:
            batch_index += 1
            tasks.append(asyncio.create_task(
                do_upsert_with_retry(buffer, batch_index)
            ))
        
        # 等待所有任务完成
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, int):
                    total_count += result
                elif isinstance(result, Exception):
                    console_log.error(f"任务异常: {result}")
        
        # 输出最终统计
        if adaptive:
            stats = controller.get_stats()
            console_log.info(
                f"完成: 总请求={stats['request_count']}, "
                f"成功率={stats['success_rate']:.2%}, "
                f"最终参数: buffer={stats['buffer_size']}, concurrency={stats['concurrency']}"
            )
        
        return total_count
    
    async def upsert_buffered(
        self,
        model: Type[ModelType],
        data_generator,
        buffer_size: int = 500,
        **kwargs
    ) -> int:
        """缓冲批量 upsert（简单版本，无并发）
        
        适用于数据量较小或不需要高并发的场景。
        
        Args:
            model: 模型类
            data_generator: 数据生成器
            buffer_size: 缓冲区大小，默认 500
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
        """
        buffer = []
        total_count = 0
        
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= buffer_size:
                result = await self.upsert(model, buffer, **kwargs)
                total_count += result.count()
                buffer = []
        
        # 处理剩余数据
        if buffer:
            result = await self.upsert(model, buffer, **kwargs)
            total_count += result.count()
        
        return total_count
    
    # ==================== 查询操作 ====================
    
    def query(self, model: Type[ModelType]) -> 'AsyncHapQuerySet[ModelType]':
        """获取异步查询集
        
        Args:
            model: 模型类
            
        Returns:
            AsyncHapQuerySet[ModelType]: 异步查询集实例
            
        Example:
            >>> query = async_hap.query(MyModel)
            >>> results = await query.filter(status="active").order_by("-created").all()
        """
        return AsyncHapQuerySet(model, self._sync_conn, self._executor, async_hap=self)
    
    # 兼容 rows 方法名
    def rows(self, model: Type[ModelType]) -> 'AsyncHapQuerySet[ModelType]':
        """获取异步查询集（与 query 方法相同）
        
        Args:
            model: 模型类
            
        Returns:
            AsyncHapQuerySet[ModelType]: 异步查询集实例
        """
        return self.query(model)
    
    # ==================== 缓存操作 ====================
    
    async def get_cached_data(
        self,
        model: Type[ModelType],
        key: Union[str, tuple],
        index_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """异步获取缓存数据
        
        Args:
            model: 模型类
            key: 索引值（主键、rowid 或冲突字段元组）
            index_type: 索引类型，可选 'pk', 'rowid', 'conflict'，默认自动检测
            
        Returns:
            Optional[Dict[str, Any]]: 缓存的数据，不存在则返回 None
        """
        return await self._run_in_executor(
            self._sync_conn.get_cached_data,
            model,
            key,
            index_type
        )
    
    async def warmup_cache(self, model: Type[ModelType]) -> None:
        """异步预热缓存
        
        重新加载模型的缓存数据。
        
        Args:
            model: 模型类
        """
        await self._run_in_executor(self._sync_conn.register_model, model)
    
    # ==================== 选项集操作 ====================
    
    async def get_choice_sets(self) -> Dict[str, Any]:
        """异步获取选项集
        
        Returns:
            Dict[str, Any]: 选项集数据
        """
        return await self._run_in_executor(self._sync_conn.get_choice_sets)
    
    # ==================== 生命周期管理 ====================
    
    async def close(self) -> None:
        """关闭连接，释放资源
        
        关闭线程池，等待所有任务完成。
        """
        self._executor.shutdown(wait=True)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
        return False


class AsyncHapQuerySet(Generic[ModelType]):
    """异步查询集包装器
    
    包装同步的 HapQuerySet，提供异步查询操作。
    链式调用方法（filter, order_by 等）保持同步，
    执行方法（all, first, count 等）改为异步。
    
    Example:
        >>> query = async_hap.query(MyModel)
        >>> query = query.filter(status="active").order_by("-created")
        >>> results = await query.all()
        >>> first = await query.first()
        >>> count = await query.count()
    """
    
    def __init__(
        self, 
        model: Type[ModelType], 
        sync_conn: HapConnection, 
        executor: ThreadPoolExecutor,
        async_hap: 'AsyncHapConnection' = None
    ):
        """
        初始化异步查询集
        
        Args:
            model: 模型类
            sync_conn: 同步 HAP 连接
            executor: 线程池执行器
            async_hap: 异步 HAP 连接实例（用于获取监控器）
        """
        self._model = model
        self._sync_conn = sync_conn
        self._executor = executor
        self._async_hap = async_hap
        self._sync_query = sync_conn.rows(model)
    
    def _run_in_executor(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """在线程池中执行同步函数"""
        loop = asyncio.get_event_loop()
        if kwargs:
            def wrapper():
                return func(*args, **kwargs)
            return loop.run_in_executor(self._executor, wrapper)
        else:
            return loop.run_in_executor(self._executor, func, *args)
    
    # ==================== 链式查询构建（同步）====================
    
    def filter(self, *args, **kwargs) -> 'AsyncHapQuerySet[ModelType]':
        """添加过滤条件
        
        Args:
            *args: Q 对象
            **kwargs: 字段过滤条件，如 name__eq="test"
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.filter(*args, **kwargs)
        return self
    
    def exclude(self, *args, **kwargs) -> 'AsyncHapQuerySet[ModelType]':
        """添加排除条件
        
        Args:
            *args: Q 对象
            **kwargs: 字段排除条件
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.exclude(*args, **kwargs)
        return self
    
    def order_by(self, *fields: str) -> 'AsyncHapQuerySet[ModelType]':
        """设置排序字段
        
        Args:
            *fields: 排序字段，前缀 "-" 表示降序，如 "-created"
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.order_by(*fields)
        return self
    
    def limit(self, n: int) -> 'AsyncHapQuerySet[ModelType]':
        """设置返回数量限制
        
        Args:
            n: 限制数量
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query.limit = n
        return self
    
    def offset(self, n: int) -> 'AsyncHapQuerySet[ModelType]':
        """设置偏移量
        
        Args:
            n: 偏移数量
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query.offset = n
        return self
    
    # ==================== 查询执行（异步）====================
    
    async def all(self) -> HapRowSet[ModelType]:
        """异步获取所有结果
        
        Returns:
            HapRowSet[ModelType]: 查询结果集
        """
        return await self._run_in_executor(self._sync_query.all)
    
    async def first(self) -> Optional[ModelType]:
        """异步获取第一条结果
        
        Returns:
            Optional[ModelType]: 第一个模型实例，不存在则返回 None
        """
        return await self._run_in_executor(self._sync_query.first)
    
    async def count(self) -> int:
        """异步获取记录数
        
        Returns:
            int: 符合条件的记录总数
        """
        return await self._run_in_executor(self._sync_query.count)
    
    async def stream(self, batch_size: int = 100) -> AsyncGenerator[ModelType, None]:
        """异步流式获取结果
        
        分批获取数据，避免内存溢出，适合处理大数据量。
        
        Args:
            batch_size: 每批获取数量，默认 100
            
        Yields:
            ModelType: 模型实例
            
        Example:
            >>> async for item in query.stream(batch_size=50):
            ...     await process_item(item)
        """
        offset = 0
        while True:
            batch_query = self._sync_query.limit(batch_size).offset(offset)
            batch = await self._run_in_executor(batch_query.all)
            
            if not batch.row_objects:
                break
                
            for item in batch.row_objects:
                yield item
                
            if len(batch.row_objects) < batch_size:
                break
                
            offset += batch_size
    
    # ==================== 数据修改（异步）====================
    
    @hap_async_timer()
    async def upsert(
        self,
        data_list: List[Dict[str, Any]],
        exclude_none: bool = True,
        trigger_workflow: bool = True,
        when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
    ) -> HapRowSet[ModelType]:
        """异步 upsert 操作
        
        Args:
            data_list: 要 upsert 的数据列表
            exclude_none: 是否排除值为 None 的字段，默认 True
            trigger_workflow: 是否触发工作流，默认 True
            when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
            
        Returns:
            HapRowSet[ModelType]: 包含 upsert 后模型实例的行集合
        """
        return await self._run_in_executor(
            self._sync_query.upsert,
            data_list,
            exclude_none=exclude_none,
            trigger_workflow=trigger_workflow,
            when_value_equal_then=when_value_equal_then
        )
    
    @hap_async_timer()
    async def bulk_create(
        self,
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量创建
        
        Args:
            data_list: 要创建的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 创建的模型实例列表
        """
        return await self._run_in_executor(
            self._sync_query.bulk_create,
            data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def bulk_update(
        self,
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量更新
        
        Args:
            data_list: 要更新的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 更新的模型实例列表
        """
        return await self._run_in_executor(
            self._sync_query.bulk_update,
            data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def delete(self, trigger_workflow: bool = True) -> bool:
        """异步删除模型实例
        
        Args:
            trigger_workflow: 是否触发工作流
            
        Returns:
            bool: 删除是否成功
        """
        return await self._run_in_executor(self._sync_query.delete, trigger_workflow)
    
    async def bulk_upsert(
        self,
        data_list: List[Dict[str, Any]],
        batch_size: int = 100,
        **kwargs
    ) -> List[ModelType]:
        """批量 upsert，分批处理大数据量
        
        Args:
            data_list: 要 upsert 的数据列表
            batch_size: 每批处理数量，默认 100
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            List[ModelType]: 处理后的模型实例列表
        """
        results = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i+batch_size]
            if batch:
                batch_result = await self.upsert(batch, **kwargs)
                results.extend(batch_result.row_objects)
        return results
    
    async def bulk_upsert_parallel(
        self,
        data_list: List[Dict[str, Any]],
        batch_size: int = 100,
        max_concurrency: int = _MAX_CONCURRENCY
    ) -> List[ModelType]:
        """并行批量 upsert，提高处理速度
        
        Args:
            data_list: 要 upsert 的数据列表
            batch_size: 每批处理数量，默认 100
            max_concurrency: 最大并发数，默认 _MAX_CONCURRENCY
            
        Returns:
            List[ModelType]: 处理后的模型实例列表
        """
        # 分批次
        batches = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i+batch_size]
            if batch:
                batches.append(batch)
        
        # 并行处理
        results = []
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def process_batch(batch):
            async with semaphore:
                batch_result = await self.upsert(batch)
                return batch_result.row_objects
        
        tasks = [process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*tasks)
        
        for batch_result in batch_results:
            results.extend(batch_result)
        
        return results

    @hap_async_timer()
    async def upsert_from_generator(
        self,
        data_source,
        buffer_size: int = None,
        max_concurrency: int = None,
        max_retries: int = None,
        retry_delay: float = None,
        adaptive: bool = True,
        target_qps: float = None,
        **kwargs
    ) -> int:
        """从生成器函数批量 upsert 数据（高性能版本）
        
        针对数据同步场景优化，支持批量收集和并发处理。
        包含错误处理、重试机制和自适应速率控制。
        
        Args:
            data_source: 数据生成器函数，每次调用返回一个数据列表的生成器
            buffer_size: 缓冲区大小，None 时使用自适应调节
            max_concurrency: 最大并发数，None 时使用自适应调节
            max_retries: 最大重试次数，None 时使用配置默认值
            retry_delay: 重试延迟（秒），None 时使用配置默认值
            adaptive: 是否启用自适应速率控制，默认 True
            target_qps: 目标 QPS（每秒请求数），None 时自动从 HapConfig 获取
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
            
        Example:
            >>> # 自适应模式（推荐，自动从 HapConfig 获取 QPS）
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(data_gen_func)
            >>> 
            >>> # 固定参数模式
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(
            ...     data_gen_func, buffer_size=200, max_concurrency=20
            ... )
        """
        import logging
        import time
        from typing import Callable, Generator
        
        model = self._model
        
        if callable(data_source):
            data_generator = data_source()
        else:
            raise ValueError("data_source 必须是生成器函数，请传递函数名而非函数调用结果")
        
        if max_retries is None:
            max_retries = _DEFAULT_MAX_RETRIES
        if retry_delay is None:
            retry_delay = _DEFAULT_RETRY_DELAY
        
        if target_qps is None:
            target_qps = getattr(self._sync_conn, 'qps_limit', 10.0)
            console_log.info(f"从 HapConfig 自动获取 QPS 限制: {target_qps}")
        
        smart_batch_calculator = getattr(self._sync_conn, '_batch_size_calculator', None)
        
        if adaptive:
            if buffer_size is None and smart_batch_calculator:
                initial_buffer = _DEFAULT_BUFFER_SIZE
            else:
                initial_buffer = buffer_size or _DEFAULT_BUFFER_SIZE
            
            controller = AdaptiveRateController(
                initial_buffer_size=initial_buffer,
                initial_concurrency=max_concurrency or _MAX_CONCURRENCY,
                target_qps=target_qps,
            )
            current_buffer_size = controller.buffer_size
            current_concurrency = controller.concurrency
        else:
            if buffer_size is None and smart_batch_calculator:
                current_buffer_size = _DEFAULT_BUFFER_SIZE
            else:
                current_buffer_size = buffer_size or _DEFAULT_BUFFER_SIZE
            current_concurrency = max_concurrency or _MAX_CONCURRENCY
        
        buffer = []
        total_count = 0
        semaphore = asyncio.Semaphore(current_concurrency)
        tasks = []
        
        async def do_upsert_with_retry(data_batch, batch_index):
            nonlocal current_buffer_size, current_concurrency, semaphore
            
            async with semaphore:
                start_time = time.time()
                for attempt in range(max_retries):
                    try:
                        result = await self.upsert(data_batch, **kwargs)
                        response_time = time.time() - start_time
                        
                        if adaptive:
                            controller.record_request(True, response_time)
                        
                        if self._async_hap and self._async_hap._monitor:
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._async_hap._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=True
                            )
                        
                        return result.count()
                    except Exception as e:
                        response_time = time.time() - start_time
                        console_log.warning(f"批次 {batch_index} 第 {attempt + 1} 次尝试失败: {e}")
                        
                        if adaptive:
                            controller.record_request(False, response_time)
                        
                        if self._async_hap and self._async_hap._monitor:
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._async_hap._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=False,
                                error=str(e)
                            )
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                        else:
                            console_log.error(f"批次 {batch_index} 最终失败，跳过 {len(data_batch)} 条数据")
                            return 0
                return 0
        
        batch_index = 0
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= current_buffer_size:
                batch_index += 1
                
                if adaptive and batch_index % 5 == 0:
                    new_buffer_size, new_concurrency = controller.adjust()
                    
                    if new_concurrency != current_concurrency:
                        current_concurrency = new_concurrency
                        semaphore = asyncio.Semaphore(current_concurrency)
                        console_log.info(f"自适应调整: 并发数 -> {current_concurrency}")
                    
                    if new_buffer_size != current_buffer_size:
                        current_buffer_size = new_buffer_size
                        console_log.info(f"自适应调整: 缓冲区 -> {current_buffer_size}")
                    
                    if batch_index % 20 == 0:
                        stats = controller.get_stats()
                        console_log.info(
                            f"统计: 成功率={stats['success_rate']:.2%}, "
                            f"平均响应={stats['avg_response_time']:.2f}s, "
                            f"当前参数: buffer={current_buffer_size}, concurrency={current_concurrency}"
                        )
                
                tasks.append(asyncio.create_task(
                    do_upsert_with_retry(buffer[:], batch_index)
                ))
                buffer = []
                
                if len(tasks) >= current_concurrency * 2:
                    done, pending = await asyncio.wait(
                        tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        try:
                            total_count += await task
                        except Exception as e:
                            console_log.error(f"任务执行失败: {e}")
                    tasks = list(pending)
        
        if buffer:
            batch_index += 1
            tasks.append(asyncio.create_task(
                do_upsert_with_retry(buffer, batch_index)
            ))
        
        if tasks:
            done, _ = await asyncio.wait(tasks)
            for task in done:
                try:
                    total_count += await task
                except Exception as e:
                    console_log.error(f"任务执行失败: {e}")
        
        console_log.info(f"upsert_from_generator 完成，总处理 {total_count} 条记录")
        return total_count


# ==================== 便捷函数 ====================

async def async_upsert(
    model: Type[ModelType],
    data_list: List[Dict[str, Any]],
    sync_conn: Optional[HapConnection] = None,
    **kwargs
) -> HapRowSet[ModelType]:
    """便捷函数：快速 upsert
    
    无需创建 AsyncHapConnection 实例，直接调用 upsert。
    
    Args:
        model: 模型类
        data_list: 要 upsert 的数据列表
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        **kwargs: 其他参数传递给 upsert 方法
        
    Returns:
        HapRowSet[ModelType]: upsert 结果
        
    Example:
        >>> result = await async_upsert(MyModel, [{"name": "test"}])
    """
    if sync_conn is None:
        # 尝试从 hap 模块获取全局连接
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    try:
        return await async_hap.upsert(model, data_list, **kwargs)
    finally:
        await async_hap.close()


async def async_bulk_create(
    model: Type[ModelType],
    data_list: List[Dict[str, Any]],
    sync_conn: Optional[HapConnection] = None,
    **kwargs
) -> List[ModelType]:
    """便捷函数：快速批量创建
    
    Args:
        model: 模型类
        data_list: 要创建的数据列表
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        **kwargs: 其他参数传递给 bulk_create 方法
        
    Returns:
        List[ModelType]: 创建的模型实例列表
    """
    if sync_conn is None:
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    try:
        return await async_hap.bulk_create(model, data_list, **kwargs)
    finally:
        await async_hap.close()


async def async_query(
    model: Type[ModelType],
    sync_conn: Optional[HapConnection] = None
) -> 'AsyncHapQuerySet[ModelType]':
    """便捷函数：快速获取查询集
    
    Args:
        model: 模型类
        sync_conn: HAP 连接实例，为 None 时尝试从全局获取
        
    Returns:
        AsyncHapQuerySet[ModelType]: 异步查询集
    """
    if sync_conn is None:
        from .hap import hap_conn as _hap_conn
        sync_conn = _hap_conn
    
    async_hap = AsyncHapConnection(sync_conn)
    return async_hap.query(model)


###

if __name__ == "__main__":
    """
    ============================================================================
    使用示例
    ============================================================================

    异步版本调用方式与同步版本保持一致，只需添加 await 关键字。

    与同步版本的对比：
    -------------------------------------------------------------------------
    同步版本:                |  异步版本:
    ----------------------- | -----------------------
    hap_conn.rows(Model)    |  await async_hap.rows(Model)
    .upsert(data_list)      |  .upsert(data_list)
    .filter(...).all()      |  .filter(...).all()
    .bulk_create(data_list) |  .bulk_create(data_list)
    .bulk_update(data_list) |  .bulk_update(data_list)
    .delete()               |  .delete()
    -------------------------------------------------------------------------

    示例代码：
    -------------------------------------------------------------------------
    """
    import asyncio

    class MyModel(Model):
        class Meta:
            worksheet_id = "your_worksheet_id"
            primary_field = "id"

        id = StrField(field_name="ID")
        name = StrField(field_name="Name")
        status = StrField(field_name="Status")
        amount = NumField(field_name="Amount")

    async def main():
        hap_conn = HapConnection()
        async_hap = AsyncHapConnection(hap_conn)

        results = await async_hap.rows(MyModel).all()

        results = await async_hap.rows(MyModel).filter(
            status="active"
        ).all()

        results = await async_hap.rows(MyModel).filter(
            status="active",
            amount__gt=1000
        ).order_by("-created").all()

        first = await async_hap.rows(MyModel).filter(id="123").first()

        count = await async_hap.rows(MyModel).filter(status="active").count()

        results = await async_hap.rows(MyModel).filter(
            status="active"
        ).limit(10).offset(20).all()

        result = await async_hap.rows(MyModel).upsert([
            {"id": "1", "name": "张三", "status": "active", "amount": 1000},
            {"id": "2", "name": "李四", "status": "inactive", "amount": 2000},
        ])
        print(f"处理了 {result.count()} 条记录")

        created = await async_hap.rows(MyModel).bulk_create([
            {"name": "王五", "status": "active", "amount": 3000},
            {"name": "赵六", "status": "active", "amount": 4000},
        ])

        updated = await async_hap.rows(MyModel).bulk_update([
            {"row_id": "123", "name": "张三（已更新）", "amount": 1500},
            {"row_id": "456", "name": "李四（已更新）", "amount": 2500},
        ])

        success = await async_hap.rows(MyModel).filter(
            status="deleted"
        ).all().delete()

        # 从生成器函数批量 upsert（高性能版本）
        def data_generator():
            for i in range(1000):
                yield [{"id": str(i), "name": f"用户{i}", "status": "active"}]

        count = await async_hap.rows(MyModel).upsert_from_generator(
            data_generator,
            adaptive=True,
            target_qps=50
        )
        print(f"从生成器处理了 {count} 条记录")

        result = await async_hap.upsert(MyModel, [
            {"id": "1", "name": "测试"}
        ])
        created = await async_hap.bulk_create(MyModel, [
            {"name": "测试1"},
            {"name": "测试2"},
        ])
        updated = await async_hap.bulk_update(MyModel, [
            {"row_id": "123", "name": "已更新"}
        ])

        stats = async_hap.get_monitor_stats(last_n=100)
        print(f"总请求数: {stats['total']}")
        print(f"成功率: {stats['success_rate']}")
        print(f"平均响应时间: {stats['avg_response_time']:.2f}s")

        errors = async_hap.get_recent_errors(limit=10)

        await async_hap.close()

    asyncio.run(main())