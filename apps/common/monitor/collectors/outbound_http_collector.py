"""
对外 HTTP 请求收集器

收集和管理所有外发 HTTP 请求的指标和详细信息
"""

import time
import asyncio
import json
import threading
from typing import Dict, Any, List
from collections import deque, defaultdict
from datetime import datetime, timezone
from ..storage import outbound_request_storage
from ..models import is_internal_url


class OutboundHTTPCollector:
    """对外 HTTP 请求收集器（单例模式）"""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_requests: int = 1000, slow_threshold: float = 1.0, max_url_stats: int = 1000, max_module_stats: int = 100):
        """
        初始化对外 HTTP 请求收集器

        Args:
            max_requests: 最大存储的请求数
            slow_threshold: 慢请求阈值（秒）
            max_url_stats: URL统计最大条目数
            max_module_stats: 模块统计最大条目数
        """
        if not self._initialized:
            self._max_requests = max_requests
            self._slow_threshold = slow_threshold
            self._max_url_stats = max_url_stats
            self._max_module_stats = max_module_stats
            self._requests: deque = deque(maxlen=max_requests)
            self._stats = {
                "total_requests": 0,
                "total_errors": 0,
                "total_slow_requests": 0,
                "url_stats": defaultdict(lambda: {
                    "count": 0,
                    "total_time": 0.0,
                    "errors": 0,
                    "slow_requests": 0,
                }),
                "status_codes": defaultdict(int),
                "module_stats": defaultdict(lambda: {
                    "count": 0,
                    "total_time": 0.0,
                    "errors": 0,
                }),
            }
            self._lock = None  # 延迟初始化锁，确保绑定到正确的事件循环
            self._thread_lock = threading.Lock()
            
            # 批量保存相关配置
            self._batch_size = 50  # 批量保存的请求数量阈值
            self._batch_timeout = 5.0  # 批量保存的超时时间（秒）
            self._pending_requests: deque = deque(maxlen=5000)  # 待批量保存的请求队列
            
            # 信号量限制并发数据库操作
            self._db_semaphore = asyncio.Semaphore(10)  # 最多10个并发数据库操作
            
            # 降级模式标志
            self._degraded_mode = False  # 数据库繁忙时启用降级模式
            self._degraded_counter = 0  # 连续失败计数
            
            self._initialized = True
            self._batch_task = None  # 批量保存定时任务
            self._last_batch_time = time.time()  # 上次批量保存时间
            
    def _get_lock(self):
        """
        获取锁，确保锁绑定到当前事件循环
        """
        if self._lock is None or self._lock._loop is not asyncio.get_event_loop():
            self._lock = asyncio.Lock()
        return self._lock

    async def record_request(
        self,
        method: str,
        url: str,
        status_code: int,
        duration: float,
        request_headers: Dict[str, str],
        request_body: Any,
        response_headers: Dict[str, str] = None,
        response_body: Any = None,
        error_message: str = None,
        module: str = None,
    ):
        """
        记录对外 HTTP 请求信息

        Args:
            method: HTTP 方法
            url: 请求 URL
            status_code: 响应状态码
            duration: 响应时间（秒）
            request_headers: 请求头
            request_body: 请求体
            response_headers: 响应头
            response_body: 响应体
            error_message: 错误信息
            module: 发起请求的模块
        """
        # 限制请求体和响应体大小（不持有锁）
        max_size = 1024 * 1024 * 5  # 5MB
        try:
            if request_body is not None:
                if isinstance(request_body, (dict, list)):
                    request_body = json.dumps(request_body, ensure_ascii=False)[:max_size]
                elif isinstance(request_body, str):
                    request_body = request_body[:max_size]
        except:
            request_body = str(request_body)[:max_size] if request_body is not None else None

        try:
            if response_body is not None:
                if isinstance(response_body, (dict, list)):
                    response_body = json.dumps(response_body, ensure_ascii=False)[:max_size]
                elif isinstance(response_body, str):
                    response_body = response_body[:max_size]
        except:
            response_body = str(response_body)[:max_size] if response_body is not None else None

        # 构建请求信息
        timestamp = time.time()
        is_error = bool(status_code >= 400 or error_message)
        is_slow = duration >= self._slow_threshold
        is_internal = is_internal_url(url)

        request_info = {
            "timestamp": timestamp,
            "method": method,
            "url": url,
            "status_code": status_code,
            "duration": duration,
            "request_headers": request_headers,
            "request_body": request_body,
            "response_headers": response_headers,
            "response_body": response_body,
            "error_message": error_message,
            "module": module,
            "is_error": is_error,
            "is_slow": is_slow,
            "is_internal": is_internal,
        }

        # 更新内存统计（持有锁，但只做轻量级操作）
        async with self._get_lock():
            self._requests.append(request_info)

            # 更新统计
            self._stats["total_requests"] += 1
            if is_error:
                self._stats["total_errors"] += 1
            if is_slow:
                self._stats["total_slow_requests"] += 1

            # URL 统计
            url_key = f"{method} {url}"
            self._stats["url_stats"][url_key]["count"] += 1
            self._stats["url_stats"][url_key]["total_time"] += duration
            if is_error:
                self._stats["url_stats"][url_key]["errors"] += 1
            if is_slow:
                self._stats["url_stats"][url_key]["slow_requests"] += 1

            # 状态码统计
            self._stats["status_codes"][status_code] += 1

            # 模块统计
            if module:
                self._stats["module_stats"][module]["count"] += 1
                self._stats["module_stats"][module]["total_time"] += duration
                if is_error:
                    self._stats["module_stats"][module]["errors"] += 1

            # 定期清理统计（使用计数器避免每次都清理）
            self._cleanup_counter = getattr(self, '_cleanup_counter', 0) + 1
            if self._cleanup_counter >= 100:  # 每100次请求清理一次
                self._cleanup_counter = 0
                self._cleanup_stats()

        # 异步保存到数据库（使用信号量和批量机制）
        if not self._degraded_mode:
            # 正常模式：将请求加入待批量保存队列
            self._pending_requests.append({
                "timestamp": timestamp,
                "method": method,
                "url": url,
                "status_code": status_code,
                "duration": duration,
                "request_headers": request_headers,
                "request_body": request_body,
                "response_headers": response_headers,
                "response_body": response_body,
                "error_message": error_message,
                "module": module,
                "is_error": is_error,
                "is_slow": is_slow,
                "is_internal": is_internal,
            })
            
            # 检查是否需要触发批量保存
            if len(self._pending_requests) >= self._batch_size:
                asyncio.create_task(self._flush_batch())
            elif time.time() - self._last_batch_time >= self._batch_timeout:
                asyncio.create_task(self._flush_batch())
        else:
            # 降级模式：只打印日志，不保存到数据库
            print(f"降级模式：跳过保存请求 {method} {url}")

    async def _flush_batch(self):
        """批量保存待处理的请求到数据库"""
        if not self._pending_requests:
            return
            
        async with self._db_semaphore:
            batch_to_save = list(self._pending_requests)
            self._pending_requests.clear()
            self._last_batch_time = time.time()
            
            try:
                requests_data = []
                for req in batch_to_save:
                    requests_data.append({
                        "timestamp": datetime.fromtimestamp(req["timestamp"], timezone.utc),
                        "method": req["method"],
                        "url": req["url"],
                        "status_code": req["status_code"],
                        "duration": req["duration"],
                        "request_headers": json.dumps(req["request_headers"]) if req["request_headers"] else None,
                        "request_body": req["request_body"],
                        "response_headers": json.dumps(req["response_headers"]) if req["response_headers"] else None,
                        "response_body": req["response_body"],
                        "error_message": req["error_message"],
                        "module": req["module"],
                        "is_error": req["is_error"],
                        "is_slow": req["is_slow"],
                        "is_internal": req["is_internal"],
                    })
                
                await outbound_request_storage.save_requests(requests_data)
                
                # 批量保存成功后，重置降级相关状态
                if self._degraded_mode:
                    self._degraded_counter = 0
                    print("数据库恢复正常，退出降级模式")
                
            except Exception as e:
                print(f"批量保存请求到数据库失败: {e}")
                self._degraded_counter += 1
                
                # 连续失败5次后进入降级模式
                if self._degraded_counter >= 5:
                    self._degraded_mode = True
                    print("数据库连续失败，进入降级模式：只保存内存数据，不再写入数据库")
                
                # 将未保存的请求重新放回队列
                for req in batch_to_save:
                    if len(self._pending_requests) < 5000:
                        self._pending_requests.append(req)

    def _cleanup_stats(self):
        """清理统计信息，避免无限增长（必须在锁内调用）"""
        # 清理 URL 统计
        if len(self._stats["url_stats"]) > self._max_url_stats:
            sorted_urls = sorted(
                self._stats["url_stats"].items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )
            for url_key, _ in sorted_urls[self._max_url_stats:]:
                del self._stats["url_stats"][url_key]

        # 清理模块统计
        if len(self._stats["module_stats"]) > self._max_module_stats:
            sorted_modules = sorted(
                self._stats["module_stats"].items(),
                key=lambda x: x[1]["count"],
                reverse=True
            )
            for module_key, _ in sorted_modules[self._max_module_stats:]:
                del self._stats["module_stats"][module_key]

        # 清理状态码统计
        common_status_codes = {200, 201, 204, 400, 401, 403, 404, 500, 502, 503, 504}
        status_codes_to_remove = [
            code for code in self._stats["status_codes"]
            if code not in common_status_codes and self._stats["status_codes"][code] < 10
        ]
        for code in status_codes_to_remove:
            del self._stats["status_codes"][code]

    def record_request_sync(
        self,
        method: str,
        url: str,
        status_code: int,
        duration: float,
        request_headers: Dict[str, str],
        request_body: Any,
        response_headers: Dict[str, str] = None,
        response_body: Any = None,
        error_message: str = None,
        module: str = None,
    ):
        """
        同步记录对外 HTTP 请求信息

        Args:
            method: HTTP 方法
            url: 请求 URL
            status_code: 响应状态码
            duration: 响应时间（秒）
            request_headers: 请求头
            request_body: 请求体
            response_headers: 响应头
            response_body: 响应体
            error_message: 错误信息
            module: 发起请求的模块
        """
        # 限制请求体和响应体大小
        # 增加大小限制到 5MB，避免频繁截断
        max_size = 1024 * 1024 * 5  # 5MB
        try:
            if request_body is not None:
                if isinstance(request_body, (dict, list)):
                    request_body = json.dumps(request_body, ensure_ascii=False)[:max_size]  # 限制为 5MB
                elif isinstance(request_body, str):
                    request_body = request_body[:max_size]  # 限制为 5MB
        except:
            request_body = str(request_body)[:max_size] if request_body is not None else None

        try:
            if response_body is not None:
                if isinstance(response_body, (dict, list)):
                    response_body = json.dumps(response_body, ensure_ascii=False)[:max_size]  # 限制为 5MB
                elif isinstance(response_body, str):
                    response_body = response_body[:max_size]  # 限制为 5MB
        except:
            response_body = str(response_body)[:max_size] if response_body is not None else None

        request_info = {
            "timestamp": time.time(),
            "method": method,
            "url": url,
            "status_code": status_code,
            "duration": duration,
            "request_headers": request_headers,
            "request_body": request_body,
            "response_headers": response_headers,
            "response_body": response_body,
            "error_message": error_message,
            "module": module,
            "is_error": bool(status_code >= 400 or error_message),
            "is_slow": duration >= self._slow_threshold,
            "is_internal": is_internal_url(url),
        }

        # 使用线程锁保护共享资源
        with self._thread_lock:
            # 先添加请求记录，确保请求记录不会丢失
            try:
                self._requests.append(request_info)
            except Exception as e:
                print(f"添加请求记录时发生异常: {e}")

            # 更新统计信息，即使发生异常也不会影响请求记录的添加
            try:
                # 更新统计
                self._stats["total_requests"] += 1
                if request_info["is_error"]:
                    self._stats["total_errors"] += 1
                if request_info["is_slow"]:
                    self._stats["total_slow_requests"] += 1

                # URL 统计
                url_key = f"{method} {url}"
                self._stats["url_stats"][url_key]["count"] += 1
                self._stats["url_stats"][url_key]["total_time"] += duration
                if request_info["is_error"]:
                    self._stats["url_stats"][url_key]["errors"] += 1
                if request_info["is_slow"]:
                    self._stats["url_stats"][url_key]["slow_requests"] += 1

                # 状态码统计
                self._stats["status_codes"][status_code] += 1

                # 模块统计
                if module:
                    self._stats["module_stats"][module]["count"] += 1
                    self._stats["module_stats"][module]["total_time"] += duration
                    if request_info["is_error"]:
                        self._stats["module_stats"][module]["errors"] += 1

                # 清理 URL 统计，避免无限增长
                if len(self._stats["url_stats"]) > self._max_url_stats:
                    # 按请求次数排序，保留请求次数多的 URL
                    sorted_urls = sorted(
                        self._stats["url_stats"].items(),
                        key=lambda x: x[1]["count"],
                        reverse=True
                    )
                    # 只保留前 max_url_stats 个
                    for url_key, _ in sorted_urls[self._max_url_stats:]:
                        del self._stats["url_stats"][url_key]

                # 清理模块统计，避免无限增长
                if len(self._stats["module_stats"]) > self._max_module_stats:
                    # 按请求次数排序，保留请求次数多的模块
                    sorted_modules = sorted(
                        self._stats["module_stats"].items(),
                        key=lambda x: x[1]["count"],
                        reverse=True
                    )
                    # 只保留前 max_module_stats 个
                    for module_key, _ in sorted_modules[self._max_module_stats:]:
                        del self._stats["module_stats"][module_key]

                # 清理状态码统计，只保留常见状态码
                common_status_codes = {200, 201, 204, 400, 401, 403, 404, 500, 502, 503, 504}
                status_codes_to_remove = []
                for code in self._stats["status_codes"]:
                    if code not in common_status_codes and self._stats["status_codes"][code] < 10:
                        status_codes_to_remove.append(code)
                for code in status_codes_to_remove:
                    del self._stats["status_codes"][code]
            except Exception as e:
                # 记录异常，确保即使发生异常也不会影响主流程
                print(f"更新统计信息时发生异常: {e}")

            # 异步保存到数据库，避免阻塞同步线程
            try:
                import asyncio
                from datetime import datetime, timezone

                # 准备保存到数据库的数据
                request_data = {
                    "timestamp": datetime.fromtimestamp(request_info["timestamp"], timezone.utc),
                    "method": method,
                    "url": url,
                    "status_code": status_code,
                    "duration": duration,
                    "request_headers": json.dumps(request_headers) if request_headers else None,
                    "request_body": request_body,
                    "response_headers": json.dumps(response_headers) if response_headers else None,
                    "response_body": response_body,
                    "error_message": error_message,
                    "module": module,
                    "is_error": request_info["is_error"],
                    "is_slow": request_info["is_slow"],
                    "is_internal": request_info["is_internal"],
                }

                # 直接使用同步方式保存到数据库，避免事件循环问题
                try:
                    from tortoise import Tortoise
                    from core.database import TORTOISE_ORM_CONFIG

                    # 初始化Tortoise ORM
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    async def save_to_db():
                        try:
                            # 检查Tortoise是否已经初始化
                            if not Tortoise._inited:
                                await Tortoise.init(config=TORTOISE_ORM_CONFIG)
                            await outbound_request_storage.save_request(request_data)
                        except Exception as e:
                            pass
                            print(f"保存对外请求到数据库失败: {e}")
                        finally:
                            # 不要关闭数据库连接，避免影响其他线程
                            pass

                    # 运行事件循环直到任务完成
                    loop.run_until_complete(save_to_db())
                except Exception as e:
                    # 记录异常，确保即使发生异常也不会影响主流程
                    print(f"同步保存对外请求到数据库失败: {e}")
                    pass
            except Exception as e:
                # 记录异常，确保即使发生异常也不会影响主流程
                print(f"创建数据库保存任务失败: {e}")
                pass

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取 HTTP 指标

        Returns:
            Dict: HTTP 请求指标
        """
        # 计算 URL 平均响应时间
        url_stats = {}
        for url, stats in self._stats["url_stats"].items():
            count = stats["count"]
            url_stats[url] = {
                "count": count,
                "avg_time": round(stats["total_time"] / count, 3) if count > 0 else 0,
                "errors": stats["errors"],
                "slow_requests": stats["slow_requests"],
                "error_rate": round(stats["errors"] / count * 100, 2) if count > 0 else 0,
            }

        # 计算总体平均响应时间
        total_time = sum(r["duration"] for r in self._requests)
        avg_response_time = round(total_time / len(self._requests), 3) if self._requests else 0

        # 最近请求
        recent_requests = list(self._requests)[-20:]

        return {
            "timestamp": time.time(),
            "summary": {
                "total_requests": self._stats["total_requests"],
                "total_errors": self._stats["total_errors"],
                "total_slow_requests": self._stats["total_slow_requests"],
                "error_rate": round(
                    self._stats["total_errors"] / self._stats["total_requests"] * 100, 2
                ) if self._stats["total_requests"] > 0 else 0,
                "avg_response_time": avg_response_time,
                "requests_per_minute": self._calculate_rpm(),
            },
            "status_codes": dict(self._stats["status_codes"]),
            "url_stats": url_stats,
            "recent_requests": recent_requests,
        }

    def _calculate_rpm(self) -> int:
        """计算每分钟请求数"""
        if not self._requests:
            return 0

        now = time.time()
        one_minute_ago = now - 60
        recent_count = sum(1 for r in self._requests if r["timestamp"] > one_minute_ago)
        return recent_count

    def get_slow_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取慢请求列表"""
        slow_requests = [r for r in self._requests if r["is_slow"]]
        return sorted(slow_requests, key=lambda x: x["duration"], reverse=True)[:limit]

    def get_error_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取错误请求列表"""
        error_requests = [r for r in self._requests if r["is_error"]]
        return sorted(error_requests, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_all_requests(self) -> List[Dict[str, Any]]:
        """获取所有请求记录"""
        return list(self._requests)

    def reset_stats(self):
        """重置统计"""
        self._requests.clear()
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_slow_requests": 0,
            "url_stats": defaultdict(lambda: {
                "count": 0,
                "total_time": 0.0,
                "errors": 0,
                "slow_requests": 0,
            }),
            "status_codes": defaultdict(int),
            "module_stats": defaultdict(lambda: {
                "count": 0,
                "total_time": 0.0,
                "errors": 0,
            }),
        }

    async def get_requests_by_date(self, date: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        按日期获取对外请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 对外请求记录列表
        """
        from ..storage import outbound_request_storage
        requests = await outbound_request_storage.get_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration,
            "request_headers": req.request_headers,
            "request_body": req.request_body,
            "response_headers": req.response_headers,
            "response_body": req.response_body,
            "error_message": req.error_message,
            "module": req.module,
            "is_error": req.is_error,
            "is_slow": req.is_slow,
            "is_internal": req.is_internal
        } for req in requests]

    async def get_slow_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取对外慢请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 对外慢请求记录列表
        """
        from ..storage import outbound_request_storage
        slow_requests = await outbound_request_storage.get_slow_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration,
            "request_headers": req.request_headers,
            "request_body": req.request_body,
            "response_headers": req.response_headers,
            "response_body": req.response_body,
            "error_message": req.error_message,
            "module": req.module,
            "is_error": req.is_error,
            "is_slow": req.is_slow,
            "is_internal": req.is_internal
        } for req in slow_requests]

    async def get_error_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取对外错误请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 对外错误请求记录列表
        """
        from ..storage import outbound_request_storage
        error_requests = await outbound_request_storage.get_error_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "url": req.url,
            "status_code": req.status_code,
            "duration": req.duration,
            "request_headers": req.request_headers,
            "request_body": req.request_body,
            "response_headers": req.response_headers,
            "response_body": req.response_body,
            "error_message": req.error_message,
            "module": req.module,
            "is_error": req.is_error,
            "is_slow": req.is_slow,
            "is_internal": req.is_internal
        } for req in error_requests]


# 全局对外 HTTP 请求收集器实例
outbound_http_collector = OutboundHTTPCollector()