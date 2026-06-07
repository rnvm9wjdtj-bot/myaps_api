"""
数据库连接池管理模块

提供连接池状态管理、健康检查、安全刷新、泄漏检测和后台清理功能。
"""
from globalobjects.db_pool.db_pool_models import (
    ConnectionPoolState,
    LeakSeverity,
    TrendType,
    AlertLevel,
    AlertType,
    ConnectionPoolStateInfo,
    HealthCheckResult,
    ConnectionPoolStatus,
    UsageRecord,
    TrendAnalysis,
    LeakDetectionResult,
    AlertMessage,
    PendingCleanupItem,
    PoolManagerConfig
)
from globalobjects.db_pool.db_pool_exceptions import (
    DbPoolError,
    ConnectionPoolUnavailableError,
    ConnectionPoolStateError,
    HealthCheckError,
    ConnectionRefreshError,
    CleanupQueueFullError,
    ForceCloseError,
    StateTransitionError
)
from globalobjects.db_pool.db_pool_state_manager import ConnectionPoolStateManager
from globalobjects.db_pool.db_health_checker import HealthChecker
from globalobjects.db_pool.db_connection_refresher import SafeConnectionRefresher
from globalobjects.db_pool.db_leak_detector import EnhancedConnectionLeakDetector
from globalobjects.db_pool.db_cleanup_task import BackgroundCleanupTask
from globalobjects.db_pool.db_enhanced_manager import (
    EnhancedDbManager,
    get_enhanced_db_manager
)
from globalobjects.db_pool.db_pool_monitor import (
    PoolMonitorTask,
    start_pool_monitoring,
    stop_pool_monitoring,
    get_pool_monitor_status
)

__all__ = [
    # 数据模型
    "ConnectionPoolState",
    "LeakSeverity",
    "TrendType",
    "AlertLevel",
    "AlertType",
    "ConnectionPoolStateInfo",
    "HealthCheckResult",
    "ConnectionPoolStatus",
    "UsageRecord",
    "TrendAnalysis",
    "LeakDetectionResult",
    "AlertMessage",
    "PendingCleanupItem",
    "PoolManagerConfig",
    # 异常类
    "DbPoolError",
    "ConnectionPoolUnavailableError",
    "ConnectionPoolStateError",
    "HealthCheckError",
    "ConnectionRefreshError",
    "CleanupQueueFullError",
    "ForceCloseError",
    "StateTransitionError",
    # 核心组件
    "ConnectionPoolStateManager",
    "HealthChecker",
    "SafeConnectionRefresher",
    "EnhancedConnectionLeakDetector",
    "BackgroundCleanupTask",
    "EnhancedDbManager",
    # 监控任务
    "PoolMonitorTask",
    # 工具函数
    "get_enhanced_db_manager",
    "start_pool_monitoring",
    "stop_pool_monitoring",
    "get_pool_monitor_status"
]