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
        import os
        from datetime import datetime
        
        logs = []
        log_dir = "d:\\code\\myaps_fastapi\\logs"
        
        # 支持的日志文件
        log_files = {
            "error": "error.log",
            "warning": "app.log"
        }
        
        # 确定要读取的文件
        if level:
            if level in log_files:
                files_to_read = [(level, os.path.join(log_dir, log_files[level]))]
            else:
                return []
        else:
            files_to_read = [(lvl, os.path.join(log_dir, fname)) for lvl, fname in log_files.items()]
        
        # 读取日志文件
        for log_level, file_path in files_to_read:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        
                    # 倒序读取，获取最新的日志
                    for line in reversed(lines):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 解析日志格式，支持两种格式：
                        # 1. 旧格式: 2026-02-04 21:32:29,631 - project_files._base_error.log - ERROR - ❌ 领料申请推送失败...
                        # 2. 新格式: 2026-04-03 16:06:38,458 - smart_apps.io_api.utils.db_operation - _log_to_file:999 - ERROR - 鉂?鏁版嵁搴撻獙璇佸け璐...
                        parts = line.split(' - ')
                        if len(parts) < 4:
                            continue
                        
                        timestamp_str = parts[0]
                        if len(parts) == 4:
                            # 旧格式
                            module, log_level_str, message = parts[1], parts[2], parts[3]
                        else:
                            # 新格式
                            module = parts[1]
                            # 找到日志级别字段（通常是倒数第二个）
                            log_level_str = None
                            for i in range(len(parts)-1, 1, -1):
                                if parts[i].upper() in ['ERROR', 'WARNING', 'INFO', 'DEBUG']:
                                    log_level_str = parts[i]
                                    # 消息是级别后面的所有内容
                                    message = ' - '.join(parts[i+1:])
                                    break
                            if not log_level_str:
                                continue
                        
                        # 解析时间戳
                        try:
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f').timestamp()
                        except ValueError:
                            continue
                        
                        # 提取模块名（去掉.log后缀）
                        module = module.replace('.log', '')
                        
                        # 统一日志级别格式
                        log_level_str = log_level_str.lower()
                        if log_level_str in ['error', 'warning']:
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
