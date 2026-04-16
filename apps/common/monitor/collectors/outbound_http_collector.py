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
from datetime import datetime
from ..storage import outbound_request_storage


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
            self._lock = asyncio.Lock()
            self._thread_lock = threading.Lock()
            self._initialized = True
    
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
        async with self._lock:
            # 限制请求体和响应体大小
            # 增加大小限制到 5MB，避免频繁截断
            max_size = 1024 * 1024 * 5  # 5MB
            try:
                if request_body and isinstance(request_body, (dict, list)):
                    request_body = json.dumps(request_body)[:max_size]  # 限制为 5MB
                elif request_body and isinstance(request_body, str):
                    request_body = request_body[:max_size]  # 限制为 5MB
            except:
                request_body = str(request_body)[:max_size]
            
            try:
                if response_body and isinstance(response_body, (dict, list)):
                    response_body = json.dumps(response_body)[:max_size]  # 限制为 5MB
                elif response_body and isinstance(response_body, str):
                    response_body = response_body[:max_size]  # 限制为 5MB
            except:
                response_body = str(response_body)[:max_size]
            
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
            }
            
            self._requests.append(request_info)
            
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
            
            # 持久化到数据库
            try:
                request_data = {
                    "timestamp": datetime.fromtimestamp(request_info["timestamp"]),
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
                }
                await outbound_request_storage.save_request(request_data)
            except Exception as e:
                # 记录异常，确保即使发生异常也不会影响主流程
                print(f"保存对外请求到数据库失败: {e}")
    
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
            if request_body and isinstance(request_body, (dict, list)):
                request_body = json.dumps(request_body)[:max_size]  # 限制为 5MB
            elif request_body and isinstance(request_body, str):
                request_body = request_body[:max_size]  # 限制为 5MB
        except:
            request_body = str(request_body)[:max_size]
        
        try:
            if response_body and isinstance(response_body, (dict, list)):
                response_body = json.dumps(response_body)[:max_size]  # 限制为 5MB
            elif response_body and isinstance(response_body, str):
                response_body = response_body[:max_size]  # 限制为 5MB
        except:
            response_body = str(response_body)[:max_size]
        
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
                from datetime import datetime
                
                # 准备保存到数据库的数据
                request_data = {
                    "timestamp": datetime.fromtimestamp(request_info["timestamp"]),
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
                            print(f"保存对外请求到数据库失败: {e}")
                        finally:
                            # 不要关闭数据库连接，避免影响其他线程
                            pass
                    
                    # 运行事件循环直到任务完成
                    loop.run_until_complete(save_to_db())
                except Exception as e:
                    # 记录异常，确保即使发生异常也不会影响主流程
                    print(f"同步保存对外请求到数据库失败: {e}")
            except Exception as e:
                # 记录异常，确保即使发生异常也不会影响主流程
                print(f"创建数据库保存任务失败: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取对外 HTTP 请求指标
        
        Returns:
            指标数据
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
        
        # 计算模块统计
        module_stats = {}
        for module, stats in self._stats["module_stats"].items():
            count = stats["count"]
            module_stats[module] = {
                "count": count,
                "avg_time": round(stats["total_time"] / count, 3) if count > 0 else 0,
                "errors": stats["errors"],
                "error_rate": round(stats["errors"] / count * 100, 2) if count > 0 else 0,
            }
        
        # 计算总体平均响应时间
        total_time = sum(r["duration"] for r in self._requests)
        avg_response_time = round(total_time / len(self._requests), 3) if self._requests else 0
        
        # 计算最近一分钟的错误率
        now = time.time()
        one_minute_ago = now - 60
        recent_requests = [r for r in self._requests if r["timestamp"] > one_minute_ago]
        recent_errors = sum(1 for r in recent_requests if r["is_error"])
        recent_error_rate = round(recent_errors / len(recent_requests) * 100, 2) if recent_requests else 0
        
        # 最近请求
        all_recent_requests = list(self._requests)[-20:]
        
        return {
            "timestamp": time.time(),
            "summary": {
                "total_requests": self._stats["total_requests"],
                "total_errors": self._stats["total_errors"],
                "total_slow_requests": self._stats["total_slow_requests"],
                "error_rate": recent_error_rate,  # 使用最近一分钟的错误率
                "avg_response_time": avg_response_time,
                "requests_per_minute": self._calculate_rpm(),
            },
            "status_codes": dict(self._stats["status_codes"]),
            "url_stats": url_stats,
            "module_stats": module_stats,
            "recent_requests": all_recent_requests,
        }
    
    def _calculate_rpm(self) -> int:
        """
        计算每分钟请求数
        
        Returns:
            每分钟请求数
        """
        if not self._requests:
            return 0
        
        now = time.time()
        one_minute_ago = now - 60
        recent_count = sum(1 for r in self._requests if r["timestamp"] > one_minute_ago)
        return recent_count
    
    def get_slow_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取慢请求列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            慢请求列表
        """
        slow_requests = [r for r in self._requests if r["is_slow"]]
        return sorted(slow_requests, key=lambda x: x["duration"], reverse=True)[:limit]
    
    def get_error_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取错误请求列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            错误请求列表
        """
        error_requests = [r for r in self._requests if r["is_error"]]
        return sorted(error_requests, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def get_all_requests(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        获取所有请求列表
        
        Args:
            limit: 返回数量限制
            
        Returns:
            请求列表
        """
        return sorted(self._requests, key=lambda x: x["timestamp"], reverse=True)[:limit]
    
    def reset_stats(self):
        """
        重置统计
        """
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
            date: 日期字符串 (YYYY-MM-DD)
            limit: 返回数量限制
            
        Returns:
            对外请求记录列表
        """
        requests = await outbound_request_storage.get_requests_by_date(date, limit)
        # 转换为字典格式
        result = []
        for req in requests:
            result.append({
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
            })
        return result
    
    async def get_slow_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取对外慢请求记录
        
        Args:
            date: 日期字符串 (YYYY-MM-DD)
            limit: 返回数量限制
            
        Returns:
            对外慢请求记录列表
        """
        slow_requests = await outbound_request_storage.get_slow_requests_by_date(date, limit)
        # 转换为字典格式
        result = []
        for req in slow_requests:
            result.append({
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
            })
        return result
    
    async def get_error_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取对外错误请求记录
        
        Args:
            date: 日期字符串 (YYYY-MM-DD)
            limit: 返回数量限制
            
        Returns:
            对外错误请求记录列表
        """
        error_requests = await outbound_request_storage.get_error_requests_by_date(date, limit)
        # 转换为字典格式
        result = []
        for req in error_requests:
            result.append({
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
            })
        return result


# 全局对外 HTTP 请求收集器实例
outbound_http_collector = OutboundHTTPCollector()
