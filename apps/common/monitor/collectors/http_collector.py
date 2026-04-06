"""
HTTP 指标采集器

采集 HTTP 请求相关指标
"""

from typing import Dict, Any, List
from ..middleware import http_metrics_collector
from ..allert import AlertType, alert_sender


class HTTPCollector:
    """HTTP 指标采集器"""

    def __init__(self):
        self._collector = http_metrics_collector


    def get_metrics(self) -> Dict[str, Any]:
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
        await alert_sender.trigger_alert(AlertType.REQUEST_ERROR, error_requests)
        return error_requests


    def reset_stats(self):
        """重置统计"""
        self._collector.reset_stats()
