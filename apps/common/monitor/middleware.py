"""
接收请求中间件

用于收集 HTTP 请求指标：请求次数、响应时间、状态码等
"""

import time
import asyncio
from typing import Dict, Any, List, Optional, Callable
from collections import deque, defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


class HTTPMetricsCollector:
    """HTTP 指标收集器"""

    def __init__(self, max_requests: int = 1000, slow_threshold: float = 1.0):
        self._max_requests = max_requests
        self._slow_threshold = slow_threshold  # 慢请求阈值（秒）
        self._requests: deque = deque(maxlen=max_requests)
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_slow_requests": 0,
            "path_stats": defaultdict(lambda: {
                "count": 0,
                "total_time": 0.0,
                "errors": 0,
                "slow_requests": 0,
            }),
            "status_codes": defaultdict(int),
        }
        self._lock = asyncio.Lock()

    async def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        client_ip: str,
        error_message: str = None,
        request_body: str = None,
        response_body: str = None,
        query_params: str = None,
    ):
        """记录请求信息"""
        async with self._lock:
            request_info = {
                "timestamp": time.time(),
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration": duration,
                "client_ip": client_ip,
                "is_error": status_code >= 400,
                "is_slow": duration >= self._slow_threshold,
                "error_message": error_message,
                "request_body": request_body,
                "response_body": response_body,
                "query_params": query_params,
            }

            self._requests.append(request_info)

            # 更新统计
            self._stats["total_requests"] += 1
            if request_info["is_error"]:
                self._stats["total_errors"] += 1
            if request_info["is_slow"]:
                self._stats["total_slow_requests"] += 1

            # 路径统计
            path_key = f"{method} {path}"
            self._stats["path_stats"][path_key]["count"] += 1
            self._stats["path_stats"][path_key]["total_time"] += duration
            if request_info["is_error"]:
                self._stats["path_stats"][path_key]["errors"] += 1
            if request_info["is_slow"]:
                self._stats["path_stats"][path_key]["slow_requests"] += 1

            # 状态码统计
            self._stats["status_codes"][status_code] += 1

    def get_metrics(self) -> Dict[str, Any]:
        """获取 HTTP 指标"""
        # 计算路径平均响应时间
        path_stats = {}
        for path, stats in self._stats["path_stats"].items():
            count = stats["count"]
            path_stats[path] = {
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
            "path_stats": path_stats,
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

    def reset_stats(self):
        """重置统计"""
        self._requests.clear()
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "total_slow_requests": 0,
            "path_stats": defaultdict(lambda: {
                "count": 0,
                "total_time": 0.0,
                "errors": 0,
                "slow_requests": 0,
            }),
            "status_codes": defaultdict(int),
        }


# 全局 HTTP 指标收集器实例
http_metrics_collector = HTTPMetricsCollector()


class HTTPMonitorMiddleware(BaseHTTPMiddleware):
    """HTTP 监控中间件"""

    def __init__(self, app, include_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.include_paths = include_paths or [
            "/api",  # 只监控 API 路径的请求
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not any(path.startswith(included) for included in self.include_paths):
            return await call_next(request)

        start_time = time.time()
        error_message = None
        request_body = None
        response_body = None
        query_params = None
        
        # 收集查询参数
        try:
            query_params = dict(request.query_params)
            import json
            query_params = json.dumps(query_params)
        except Exception as e:
            logger.debug(f"读取查询参数失败: {e}")
            query_params = None

        # 读取请求体
        try:
            if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
                body = await request.body()
                if body:
                    try:
                        import json
                        # 限制请求体大小，避免内存占用过大
                        if len(body) < 1024 * 1024:  # 1MB
                            request_body = body.decode('utf-8')
                        else:
                            request_body = f"[请求体过大，已截断，大小: {len(body)} bytes]"
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        request_body = "[请求体不是有效的 JSON]"
        except Exception as e:
            logger.debug(f"读取请求体失败: {e}")

        try:
            response = await call_next(request)
            status_code = response.status_code

            # 读取响应体
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                # 创建异步迭代器
                async def async_body_iterator():
                    yield body
                
                response.body_iterator = async_body_iterator()
                
                if body:
                    try:
                        import json
                        # 限制响应体大小，避免内存占用过大
                        if len(body) < 1024 * 1024:  # 1MB
                            response_body = body.decode('utf-8')
                        else:
                            response_body = f"[响应体过大，已截断，大小: {len(body)} bytes]"
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        response_body = "[响应体不是有效的 JSON]"
            except Exception as e:
                logger.debug(f"读取响应体失败: {e}")

            if status_code >= 400:
                error_message = await self._extract_error_message(response)
        except Exception as e:
            status_code = 500
            error_message = str(e)
            logger.error(f"请求处理异常: {e}")
            raise
        finally:
            duration = time.time() - start_time

            client_ip = request.client.host if request.client else "unknown"
            asyncio.create_task(
                http_metrics_collector.record_request(
                    method=request.method,
                    path=path,
                    status_code=status_code,
                    duration=duration,
                    client_ip=client_ip,
                    error_message=error_message,
                    request_body=request_body,
                    response_body=response_body,
                    query_params=query_params,
                )
            )

        return response

    async def _extract_error_message(self, response: Response) -> str:
        """从响应体中提取错误消息"""
        try:
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # 创建异步迭代器
            async def async_body_iterator():
                yield body
            
            response.body_iterator = async_body_iterator()
            
            if body:
                try:
                    import json
                    data = json.loads(body.decode('utf-8'))
                    if isinstance(data, dict):
                        return data.get('message') or data.get('msg') or data.get('error') or data.get('detail')
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        except Exception as e:
            logger.debug(f"提取错误消息失败: {e}")
        
        return None
