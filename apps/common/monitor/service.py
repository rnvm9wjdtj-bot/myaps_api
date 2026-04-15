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

    def _read_logs_reverse(self, file_path: str, max_logs: int, level_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        反向读取日志文件，从文件末尾开始读取
        
        Args:
            file_path: 日志文件路径
            max_logs: 最大日志数量
            level_filter: 日志级别过滤
            
        Returns:
            日志列表
        """
        import os
        from datetime import datetime
        import re
        
        logs = []
        CHUNK_SIZE = 64 * 1024
        
        log_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+?) - (?:.*? - )?(ERROR|WARNING|INFO|DEBUG) - (.*)$',
            re.MULTILINE
        )
        
        try:
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                return []
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                position = file_size
                buffer = ""
                lines_buffer = []
                
                while position > 0 and len(logs) < max_logs:
                    read_size = min(CHUNK_SIZE, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    
                    buffer = chunk + buffer
                    
                    lines = buffer.split('\n')
                    
                    if position > 0:
                        buffer = lines[0]
                        lines_to_process = lines[1:]
                    else:
                        lines_to_process = lines
                    
                    for line in reversed(lines_to_process):
                        if not line.strip():
                            continue
                        lines_buffer.append(line)
                        
                        if len(lines_buffer) >= 100:
                            self._parse_log_lines(lines_buffer, logs, max_logs, log_pattern, level_filter, datetime)
                            lines_buffer = []
                            
                            if len(logs) >= max_logs:
                                break
                
                if lines_buffer and len(logs) < max_logs:
                    self._parse_log_lines(lines_buffer, logs, max_logs, log_pattern, level_filter, datetime)
                    
        except Exception as e:
            logger.error(f"反向读取日志文件失败: {e}")
        
        return logs
    
    def _parse_log_lines(self, lines: List[str], logs: List[Dict], max_logs: int, 
                         log_pattern, level_filter: Optional[str], datetime) -> None:
        """
        解析日志行并添加到日志列表
        
        Args:
            lines: 日志行列表
            logs: 日志结果列表
            max_logs: 最大日志数量
            log_pattern: 正则表达式模式
            level_filter: 日志级别过滤
            datetime: datetime 模块
        """
        from collections import OrderedDict
        
        log_entries = OrderedDict()
        current_key = None
        
        for line in lines:
            match = log_pattern.match(line)
            if match:
                current_key = line
                log_entries[current_key] = line
            elif current_key and line.strip():
                log_entries[current_key] += '\n' + line
        
        for line in reversed(list(log_entries.values())):
            if len(logs) >= max_logs:
                break
                
            match = log_pattern.match(line)
            if not match:
                continue
            
            timestamp_str = match.group(1)
            module = match.group(2).strip()
            log_level_str = match.group(3)
            message = match.group(4).strip()
            
            try:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f').timestamp()
            except ValueError:
                continue
            
            module = module.replace('.log', '')
            log_level_str = log_level_str.lower()
            
            if level_filter and log_level_str != level_filter:
                continue
            
            logs.append({
                "level": log_level_str,
                "message": message,
                "timestamp": timestamp,
                "module": module,
                "traceback": None
            })

    def get_recent_logs(self, limit: int = 50, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取最近的日志（使用反向读取优化）
        
        Args:
            limit: 返回日志数量限制
            level: 日志级别过滤 (warning, error)
            
        Returns:
            日志列表
        """
        import os
        
        logs = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
        log_dir = os.path.join(project_root, "logs")
        
        log_file = os.path.join(log_dir, "app.log")
        
        if os.path.exists(log_file):
            logs = self._read_logs_reverse(log_file, limit, level)
        
        logs.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return logs[:limit]


# 全局监控服务实例
monitor_service = MonitorService()
