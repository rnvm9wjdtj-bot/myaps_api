"""
异步处理组件

HAP API v3 的异步包装器，使用线程池将同步操作转换为异步操作，
避免在 FastAPI 等异步框架中阻塞事件循环。

使用方式：
    1. 后端直接调用：await async_hap.upsert(Model, data_list)
    2. API 接口触发：通过 FastAPI 路由调用

示例：
    >>> from apps.data_opt.components.async_hap import AsyncHapConnection
    >>> from apps.data_opt.components.hap import hap_conn, MyModel
    >>> async_hap = AsyncHapConnection(hap_conn)
    >>> result = await async_hap.upsert(MyModel, [{"name": "test"}])
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import (
    List, Dict, Any, Optional, Type, TypeVar, Generic, 
    Callable, Union, Literal, Generator, AsyncGenerator
)

from .hap import (
    HapConfig, HapConnection, HapQuerySet, HapRowSet, Model, Q, Field,
    StrField, NumField, RelationField, SubtableField, ChoiceField,
)

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
        min_buffer_size: int = 50,
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
            min_buffer_size: 最小缓冲区大小
            max_buffer_size: 最大缓冲区大小，None 时根据 QPS 自动计算
            min_concurrency: 最小并发数
            max_concurrency: 最大并发数，None 时根据 QPS 自动计算
            target_qps: 目标 QPS（每秒请求数）
            adjustment_interval: 调整间隔（每 N 个请求调整一次）
        """
        # 根据 QPS 自动计算参数
        if initial_buffer_size is None:
            initial_buffer_size = min(500, max(100, int(target_qps * 5)))
        if initial_concurrency is None:
            initial_concurrency = min(10, max(2, int(target_qps / 10)))
        if max_buffer_size is None:
            max_buffer_size = min(1000, max(300, int(target_qps * 10)))
        if max_concurrency is None:
            max_concurrency = min(20, max(5, int(target_qps / 5)))
        
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
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * 1.5))
                # 大幅增加并发（提高吞吐量）
                new_concurrency = min(self.max_concurrency, self.concurrency + 2)
            
            # 成功率一般但 QPS 远低于目标 -> 温和提速
            elif success_rate > 0.85 and current_qps < self.target_qps * 0.5:
                # 增加缓冲区
                new_buffer_size = min(self.max_buffer_size, int(self.buffer_size * 1.3))
                # 增加并发
                new_concurrency = min(self.max_concurrency, self.concurrency + 1)
            
            # 成功率低或响应时间过长 -> 降速
            elif success_rate < 0.75 or avg_response_time > 10.0:
                # 减小缓冲区（更频繁但更小的请求）
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * 0.7))
                # 减少并发（降低服务器压力）
                new_concurrency = max(self.min_concurrency, self.concurrency - 1)
            
            # 连续失败 -> 大幅降速
            elif len(self.recent_failures) >= 3:
                new_buffer_size = max(self.min_buffer_size, int(self.buffer_size * 0.5))
                new_concurrency = self.min_concurrency
            
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
    
    Attributes:
        _sync_conn: 原始的同步 HAP 连接
        _executor: 线程池执行器
        _max_workers: 最大工作线程数
    
    Example:
        >>> hap_conn = HapConnection(app_key="xxx", sign="yyy")
        >>> async_hap = AsyncHapConnection(hap_conn, max_workers=20)
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
        max_workers: int = None,
        enable_monitor: bool = True
    ):
        """
        初始化异步 HAP 连接
        
        Args:
            sync_conn: 同步 HAP 连接实例
            max_workers: 线程池最大工作线程数，默认自动计算（CPU核心数 * 5）
            enable_monitor: 是否启用 API 监控，默认 True
        """
        import os
        self._sync_conn = sync_conn
        # 自动计算线程池大小
        if max_workers is None:
            max_workers = os.cpu_count() * 5 if os.cpu_count() else 20
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        # 缓存常用操作的函数引用
        self._func_cache = {}
        # 初始化监控器
        self._monitor = HapApiMonitor() if enable_monitor else None
        
        # 连接池预热（复用同步版本的预热器）
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
    
    async def upsert_from_generator(
        self,
        model: Type[ModelType],
        data_generator,
        buffer_size: int = None,
        max_concurrency: int = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        adaptive: bool = True,
        target_qps: float = None,
        **kwargs
    ) -> int:
        """从生成器批量 upsert 数据（高性能版本）
        
        针对 `pull_incremental_data` 等场景优化，支持批量收集和并发处理。
        包含错误处理、重试机制和自适应速率控制。
        
        Args:
            model: 模型类
            data_generator: 数据生成器，每次 yield 一个数据列表
            buffer_size: 缓冲区大小，None 时使用自适应调节
            max_concurrency: 最大并发数，None 时使用自适应调节
            max_retries: 最大重试次数，默认 3
            retry_delay: 重试延迟（秒），默认 1.0
            adaptive: 是否启用自适应速率控制，默认 True
            target_qps: 目标 QPS（每秒请求数），None 时自动从 HapConfig 获取
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
            
        Example:
            >>> # 自适应模式（推荐，自动从 HapConfig 获取 QPS）
            >>> count = await async_hap.upsert_from_generator(
            ...     MyModel, data_gen, adaptive=True
            ... )
            >>> 
            >>> # 固定参数模式
            >>> count = await async_hap.upsert_from_generator(
            ...     MyModel, data_gen, buffer_size=200, max_concurrency=2
            ... )
        """
        import logging
        import time
        logger = logging.getLogger(__name__)
        
        # 自动从 HapConfig 获取 QPS 限制
        if target_qps is None:
            target_qps = getattr(self._sync_conn, 'qps_limit', 10.0)
            logger.info(f"从 HapConfig 自动获取 QPS 限制: {target_qps}")
        
        # 使用智能批处理大小计算器（如果同步版本已配置）
        smart_batch_calculator = getattr(self._sync_conn, '_batch_size_calculator', None)
        
        # 初始化自适应控制器
        if adaptive:
            # 如果提供了 buffer_size，使用提供的值；否则使用智能计算
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值初始化，后续根据实际数据量调整
                initial_buffer = 200
            else:
                initial_buffer = buffer_size or 200
            
            controller = AdaptiveRateController(
                initial_buffer_size=initial_buffer,
                initial_concurrency=max_concurrency or 2,
                target_qps=target_qps,
            )
            current_buffer_size = controller.buffer_size
            current_concurrency = controller.concurrency
        else:
            # 非自适应模式，使用智能批处理大小
            if buffer_size is None and smart_batch_calculator:
                # 先使用默认值，后续根据实际数据调整
                current_buffer_size = 200
            else:
                current_buffer_size = buffer_size or 200
            current_concurrency = max_concurrency or 2
        
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
                        logger.warning(f"批次 {batch_index} 第 {attempt + 1} 次尝试失败: {e}")
                        
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
                            logger.error(f"批次 {batch_index} 最终失败，跳过 {len(data_batch)} 条数据")
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
                        logger.info(f"自适应调整: 并发数 -> {current_concurrency}")
                    
                    if new_buffer_size != current_buffer_size:
                        current_buffer_size = new_buffer_size
                        logger.info(f"自适应调整: 缓冲区 -> {current_buffer_size}")
                    
                    # 定期输出统计信息
                    if batch_index % 20 == 0:
                        stats = controller.get_stats()
                        logger.info(
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
                            logger.error(f"任务执行失败: {e}")
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
                    logger.error(f"任务异常: {result}")
        
        # 输出最终统计
        if adaptive:
            stats = controller.get_stats()
            logger.info(
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
        return AsyncHapQuerySet(model, self._sync_conn, self._executor)
    
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
        executor: ThreadPoolExecutor
    ):
        """
        初始化异步查询集
        
        Args:
            model: 模型类
            sync_conn: 同步 HAP 连接
            executor: 线程池执行器
        """
        self._model = model
        self._sync_conn = sync_conn
        self._executor = executor
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
    
    async def delete(self, row_ids: List[str]) -> bool:
        """异步删除记录
        
        Args:
            row_ids: 要删除的行 ID 列表
            
        Returns:
            bool: 是否删除成功
        """
        return await self._run_in_executor(self._sync_query.delete, row_ids)
    
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
        max_concurrency: int = 5
    ) -> List[ModelType]:
        """并行批量 upsert，提高处理速度
        
        Args:
            data_list: 要 upsert 的数据列表
            batch_size: 每批处理数量，默认 100
            max_concurrency: 最大并发数，默认 5
            
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


if __name__ == "__main__":
    """
    ============================================================================
    使用示例
    ============================================================================
    """
    import asyncio
    
    # -------------------------------------------------------------------------
    # 示例 1: 后端直接调用（定时任务、消息队列等）
    # -------------------------------------------------------------------------
    async def example_direct_call():
        """后端直接调用示例"""
        from .hap import hap_conn, MyModel
        
        # 创建异步连接
        async_hap = AsyncHapConnection(hap_conn, max_workers=20)
        
        # 方式 1: 直接调用 upsert
        result = await async_hap.upsert(
            model=MyModel,
            data_list=[
                {"id": "1", "name": "张三", "status": "active"},
                {"id": "2", "name": "李四", "status": "inactive"},
            ],
            exclude_none=True,
            trigger_workflow=True,
            when_value_equal_then='jumpover'
        )
        print(f"Upsert 完成，处理了 {result.count()} 条记录")
        
        # 方式 2: 批量创建
        created = await async_hap.bulk_create(
            model=MyModel,
            data_list=[
                {"name": "王五", "email": "wangwu@example.com"},
                {"name": "赵六", "email": "zhaoliu@example.com"},
            ],
            trigger_workflow=False
        )
        print(f"批量创建完成，创建了 {len(created)} 条记录")
        
        # 方式 3: 使用查询集
        query = async_hap.query(MyModel).filter(status__eq="active").order_by("-created")
        active_users = await query.all()
        print(f"活跃用户数: {active_users.count()}")
        
        # 方式 4: 流式查询（大数据量）
        async for item in query.stream(batch_size=100):
            print(f"处理: {item.name}")
        
        # 关闭连接
        await async_hap.close()
    
    
    # -------------------------------------------------------------------------
    # 示例 2: FastAPI 路由中使用
    # -------------------------------------------------------------------------
    """
    # api.py
    from fastapi import APIRouter
    from apps.data_opt.components.async_hap import AsyncHapConnection
    from apps.data_opt.components.hap import hap_conn, MyModel
    
    router = APIRouter()
    async_hap = AsyncHapConnection(hap_conn)
    
    @router.post("/api/sync-data")
    async def sync_data_endpoint(data: list[dict]):
        # 异步 upsert，不会阻塞事件循环
        result = await async_hap.upsert(MyModel, data)
        return {"success": True, "count": result.count()}
    
    @router.get("/api/query")
    async def query_data(status: str = None, limit: int = 100):
        query = async_hap.query(MyModel)
        if status:
            query = query.filter(status__eq=status)
        results = await query.limit(limit).order_by("-created").all()
        return {
            "total": results.count(),
            "data": [item.to_dict() for item in results.row_objects]
        }
    """
    
    
    # -------------------------------------------------------------------------
    # 示例 3: 上下文管理器（推荐）
    # -------------------------------------------------------------------------
    async def example_context_manager():
        """使用上下文管理器自动管理资源"""
        from .hap import hap_conn, ModelA, ModelB
        
        async with AsyncHapConnection(hap_conn, max_workers=10) as async_hap:
            # 并行执行多个操作
            results = await asyncio.gather(
                async_hap.upsert(ModelA, [{"name": "test1"}]),
                async_hap.bulk_create(ModelB, [{"name": "test2"}]),
                async_hap.query(ModelA).filter(status="active").count(),
            )
            print(f"操作 1: {results[0].count()} 条")
            print(f"操作 2: 创建了 {len(results[1])} 条")
            print(f"操作 3: 共 {results[2]} 条记录")
    
    
    # -------------------------------------------------------------------------
    # 示例 4: 便捷函数（快速使用）
    # -------------------------------------------------------------------------
    async def example_quick_functions():
        """使用便捷函数快速操作"""
        from .hap import MyModel
        
        # 一行代码 upsert
        result = await async_upsert(
            MyModel,
            [{"id": "1", "name": "快速测试"}],
            trigger_workflow=False
        )
        
        # 一行代码批量创建
        created = await async_bulk_create(
            MyModel,
            [{"name": "用户1"}, {"name": "用户2"}]
        )
        
        # 一行代码查询
        query = await async_query(MyModel)
        results = await query.filter(name__contains="测试").all()
    
    
    # -------------------------------------------------------------------------
    # 示例 5: 定时任务（APScheduler）
    # -------------------------------------------------------------------------
    """
    # tasks.py
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apps.data_opt.components.async_hap import AsyncHapConnection
    from apps.data_opt.components.hap import hap_conn, SyncModel
    
    scheduler = AsyncIOScheduler()
    async_hap = AsyncHapConnection(hap_conn)
    
    async def daily_sync_job():
        # 从外部系统获取数据
        external_data = await fetch_from_external_api()
        
        # 同步到 HAP（非阻塞）
        result = await async_hap.upsert(
            SyncModel,
            external_data,
            when_value_equal_then='update'
        )
        print(f"[定时任务] 同步完成: {result.count()} 条")
    
    # 每天凌晨 2 点执行
    scheduler.add_job(daily_sync_job, 'cron', hour=2, minute=0)
    scheduler.start()
    """
    
    
    # -------------------------------------------------------------------------
    # 示例 6: 消息队列（Celery）
    # -------------------------------------------------------------------------
    """
    # celery_tasks.py
    from celery import Celery
    import asyncio
    from apps.data_opt.components.async_hap import AsyncHapConnection
    from apps.data_opt.components.hap import hap_conn, TaskModel
    
    celery_app = Celery('tasks')
    async_hap = AsyncHapConnection(hap_conn)
    
    @celery_app.task
    def process_hap_data(data_list: list):
        # Celery 是同步的，需要包装异步调用
        asyncio.run(_process_async(data_list))
    
    async def _process_async(data_list):
        result = await async_hap.bulk_create(TaskModel, data_list)
        return f"创建了 {len(result)} 条记录"
    """
    
    
    # -------------------------------------------------------------------------
    # 示例 7: 复杂查询
    # -------------------------------------------------------------------------
    async def example_complex_query():
        """复杂查询示例"""
        from .hap import hap_conn, MyModel, Q
        
        async_hap = AsyncHapConnection(hap_conn)
        
        # 使用 Q 对象构建复杂条件
        query = async_hap.query(MyModel).filter(
            Q(status__eq="active") & 
            (Q(name__contains="测试") | Q(email__contains="test"))
        ).exclude(is_deleted__eq=True).order_by("-created", "name")
        
        # 分页查询
        page1 = await query.limit(20).offset(0).all()
        page2 = await query.limit(20).offset(20).all()
        
        # 获取总数
        total = await query.count()
        
        print(f"总记录数: {total}, 第一页: {page1.count()}, 第二页: {page2.count()}")
        
        await async_hap.close()
    
    
    # -------------------------------------------------------------------------
    # 示例 8: 缓存操作
    # -------------------------------------------------------------------------
    async def example_cache_operations():
        """缓存操作示例"""
        from .hap import hap_conn, CachedModel
        
        async_hap = AsyncHapConnection(hap_conn)
        
        # 预热缓存
        await async_hap.warmup_cache(CachedModel)
        
        # 从缓存获取数据
        cached = await async_hap.get_cached_data(
            CachedModel,
            key="record_id_123",
            index_type="pk"
        )
        
        if cached:
            print(f"缓存命中: {cached}")
        else:
            print("缓存未命中")
        
        await async_hap.close()
    
    
    # -------------------------------------------------------------------------
    # 示例 9: API 监控
    # -------------------------------------------------------------------------
    async def example_monitoring():
        """API 监控示例"""
        from .hap import hap_conn, MyModel
        
        # 创建异步连接（默认启用监控）
        async_hap = AsyncHapConnection(hap_conn, enable_monitor=True)
        
        # 执行一些操作
        await async_hap.upsert(MyModel, [{"name": "test1"}, {"name": "test2"}])
        await async_hap.query(MyModel).filter(name="test").all()
        
        # 获取监控统计
        stats = async_hap.get_monitor_stats(last_n=100)
        print(f"总请求数: {stats['total']}")
        print(f"成功率: {stats['success_rate']:.2%}")
        print(f"平均响应时间: {stats['avg_response_time']:.2f}s")
        print(f"各端点统计: {stats['endpoint_stats']}")
        
        # 获取最近的错误
        errors = async_hap.get_recent_errors(limit=5)
        if errors:
            print(f"最近的错误: {len(errors)} 条")
            for error in errors:
                print(f"  - {error['endpoint']}: {error['error']}")
        
        # 清空监控数据
        async_hap.clear_monitor()
        
        await async_hap.close()
    
    
    # 运行示例
    # asyncio.run(example_direct_call())
    # asyncio.run(example_context_manager())
    # asyncio.run(example_quick_functions())
    # asyncio.run(example_complex_query())
    # asyncio.run(example_cache_operations())
    # asyncio.run(example_monitoring())
    
    pass