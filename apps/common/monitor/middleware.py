"""
接收请求中间件

用于收集 HTTP 请求指标：请求次数、响应时间、状态码等
"""

import time
import asyncio
import uuid
import json
from typing import Dict, Any, List, Optional, Callable
from collections import deque, defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from globalobjects import logger as log_config
from .models import is_internal_ip

logger = log_config.get_logger(__name__)


def truncate_json(obj, max_chars):
    """递归截断JSON对象，保持有效JSON结构"""
    def _truncate(obj, remaining):
        if remaining <= 0:
            return "...", 0
        
        if isinstance(obj, str):
            s = obj
            if len(s) <= remaining:
                return s, len(s)
            return s[:remaining - 5] + "...", remaining
        
        elif isinstance(obj, (int, float, bool, type(None))):
            s = str(obj)
            return obj, len(s)
        
        elif isinstance(obj, list):
            result = []
            chars_used = 2
            for item in obj:
                item_str_len = len(json.dumps(item, ensure_ascii=False)) + 2
                if chars_used + item_str_len > remaining - 1:
                    result.append("...")
                    chars_used += 5
                    break
                truncated_item, item_chars = _truncate(item, remaining - chars_used - 1)
                result.append(truncated_item)
                chars_used += item_chars + 2
            
            return result, chars_used
        
        elif isinstance(obj, dict):
            result = {}
            chars_used = 2
            for key, value in obj.items():
                key_len = len(json.dumps(key, ensure_ascii=False)) + 2
                value_str_len = len(json.dumps(value, ensure_ascii=False)) + 2
                if chars_used + key_len + value_str_len > remaining - 1:
                    result[key] = "..."
                    chars_used += key_len + 5
                    break
                truncated_value, value_chars = _truncate(value, remaining - chars_used - key_len - 1)
                result[key] = truncated_value
                chars_used += key_len + value_chars + 2
            
            return result, chars_used
        
        else:
            s = str(obj)
            return obj, len(s)
    
    truncated_obj, _ = _truncate(obj, max_chars)
    return truncated_obj


class HTTPMetricsCollector:
    """HTTP 指标收集器"""

    def __init__(self, max_requests: int = 1000, slow_threshold: float = 1.0, max_path_stats: int = 1000):
        self._max_requests = max_requests
        self._slow_threshold = slow_threshold  # 慢请求阈值（秒）
        self._max_path_stats = max_path_stats  # 路径统计最大条目数
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
        # 请求频率限制
        self._rate_limits = defaultdict(lambda: deque(maxlen=100))  # 每个IP最多100个请求/分钟
        self._lock = None  # 延迟初始化锁，确保绑定到正确的事件循环
        
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
        path: str,
        status_code: int,
        duration: float,
        client_ip: str,
        error_message: str = None,
        request_body: str = None,
        response_body: str = None,
        request_body_full: str = None,
        response_body_full: str = None,
        query_params: str = None,
        request_id: str = None,
    ):
        """记录请求信息
        
        Args:
            request_body: 截断版本，用于内存队列展示
            response_body: 截断版本，用于内存队列展示
            request_body_full: 完整版本，用于数据库存储
            response_body_full: 完整版本，用于数据库存储
        """
        async with self._get_lock():
            request_info = {
                "request_id": request_id or str(uuid.uuid4()),
                "timestamp": time.time(),
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration": duration,
                "client_ip": client_ip,
                "is_error": status_code >= 400,
                "is_slow": duration >= self._slow_threshold,
                "is_internal": is_internal_ip(client_ip),
                "error_message": error_message,
                "request_body": request_body,  # 截断版本，用于内存队列
                "response_body": response_body,  # 截断版本，用于内存队列
                "query_params": query_params,
            }

            self._requests.append(request_info)
            
            # 保存到数据库时使用完整版本
            asyncio.create_task(self._save_request_to_db(
                request_info,
                request_body_full=request_body_full or request_body,
                response_body_full=response_body_full or response_body
            ))

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

            # 清理路径统计，避免无限增长
            if len(self._stats["path_stats"]) > self._max_path_stats:
                # 按请求次数排序，保留请求次数多的路径
                sorted_paths = sorted(
                    self._stats["path_stats"].items(),
                    key=lambda x: x[1]["count"],
                    reverse=True
                )
                # 只保留前 max_path_stats 个
                for path_key, _ in sorted_paths[self._max_path_stats:]:
                    del self._stats["path_stats"][path_key]

            # 清理状态码统计，只保留常见状态码
            common_status_codes = {200, 201, 204, 400, 401, 403, 404, 500, 502, 503, 504}
            status_codes_to_remove = []
            for code in self._stats["status_codes"]:
                if code not in common_status_codes and self._stats["status_codes"][code] < 10:
                    status_codes_to_remove.append(code)
            for code in status_codes_to_remove:
                del self._stats["status_codes"][code]

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

    async def _save_request_to_db(
        self, 
        request_info: Dict[str, Any],
        request_body_full: str = None,
        response_body_full: str = None
    ):
        """将请求保存到数据库
        
        Args:
            request_info: 请求信息（内存队列版本，包含截断的请求体/响应体）
            request_body_full: 完整的请求体，用于数据库存储
            response_body_full: 完整的响应体，用于数据库存储
        """
        try:
            from .storage import request_storage
            from datetime import datetime, timezone
            
            request_data = {
                "request_id": request_info.get("request_id"),
                "timestamp": datetime.fromtimestamp(request_info.get("timestamp"), timezone.utc),
                "method": request_info.get("method"),
                "path": request_info.get("path"),
                "query_params": request_info.get("query_params"),
                "status_code": request_info.get("status_code"),
                "response_time": request_info.get("duration") * 1000,  # 转换为毫秒
                "client_ip": request_info.get("client_ip"),
                "user_agent": request_info.get("user_agent"),
                "payload_size": len(request_body_full) if request_body_full else None,
                "response_size": len(response_body_full) if response_body_full else None,
                "request_body": request_body_full,  # 使用完整版本
                "response_body": response_body_full,  # 使用完整版本
                "is_slow": request_info.get("is_slow", False),
                "slow_threshold": 1000.0 if request_info.get("is_slow") else None,
                "is_error": request_info.get("is_error", False),
                "error_message": request_info.get("error_message"),
                "is_internal": request_info.get("is_internal", False)
            }
            
            # 检查数据库中是否已存在相同 request_id 的记录
            existing = await request_storage.get_request_by_request_id(request_info.get("request_id"))
            if not existing:
                await request_storage.save_request(request_data)
                logger.debug(f"请求已保存到数据库: {request_info.get('request_id')}")
            else:
                logger.debug(f"请求已存在，跳过保存: {request_info.get('request_id')}")
        except Exception as e:
            logger.error(f"保存请求到数据库失败: {e}")

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

    def check_rate_limit(self, client_ip: str) -> bool:
        """
        检查请求频率是否超过限制

        Args:
            client_ip: 客户端 IP 地址

        Returns:
            bool: True 表示请求频率超过限制，False 表示正常
        """
        now = time.time()
        one_minute_ago = now - 60

        # 清理过期的请求记录
        self._rate_limits[client_ip] = deque(
            [t for t in self._rate_limits[client_ip] if t > one_minute_ago],
            maxlen=100
        )

        # 检查是否超过限制
        if len(self._rate_limits[client_ip]) >= 100:
            return True

        # 记录当前请求
        self._rate_limits[client_ip].append(now)
        return False


