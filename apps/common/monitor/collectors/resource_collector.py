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
    
    # 类级别的静态变量，用于网络带宽计算（跨实例共享）
    _class_last_network_stats = None
    _class_last_network_total = None
    _class_last_network_timestamp = None

    def __init__(self):
        self._process = psutil.Process()
        self._cpu_count = psutil.cpu_count()
        # 实例级别变量（CPU/内存等）
        self._last_network_stats = None
        self._last_network_total = None
        self._last_network_timestamp = None


    def get_current_metrics(self) -> Dict[str, Any]:
        """
        获取当前资源使用指标

        Returns:
            Dict: 包含 CPU、内存、线程等指标的字典
        """
        try:
            memory = self._process.memory_info()
            # 减少阻塞时间，提高响应速度
            system_cpu = psutil.cpu_percent(interval=0.01)
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

    async def get_current_metrics_async(self) -> Dict[str, Any]:
        """
        异步获取当前资源使用指标

        Returns:
            Dict: 包含 CPU、内存、线程等指标的字典
        """
        try:
            memory = self._process.memory_info()
            # 减少阻塞时间，提高响应速度
            system_cpu = psutil.cpu_percent(interval=0.01)
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
        from core.settings import MONITOR_THRESHOLDS
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

    def get_network_metrics(self) -> Dict[str, Any]:
        """
        获取网络 I/O 指标

        Returns:
            Dict: 包含各网络接口的发送/接收字节数、数据包数等指标
        """
        try:
            # 获取所有网络接口的 I/O 统计
            io_counters = psutil.net_io_counters(pernic=True)

            interfaces = {}
            for interface, counters in io_counters.items():
                # 过滤掉虚拟接口和回环接口（Windows）
                if interface.startswith('Loopback') or interface.startswith('veth'):
                    continue

                interfaces[interface] = {
                    "bytes_sent": counters.bytes_sent,
                    "bytes_recv": counters.bytes_recv,
                    "packets_sent": counters.packets_sent,
                    "packets_recv": counters.packets_recv,
                    "err_in": counters.errin,
                    "err_out": counters.errout,
                    "drop_in": counters.dropin,
                    "drop_out": counters.dropout,
                }

            return {
                "timestamp": time.time(),
                "interfaces": interfaces,
                "total": {
                    "bytes_sent": psutil.net_io_counters().bytes_sent,
                    "bytes_recv": psutil.net_io_counters().bytes_recv,
                    "packets_sent": psutil.net_io_counters().packets_sent,
                    "packets_recv": psutil.net_io_counters().packets_recv,
                    "err_in": psutil.net_io_counters().errin,
                    "err_out": psutil.net_io_counters().errout,
                    "drop_in": psutil.net_io_counters().dropin,
                    "drop_out": psutil.net_io_counters().dropout,
                }
            }
        except Exception as e:
            logger.error(f"采集网络指标失败: {e}")
            return {"error": str(e)}

    def get_network_bandwidth(self) -> Dict[str, Any]:
        """
        获取实时网络带宽（需要两次调用计算差值）

        Returns:
            Dict: 包含各网络接口的上传/下载带宽
        """
        current_stats = psutil.net_io_counters(pernic=True)
        current_total = psutil.net_io_counters()
        current_time = time.time()

        # 使用类级别的静态变量（跨请求共享）
        if ResourceCollector._class_last_network_stats is None or ResourceCollector._class_last_network_total is None:
            ResourceCollector._class_last_network_stats = current_stats
            ResourceCollector._class_last_network_total = current_total
            ResourceCollector._class_last_network_timestamp = current_time
            return {"message": "首次采样，等待下一次"}

        # 计算时间差
        time_diff = current_time - ResourceCollector._class_last_network_timestamp
        if time_diff < 0.1:
            return {"message": "采样间隔过短"}

        bandwidth = {}
        for interface, counters in current_stats.items():
            # 过滤掉虚拟接口和回环接口（Windows）
            if interface.startswith('Loopback') or interface.startswith('veth') or interface.startswith('蓝牙'):
                continue

            if interface not in ResourceCollector._class_last_network_stats:
                continue

            last = ResourceCollector._class_last_network_stats[interface]
            bandwidth[interface] = {
                "bps_sent": round((counters.bytes_sent - last.bytes_sent) / time_diff, 2),
                "bps_recv": round((counters.bytes_recv - last.bytes_recv) / time_diff, 2),
                "pps_sent": round((counters.packets_sent - last.packets_sent) / time_diff, 2),
                "pps_recv": round((counters.packets_recv - last.packets_recv) / time_diff, 2),
            }

        # 计算总带宽（使用正确的上次总计统计）
        total_bandwidth = {
            "bps_sent": round((current_total.bytes_sent - ResourceCollector._class_last_network_total.bytes_sent) / time_diff, 2),
            "bps_recv": round((current_total.bytes_recv - ResourceCollector._class_last_network_total.bytes_recv) / time_diff, 2),
            "pps_sent": round((current_total.packets_sent - ResourceCollector._class_last_network_total.packets_sent) / time_diff, 2),
            "pps_recv": round((current_total.packets_recv - ResourceCollector._class_last_network_total.packets_recv) / time_diff, 2),
        }

        # 更新类级别的缓存
        ResourceCollector._class_last_network_stats = current_stats
        ResourceCollector._class_last_network_total = current_total
        ResourceCollector._class_last_network_timestamp = current_time

        return {
            "timestamp": current_time,
            "interval": round(time_diff, 2),
            "interfaces": bandwidth,
            "total": total_bandwidth,
        }
