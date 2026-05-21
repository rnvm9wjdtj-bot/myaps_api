"""
Binlog 监听器高可用增强模块

提供以下核心能力：
- Prometheus 指标暴露
- 重试策略管理
- 连接池监控
- 健康检查增强
- 背压控制
- 事件去重
- 配置热更新
- 主备故障转移
"""

from .models import (
    EnvMode,
    FallbackMode,
    ListenerStatus,
    ConnectionStatus,
    ListenerRole,
    PressureState,
    ErrorType,
    EventType,
    BinlogConfig,
    MetricsSnapshot,
    BinlogEvent,
    EventMeta,
    HealthCheck,
    HealthResponse,
    AuditAction,
    AuditEntry,
)

from .prometheus_metrics import PrometheusMetrics, prometheus_metrics
from .retry_policy import RetryPolicy, retry_policy, with_retry
from .connection_monitor import (
    ConnectionPoolMonitor,
    ManagedConnection,
    ConnectionInfo,
    LeakInfo,
    PoolStats,
    connection_pool_monitor,
    tracked_connection,
)
from .health_check import HealthChecker, health_checker
from .backpressure_controller import BackpressureController, backpressure_controller, QueueMetrics
from .event_deduplicator import EventDeduplicator, event_deduplicator
from .config_manager import ConfigManager, config_manager
from .enhanced_lock import EnhancedDistributedLock, enhanced_distributed_lock, LockResult
from .failover_manager import FailoverManager, failover_manager

__all__ = [
    "EnvMode",
    "FallbackMode",
    "ListenerStatus",
    "ConnectionStatus",
    "ListenerRole",
    "PressureState",
    "ErrorType",
    "EventType",
    "BinlogConfig",
    "MetricsSnapshot",
    "BinlogEvent",
    "EventMeta",
    "HealthCheck",
    "HealthResponse",
    "AuditAction",
    "AuditEntry",
    "PrometheusMetrics",
    "prometheus_metrics",
    "RetryPolicy",
    "retry_policy",
    "with_retry",
    "ConnectionPoolMonitor",
    "ManagedConnection",
    "ConnectionInfo",
    "LeakInfo",
    "PoolStats",
    "connection_pool_monitor",
    "tracked_connection",
    "HealthChecker",
    "health_checker",
    "BackpressureController",
    "backpressure_controller",
    "QueueMetrics",
    "EventDeduplicator",
    "event_deduplicator",
    "ConfigManager",
    "config_manager",
    "EnhancedDistributedLock",
    "enhanced_distributed_lock",
    "LockResult",
    "FailoverManager",
    "failover_manager",
]
