"""
Binlog监听器简化版HA模块

提供以下核心能力:
- Prometheus指标暴露
- 重试策略管理
- 背压控制
- 事件去重
"""

from .models import (
    EventType,
    PressureState,
    ErrorType,
    BinlogEvent,
    EventMeta,
    BinlogPosition,
    QueueMetrics,
)

from .prometheus_metrics import PrometheusMetrics, prometheus_metrics
from .retry_policy import RetryPolicy, retry_policy, with_retry
from .backpressure_controller import BackpressureController, backpressure_controller
from .event_deduplicator import EventDeduplicator, event_deduplicator

__all__ = [
    "EventType",
    "PressureState",
    "ErrorType",
    "BinlogEvent",
    "EventMeta",
    "BinlogPosition",
    "QueueMetrics",
    "PrometheusMetrics",
    "prometheus_metrics",
    "RetryPolicy",
    "retry_policy",
    "with_retry",
    "BackpressureController",
    "backpressure_controller",
    "EventDeduplicator",
    "event_deduplicator",
]