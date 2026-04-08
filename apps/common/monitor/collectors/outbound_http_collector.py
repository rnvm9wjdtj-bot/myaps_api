"""
对外 HTTP 请求收集器

收集和管理所有外发 HTTP 请求的指标和详细信息
"""

import time
import asyncio
import json
from typing import Dict, Any, List
from collections import deque, defaultdict


class OutboundHTTPCollector:
    """对外 HTTP 请求收集器"""
    
    def __init__(self, max_requests: int = 1000, slow_threshold: float = 1.0, max_url_stats: int = 1000, max_module_stats: int = 100):
        """
        初始化对外 HTTP 请求收集器
        
        Args:
            max_requests: 最大存储的请求数
            slow_threshold: 慢请求阈值（秒）
            max_url_stats: URL统计最大条目数
            max_module_stats: 模块统计最大条目数
        """
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
            try:
                if request_body and isinstance(request_body, (dict, list)):
                    request_body = json.dumps(request_body)[:1024 * 1024]  # 限制为 1MB
                elif request_body and isinstance(request_body, str):
                    request_body = request_body[:1024 * 1024]  # 限制为 1MB
            except:
                request_body = str(request_body)[:1024 * 1024]
            
            try:
                if response_body and isinstance(response_body, (dict, list)):
                    response_body = json.dumps(response_body)[:1024 * 1024]  # 限制为 1MB
                elif response_body and isinstance(response_body, str):
                    response_body = response_body[:1024 * 1024]  # 限制为 1MB
            except:
                response_body = str(response_body)[:1024 * 1024]
            
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
                "is_error": status_code >= 400 or error_message,
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
        try:
            if request_body and isinstance(request_body, (dict, list)):
                request_body = json.dumps(request_body)[:1024 * 1024]  # 限制为 1MB
            elif request_body and isinstance(request_body, str):
                request_body = request_body[:1024 * 1024]  # 限制为 1MB
        except:
            request_body = str(request_body)[:1024 * 1024]
        
        try:
            if response_body and isinstance(response_body, (dict, list)):
                response_body = json.dumps(response_body)[:1024 * 1024]  # 限制为 1MB
            elif response_body and isinstance(response_body, str):
                response_body = response_body[:1024 * 1024]  # 限制为 1MB
        except:
            response_body = str(response_body)[:1024 * 1024]
        
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
            "is_error": status_code >= 400 or error_message,
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
    
    def get_all_requests(self, limit: int = 50) -> List[Dict[str, Any]]:
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


# 全局对外 HTTP 请求收集器实例
outbound_http_collector = OutboundHTTPCollector()
