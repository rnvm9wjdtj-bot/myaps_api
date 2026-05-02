"""
事件监控指标采集器

采集事件聚合器的统计信息
"""

import time
import importlib
from typing import Dict, Any
from globalobjects import logger as log_config
from globalobjects.event_aggregator import get_global_handler_aggregator
from core.settings import PROJECT_DIR


logger = log_config.get_logger(__name__)


def _event_has_handler(event_type) -> bool:
    """检查指定事件类型是否有对应的处理函数"""
    # 将枚举类型转换为字符串值
    if hasattr(event_type, 'value'):
        event_type_str = event_type.value
    else:
        event_type_str = str(event_type)
    
    handler_name = f"batch_handle_{event_type_str}"
    try:
        project_module = importlib.import_module(f'project_files.{PROJECT_DIR}.client')
        handler = getattr(project_module, handler_name, None)
        return handler is not None
    except Exception as e:
        logger.warning(f"检查事件处理函数失败 {event_type}: {e}")
        return False


class EventCollector:
    """事件监控指标采集器"""

    def __init__(self):
        self._aggregator = get_global_handler_aggregator()

    def get_event_metrics(self) -> Dict[str, Any]:
        """
        获取事件监控指标

        Returns:
            Dict: 事件监控指标
        """
        metrics = {
            "timestamp": time.time(),
            "event_stats": {},
            "summary": {},
        }

        try:
            all_stats = self._aggregator.get_all_stats()
            event_types = self._aggregator.get_event_types()

            total_received = 0
            total_processed = 0
            total_failed = 0
            total_pending = 0
            active_event_types = 0

            for event_type in event_types:
                if not _event_has_handler(event_type):
                    continue

                stats = all_stats.get(event_type, {})
                description = self._aggregator.get_event_description(event_type)

                metrics["event_stats"][event_type] = {
                    "event_type": event_type,
                    "description": description,
                    **stats
                }

                total_received += stats.get("total_received", 0)
                total_processed += stats.get("total_processed", 0)
                total_failed += stats.get("total_failed", 0)
                total_pending += stats.get("pending_count", 0)

                if stats.get("total_received", 0) > 0:
                    active_event_types += 1

            overall_success_rate = 100.0
            total = total_processed + total_failed
            if total > 0:
                overall_success_rate = (total_processed / total) * 100

            metrics["summary"] = {
                "total_received": total_received,
                "total_processed": total_processed,
                "total_failed": total_failed,
                "total_pending": total_pending,
                "overall_success_rate": overall_success_rate,
                "active_event_types": active_event_types,
                "total_event_types": len(event_types),
            }

        except Exception as e:
            logger.error(f"获取事件监控指标失败: {e}")
            metrics["error"] = str(e)

        return metrics

    def flush_now(self, event_type: str = None):
        """
        立即刷新事件聚合器

        Args:
            event_type: 指定事件类型，None表示刷新所有
        """
        self._aggregator.flush_now(event_type)

    def reset_stats(self, event_type: str = None):
        """
        重置统计数据

        Args:
            event_type: 指定事件类型，None表示重置所有
        """
        self._aggregator.reset_stats(event_type)
