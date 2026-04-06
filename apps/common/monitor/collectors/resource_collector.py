"""
资源指标采集器

采集 CPU、内存、线程等系统资源指标
"""

import time
import psutil
from typing import Dict, Any, Optional
from globalobjects import logger as log_config

logger = log_config.get_logger(__name__)


class ResourceCollector:
    """资源指标采集器"""

    def __init__(self):
        self._process = psutil.Process()
        self._cpu_count = psutil.cpu_count()


    def get_current_metrics(self) -> Dict[str, Any]:
        """
        获取当前资源使用指标

        Returns:
            Dict: 包含 CPU、内存、线程等指标的字典
        """
        try:
            memory = self._process.memory_info()
            system_cpu = psutil.cpu_percent(interval=0.1)
            process_cpu = self._process.cpu_percent(interval=0.0)
            threads = self._process.num_threads()

            return {
                "timestamp": time.time(),
                "memory": {
                    "rss": round(memory.rss / 1024 / 1024, 2),
                    "vms": round(memory.vms / 1024 / 1024, 2),
                    "percent": round(self._process.memory_percent(), 2),
                },
                "cpu": {
                    "system": round(system_cpu, 2),
                    "process": round(process_cpu, 2),
                    "process_system_percent": round(process_cpu / self._cpu_count, 2) if self._cpu_count else 0,
                    "count": self._cpu_count,
                },
                "threads": threads,
                "uptime": round(time.time() - self._process.create_time(), 2),
            }
        except Exception as e:
            logger.error(f"采集资源指标失败: {e}")
            return {
                "timestamp": time.time(),
                "error": str(e),
            }


    def get_system_info(self) -> Dict[str, Any]:
        """
        获取系统信息

        Returns:
            Dict: 系统基本信息
        """
        try:
            return {
                "platform": psutil.platform(),
                "cpu_count": self._cpu_count,
                "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                "memory_total": round(psutil.virtual_memory().total / 1024 / 1024 / 1024, 2),
                "disk_usage": {
                    path: psutil.disk_usage(path)._asdict()
                    for path in ["/", "C:\\"] if psutil.disk_usage(path)
                },
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return {"error": str(e)}


    def check_thresholds(self, metrics: Dict[str, Any], thresholds: Optional[Dict[str, float]] = None) -> list:
        """
        检查指标是否超过阈值

        Args:
            metrics: 资源指标
            thresholds: 自定义阈值，默认使用内置阈值

        Returns:
            list: 告警信息列表
        """
        # 从settings.py加载阈值
        from config.settings import MONITOR_THRESHOLDS
        resource_thresholds = MONITOR_THRESHOLDS.get('resource', {})
        
        default_thresholds = {
            "cpu": resource_thresholds.get('cpu', 80.0),
            "memory": resource_thresholds.get('memory', 80.0),
            "threads": resource_thresholds.get('threads', 200),
        }
        check_thresholds = thresholds or default_thresholds
        alerts = []

        if "cpu" in check_thresholds and "cpu" in metrics:
            cpu_system = metrics["cpu"].get("system", 0)
            if cpu_system > check_thresholds["cpu"]:
                alerts.append(f"CPU使用率 ({cpu_system}%) 超过阈值 ({check_thresholds['cpu']}%)")

        if "memory" in check_thresholds and "memory" in metrics:
            mem_percent = metrics["memory"].get("percent", 0)
            if mem_percent > check_thresholds["memory"]:
                alerts.append(f"内存使用率 ({mem_percent}%) 超过阈值 ({check_thresholds['memory']}%)")

        if "threads" in check_thresholds:
            threads = metrics.get("threads", 0)
            if threads > check_thresholds["threads"]:
                alerts.append(f"线程数 ({threads}) 超过阈值 ({check_thresholds['threads']})")

        return alerts