# 全局 HTTP 指标收集器实例
http_metrics_collector = HTTPMetricsCollector()


class HTTPMonitorMiddleware(BaseHTTPMiddleware):
    """HTTP 监控中间件"""

    def __init__(self, app, include_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.include_paths = include_paths or [
            "/api",  # 监控 API 路径的请求
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if not any(path.startswith(included) for included in self.include_paths):
            return await call_next(request)

        # 检查请求频率限制
        client_ip = request.client.host if request.client else "unknown"
        # 对来自本机的请求不设置限制
        if not is_internal_ip(client_ip) and http_metrics_collector.check_rate_limit(client_ip):
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"message": "请求过于频繁，请稍后再试", "status_code": 429}
            )

        start_time = time.time()
        error_message = None
        response_body = None
        response_body_full = None
        query_params = None

        # 收集查询参数
        try:
            query_params = dict(request.query_params)
            import json
            query_params = json.dumps(query_params, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"读取查询参数失败: {e}")
            query_params = None

        # 读取请求体
        request_body_full = None  # 完整版本，用于数据库
        request_body = None  # 截断版本，用于内存队列展示
        try:
            if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
                body = await request.body()
                if body:
                    try:
                        import json
                        decoded_body = body.decode('utf-8')
                        request_body_full = decoded_body  # 保存完整版本
                        
                        # 生成截断版本用于内存队列展示
                        if len(decoded_body) > 1024 * 1024:  # 1MB
                            preview_size = 100 * 1024  # 100KB
                            try:
                                parsed_json = json.loads(decoded_body)
                                truncated_json = truncate_json(parsed_json, preview_size)
                                request_body = json.dumps(truncated_json, ensure_ascii=False, indent=2)
                            except Exception:
                                request_body = decoded_body[:preview_size]
                        else:
                            request_body = decoded_body
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        request_body_full = "[请求体不是有效的 JSON]"
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
                        # 尝试解码响应体
                        decoded_body = body.decode('utf-8')
                        response_body_full = decoded_body  # 保存完整版本
                        
                        # 总是尝试解析响应体，检查业务状态码
                        try:
                            response_json = json.loads(decoded_body)
                            # 检查是否包含业务状态码
                            if isinstance(response_json, dict):
                                # 直接取响应体json根路径下的status_code
                                biz_status_code = response_json.get('status_code')
                                # 检查业务状态码是否表示错误
                                if biz_status_code and str(biz_status_code).startswith('5'):
                                    # 将业务错误视为HTTP错误
                                    status_code = 500
                        except json.JSONDecodeError:
                            # 解析失败，仍然保存响应体
                            pass
                        
                        # 生成截断版本用于内存队列展示
                        if len(decoded_body) > 1024 * 1024:  # 1MB
                            preview_size = 100 * 1024  # 100KB
                            try:
                                parsed_json = json.loads(decoded_body)
                                truncated_json = truncate_json(parsed_json, preview_size)
                                response_body = json.dumps(truncated_json, ensure_ascii=False, indent=2)
                            except Exception:
                                response_body = decoded_body[:preview_size]
                        else:
                            response_body = decoded_body
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        response_body_full = "[响应体不是有效的 JSON]"
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

            # 记录请求到监控收集器
            request_id = str(uuid.uuid4())
            
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
                    request_body_full=request_body_full,
                    response_body_full=response_body_full,
                    query_params=query_params,
                    request_id=request_id,
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