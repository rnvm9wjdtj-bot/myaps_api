"""
监控服务模块

整合各类采集器，提供统一的监控数据接口
"""

import time
import asyncio
from typing import Dict, Any, List, Optional
from .collectors import ResourceCollector, DatabaseCollector, SchedulerCollector, HTTPCollector
from .collectors.outbound_http_collector import outbound_http_collector
from .collectors.event_collector import EventCollector
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
        self.outbound_http_collector = outbound_http_collector
        self.event_collector = EventCollector()
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

    def get_outbound_http_metrics(self) -> Dict[str, Any]:
        """获取对外 HTTP 请求指标"""
        return self.outbound_http_collector.get_metrics()

    def get_event_metrics(self) -> Dict[str, Any]:
        """获取事件监控指标"""
        return self.event_collector.get_event_metrics()

    def flush_events_now(self, event_type: str = None):
        """立即刷新事件聚合器"""
        self.event_collector.flush_now(event_type)

    def reset_event_stats(self, event_type: str = None):
        """重置事件统计数据"""
        self.event_collector.reset_stats(event_type)

    async def get_overview(self) -> Dict[str, Any]:
        """获取监控总览"""
        return {
            "timestamp": time.time(),
            "resource": self.get_resource_metrics(),
            "database": await self.get_database_metrics(),
            "scheduler": self.get_scheduler_metrics(),
            "http": self.get_http_metrics(),
            "outbound_http": self.get_outbound_http_metrics(),
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

        # 检查对外 HTTP 请求
        try:
            outbound_http_metrics = self.get_outbound_http_metrics()
            summary = outbound_http_metrics.get("summary", {})
            error_rate = summary.get("error_rate", 0)
            if error_rate < 5:
                checks["outbound_http"] = {"status": "healthy", "message": f"对外 HTTP 请求正常 (错误率: {error_rate}%)"}
                healthy_count += 1
            else:
                checks["outbound_http"] = {"status": "warning", "message": f"对外 HTTP 请求错误率较高: {error_rate}%"}
            total_count += 1
        except Exception as e:
            checks["outbound_http"] = {"status": "error", "message": str(e)}
            total_count += 1

        # 确定整体状态
        if healthy_count == total_count:
            status = "healthy"
            message = "所有系统运行正常"
        elif healthy_count >= total_count - 1:  # 最多只有一个系统有问题
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
        # 生成告警类型标识（基于来源和消息内容的前半部分）
        alert_type = f"{source}_{message.split(':')[0]}"
        
        # 检查是否存在相同类型的告警
        for i, existing_alert in enumerate(self._alerts):
            existing_type = f"{existing_alert['source']}_{existing_alert['message'].split(':')[0]}"
            if existing_type == alert_type:
                # 替换为新的告警
                self._alerts[i] = {
                    "level": level,
                    "message": message,
                    "timestamp": time.time(),
                    "source": source,
                }
                return
        
        # 如果不存在相同类型的告警，添加新告警
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
        # 定义告警级别优先级
        level_priority = {
            "critical": 4,
            "error": 3,
            "warning": 2,
            "info": 1
        }
        
        # 先按级别优先级排序，再按时间戳排序
        return sorted(
            self._alerts,
            key=lambda x: (level_priority.get(x["level"], 0), x["timestamp"]),
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
        import os
        from datetime import datetime
        import re
        
        logs = []
        # 使用相对路径，从当前文件所在目录向上找到项目根目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级目录到项目根目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        log_dir = os.path.join(project_root, "logs")
        
        # 支持的日志文件
        log_files = {
            "app": "app.log"
        }
        
        # 确定要读取的文件
        files_to_read = [("app", os.path.join(log_dir, fname)) for lvl, fname in log_files.items()]
        
        # 读取日志文件
        for log_level, file_path in files_to_read:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    # 使用正则表达式匹配完整的日志条目（支持多行消息）
                    # 日志格式: 2026-04-05 07:45:01,442 - module - ... - LEVEL - message
                    log_pattern = re.compile(
                        r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+?) - (?:.*? - )?(ERROR|WARNING|INFO|DEBUG) - (.*?)(?=\n\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} - |\Z)',
                        re.DOTALL
                    )
                    
                    # 查找所有匹配的日志
                    matches = list(log_pattern.finditer(content))
                    
                    # 倒序处理，获取最新的日志
                    for match in reversed(matches):
                        timestamp_str = match.group(1)
                        module = match.group(2).strip()
                        log_level_str = match.group(3)
                        message = match.group(4).strip()
                        
                        # 解析时间戳
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f').timestamp()
                        except ValueError:
                            continue
                        
                        # 提取模块名（去掉.log后缀和可能的文件名信息）
                        module = module.replace('.log', '')
                        
                        # 统一日志级别格式
                        log_level_str = log_level_str.lower()
                        
                        # 根据级别过滤
                        if level and log_level_str != level:
                            continue
                        
                        # 包含所有级别的日志
                        logs.append({
                            "level": log_level_str,
                            "message": message,
                            "timestamp": timestamp,
                            "module": module,
                            "traceback": None  # 简单日志格式不包含堆栈信息
                        })
                            
                        if len(logs) >= limit:
                            break
                except Exception as e:
                    logger.error(f"读取日志文件失败: {e}")
        
        # 按时间倒序排序
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return logs[:limit]


# 全局监控服务实例
monitor_service = MonitorService()
