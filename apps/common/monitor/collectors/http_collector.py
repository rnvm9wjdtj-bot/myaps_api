"""
HTTP 指标采集器

采集 HTTP 请求相关指标
"""

from typing import Dict, Any, List
from globalobjects import RemindType, remind_manager
from ..middleware import http_metrics_collector
from ..storage import request_storage


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
        return self._collector.get_metrics()


    async def get_slow_requests(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取慢请求列表

        Args:
            limit: 返回数量限制

        Returns:
            List: 慢请求列表
        """
        slow_requests = self._collector.get_slow_requests(limit)

        await remind_manager.trigger_remind(RemindType.REQUEST_SLOW, slow_requests)
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

        await remind_manager.trigger_remind(RemindType.REQUEST_ERROR, error_requests)
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