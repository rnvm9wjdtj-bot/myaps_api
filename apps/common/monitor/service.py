"""
监控服务模块

整合各类采集器，提供统一的监控数据接口
"""

import time
import asyncio
from typing import Dict, Any, List, Optional
from .collectors import ResourceCollector, DatabaseCollector, SchedulerCollector, HTTPCollector
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


class MonitorService:
    """监控服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.resource_collector = ResourceCollector()
        self.db_collector = DatabaseCollector()
        self.scheduler_collector = SchedulerCollector()
        self.http_collector = HTTPCollector()
        self._alerts: List[Dict[str, Any]] = []
        self._max_alerts = 100
        self._initialized = True

    def get_resource_metrics(self) -> Dict[str, Any]:
        """获取资源指标"""
        metrics = self.resource_collector.get_current_metrics()
        alerts = self.resource_collector.check_thresholds(metrics)

        for alert in alerts:
            self._add_alert("warning", alert, "resource")

        return metrics

    async def get_database_metrics(self) -> Dict[str, Any]:
        """获取数据库指标"""
        return await self.db_collector.get_all_metrics()

    def get_scheduler_metrics(self) -> Dict[str, Any]:
        """获取定时任务指标"""
        return self.scheduler_collector.get_all_metrics()

    def get_http_metrics(self) -> Dict[str, Any]:
        """获取 HTTP 指标"""
        return self.http_collector.get_metrics()

    async def get_overview(self) -> Dict[str, Any]:
        """获取监控总览"""
        return {
            "timestamp": time.time(),
            "resource": self.get_resource_metrics(),
            "database": await self.get_database_metrics(),
            "scheduler": self.get_scheduler_metrics(),
            "http": self.get_http_metrics(),
            "alerts": self.get_recent_alerts(10),
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """获取健康检查状态"""
        checks = {}
        healthy_count = 0
        total_count = 0

        # 检查资源
        try:
            resource = self.resource_collector.get_current_metrics()
            resource_alerts = self.resource_collector.check_thresholds(resource)
            checks["resource"] = {
                "status": "healthy" if not resource_alerts else "warning",
                "message": "资源使用正常" if not resource_alerts else f"有 {len(resource_alerts)} 个告警",
            }
            if not resource_alerts:
                healthy_count += 1
            total_count += 1
        except Exception as e:
            checks["resource"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查数据库
        try:
            db_status = await self.db_collector.get_connection_status()
            summary = db_status.get("summary", {})
            if summary.get("unhealthy", 0) == 0:
                checks["database"] = {"status": "healthy", "message": "所有数据库连接正常"}
                healthy_count += 1
            else:
                checks["database"] = {
                    "status": "warning",
                    "message": f"{summary.get('unhealthy', 0)} 个数据库连接异常",
                }
            total_count += 1
        except Exception as e:
            checks["database"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查调度器
        try:
            scheduler = self.scheduler_collector.get_scheduler_status()
            if scheduler.get("running", False):
                checks["scheduler"] = {"status": "healthy", "message": "调度器运行正常"}
                healthy_count += 1
            else:
                checks["scheduler"] = {"status": "warning", "message": "调度器未运行"}
            total_count += 1
        except Exception as e:
            checks["scheduler"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 检查 HTTP
        try:
            http_metrics = self.http_collector.get_metrics()
            summary = http_metrics.get("summary", {})
            error_rate = summary.get("error_rate", 0)
            if error_rate < 5:
                checks["http"] = {"status": "healthy", "message": f"HTTP 服务正常 (错误率: {error_rate}%)"}
                healthy_count += 1
            else:
                checks["http"] = {"status": "warning", "message": f"HTTP 错误率较高: {error_rate}%"}
            total_count += 1
        except Exception as e:
            checks["http"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 确定整体状态
        if healthy_count == total_count:
            status = "healthy"
            message = "所有系统运行正常"
        elif healthy_count >= total_count / 2:
            status = "degraded"
            message = "部分系统存在警告"
        else:
            status = "unhealthy"
            message = "多个系统异常，需要关注"

        return {
            "status": status,
            "timestamp": time.time(),
            "checks": checks,
            "message": message,
        }

    def _add_alert(self, level: str, message: str, source: str):
        """添加告警"""
        alert = {
            "level": level,
            "message": message,
            "timestamp": time.time(),
            "source": source,
        }
        self._alerts.append(alert)

        # 限制告警数量
        if len(self._alerts) > self._max_alerts:
            self._alerts = self._alerts[-self._max_alerts:]

    def get_recent_alerts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近告警"""
        return sorted(
            self._alerts,
            key=lambda x: x["timestamp"],
            reverse=True
        )[:limit]

    def clear_alerts(self):
        """清空告警"""
        self._alerts = []

    def get_recent_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最近的日志
        
        Args:
            limit: 返回日志数量限制
            level: 日志级别过滤 (warning, error)
            
        Returns:
            日志列表
        """
        # 从全局日志中获取最近的日志
        # 这里需要根据实际的日志系统实现
        # 暂时返回模拟数据
        import logging
        from datetime import datetime
        
        logs = []
        
        # 模拟日志数据
        log_levels = ['warning', 'error'] if level else ['warning', 'error']
        
        for i in range(20):
            log_level = log_levels[i % len(log_levels)]
            logs.append({
                "level": log_level,
                "message": f"模拟 {log_level} 日志消息 {i+1}",
                "timestamp": time.time() - (i * 30),
                "module": f"module.{i % 5}",
                "traceback": "Traceback (most recent call last):\n  File \"example.py\", line 10, in <module>\n    1 / 0\nZeroDivisionError: division by zero" if log_level == 'error' else None
            })
        
        # 按时间倒序排序
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return logs[:limit]


# 全局监控服务实例
monitor_service = MonitorService()
