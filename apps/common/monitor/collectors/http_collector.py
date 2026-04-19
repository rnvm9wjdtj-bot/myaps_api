"""
HTTP 指标采集器

采集 HTTP 请求相关指标
"""

from typing import Dict, Any, List
from ..middleware import http_metrics_collector
from ..allert import AlertType, alert_sender
from ..storage import request_storage
from ..models import is_internal_ip


class HTTPCollector:
    """HTTP 指标采集器"""

    def __init__(self):
        self._collector = http_metrics_collector


    async def get_metrics(self) -> Dict[str, Any]:
        """
        获取 HTTP 指标

        Returns:
            Dict: HTTP 请求指标
        """
        # 保存所有请求到数据库
        await self.save_all_requests()
        return self._collector.get_metrics()


    async def save_all_requests(self):
        """
        保存所有请求到数据库
        """
        from globalobjects import logger as log_config
        logger = log_config.get_logger(__name__)

        requests = list(self._collector._requests)
        logger.debug(f"开始保存请求数据，共 {len(requests)} 个请求")

        saved_count = 0
        for req in requests:
            try:
                # 检查是否已经保存过（通过时间戳和路径判断）
                existing = await request_storage.get_request_by_timestamp_and_path(
                    req.get("timestamp"),
                    req.get("path")
                )
                if not existing:
                    client_ip = req.get("client_ip")
                    # 保存请求数据
                    from datetime import datetime, timezone
                    request_data = {
                        "timestamp": datetime.fromtimestamp(req.get("timestamp"), timezone.utc),
                        "method": req.get("method"),
                        "path": req.get("path"),
                        "query_params": req.get("query_params"),
                        "status_code": req.get("status_code"),
                        "response_time": req.get("duration") * 1000,  # 转换为毫秒
                        "client_ip": client_ip,
                        "user_agent": req.get("user_agent"),
                        "payload_size": len(req.get("request_body", "")) if req.get("request_body") else None,
                        "response_size": len(req.get("response_body", "")) if req.get("response_body") else None,
                        "request_body": req.get("request_body"),
                        "response_body": req.get("response_body"),
                        "is_slow": req.get("is_slow", False),
                        "slow_threshold": 1000.0 if req.get("is_slow") else None,
                        "is_error": req.get("is_error", False),
                        "error_message": req.get("error_message"),
                        "is_internal": is_internal_ip(client_ip) if client_ip else False
                    }
                    await request_storage.save_request(request_data)
                    saved_count += 1
            except Exception as e:
                logger.error(f"保存请求数据失败: {e}")

        logger.debug(f"请求数据保存完成，共保存 {saved_count} 个请求")


    async def get_slow_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取慢请求列表

        Args:
            limit: 返回数量限制

        Returns:
            List: 慢请求列表
        """
        slow_requests = self._collector.get_slow_requests(limit)

        # 持久化慢请求数据
        from datetime import datetime, timezone
        for req in slow_requests:
            client_ip = req.get("client_ip")
            # 保存基础请求数据和慢请求字段
            request_data = {
                "timestamp": datetime.fromtimestamp(req.get("timestamp"), timezone.utc),
                "method": req.get("method"),
                "path": req.get("path"),
                "query_params": req.get("query_params"),
                "status_code": req.get("status_code"),
                "response_time": req.get("duration") * 1000,  # 转换为毫秒
                "client_ip": client_ip,
                "user_agent": req.get("user_agent"),
                "payload_size": len(req.get("request_body", "")) if req.get("request_body") else None,
                "response_size": len(req.get("response_body", "")) if req.get("response_body") else None,
                "request_body": req.get("request_body"),
                "response_body": req.get("response_body"),
                "is_slow": True,
                "slow_threshold": 1000.0,
                "is_error": False,
                "is_internal": is_internal_ip(client_ip) if client_ip else False
            }
            await request_storage.save_request(request_data)

        await alert_sender.trigger_alert(AlertType.REQUEST_SLOW, slow_requests)
        return slow_requests


    async def get_error_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取错误请求列表

        Args:
            limit: 返回数量限制

        Returns:
            List: 错误请求列表
        """
        error_requests = self._collector.get_error_requests(limit)

        # 持久化错误请求数据
        from datetime import datetime, timezone
        for req in error_requests:
            client_ip = req.get("client_ip")
            # 保存基础请求数据和错误请求字段
            request_data = {
                "timestamp": datetime.fromtimestamp(req.get("timestamp"), timezone.utc),
                "method": req.get("method"),
                "path": req.get("path"),
                "query_params": req.get("query_params"),
                "status_code": req.get("status_code"),
                "response_time": req.get("duration") * 1000,  # 转换为毫秒
                "client_ip": client_ip,
                "user_agent": req.get("user_agent"),
                "payload_size": len(req.get("request_body", "")) if req.get("request_body") else None,
                "response_size": len(req.get("response_body", "")) if req.get("response_body") else None,
                "request_body": req.get("request_body"),
                "response_body": req.get("response_body"),
                "is_error": True,
                "error_message": req.get("error_message"),
                "is_slow": False,
                "is_internal": is_internal_ip(client_ip) if client_ip else False
            }
            await request_storage.save_request(request_data)

        await alert_sender.trigger_alert(AlertType.REQUEST_ERROR, error_requests)
        return error_requests


    def reset_stats(self):
        """重置统计"""
        self._collector.reset_stats()


    async def get_requests_by_date(self, date: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        按日期获取请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 请求记录列表
        """
        requests = await request_storage.get_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "path": req.path,
            "query_params": req.query_params,
            "status_code": req.status_code,
            "response_time": req.response_time,
            "client_ip": req.client_ip,
            "user_agent": req.user_agent,
            "payload_size": req.payload_size,
            "response_size": req.response_size,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "is_slow": req.is_slow,
            "slow_threshold": req.slow_threshold,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "is_internal": req.is_internal
        } for req in requests]


    async def get_slow_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取慢请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 慢请求记录列表
        """
        slow_requests = await request_storage.get_slow_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "path": req.path,
            "query_params": req.query_params,
            "status_code": req.status_code,
            "response_time": req.response_time,
            "client_ip": req.client_ip,
            "user_agent": req.user_agent,
            "payload_size": req.payload_size,
            "response_size": req.response_size,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "is_slow": req.is_slow,
            "slow_threshold": req.slow_threshold,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "is_internal": req.is_internal
        } for req in slow_requests]


    async def get_error_requests_by_date(self, date: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        按日期获取错误请求记录

        Args:
            date: 查询日期，格式：YYYY-MM-DD
            limit: 返回数量限制

        Returns:
            List: 错误请求记录列表
        """
        error_requests = await request_storage.get_error_requests_by_date(date, limit)
        return [{
            "id": req.id,
            "timestamp": req.timestamp.isoformat(),
            "method": req.method,
            "path": req.path,
            "query_params": req.query_params,
            "status_code": req.status_code,
            "response_time": req.response_time,
            "client_ip": req.client_ip,
            "user_agent": req.user_agent,
            "payload_size": req.payload_size,
            "response_size": req.response_size,
            "request_body": req.request_body,
            "response_body": req.response_body,
            "is_slow": req.is_slow,
            "slow_threshold": req.slow_threshold,
            "is_error": req.is_error,
            "error_message": req.error_message,
            "is_internal": req.is_internal
        } for req in error_requests]