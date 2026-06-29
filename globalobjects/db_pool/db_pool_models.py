"""
数据库连接池管理数据模型

定义连接池管理所需的所有数据模型、枚举类型和配置对象。
"""
import time
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


def check_cooldown(
    timestamps: Dict[str, float],
    key: str,
    cooldown: int
) -> bool:
    """
    检查冷却状态并消耗冷却

    如果距离上次记录的时间超过冷却期，则更新记录并返回 True；
    否则返回 False。

    Args:
        timestamps: 时间戳记录字典
        key: 要检查的键（如连接名称）
        cooldown: 冷却时间（秒）

    Returns:
        True 如果允许操作（不在冷却期内），False 如果在冷却期内
    """
    current_time = time.time()
    last_time = timestamps.get(key, 0)
    if current_time - last_time >= cooldown:
        timestamps[key] = current_time
        return True
    return False


class ConnectionPoolState(str, Enum):
    """连接池状态枚举"""
    OPEN = "open"
    CLOSED = "closed"
    REFRESHING = "refreshing"


class LeakSeverity(str, Enum):
    """泄漏严重程度枚举"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class TrendType(str, Enum):
    """使用率趋势类型枚举"""
    STABLE = "stable"
    INCREASING = "increasing"
    DECREASING = "decreasing"


class AlertLevel(str, Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(str, Enum):
    """告警类型枚举"""
    LEAK_DETECTED = "leak_detected"
    POOL_UNAVAILABLE = "pool_unavailable"
    HEALTH_CHECK_FAILED = "health_check_failed"
    REFRESH_FAILED = "refresh_failed"
    CLEANUP_FAILED = "cleanup_failed"


class ConnectionPoolStateInfo(BaseModel):
    """连接池状态信息模型"""
    connection_name: str = Field(..., description="连接名称")
    state: ConnectionPoolState = Field(..., description="当前状态")
    last_update_time: Optional[datetime] = Field(None, description="最后更新时间")
    update_reason: Optional[str] = Field(None, description="更新原因")
    is_available: bool = Field(..., description="是否可用")


class HealthCheckResult(BaseModel):
    """健康检查结果模型"""
    is_healthy: bool = Field(..., description="是否健康")
    response_time: Optional[float] = Field(None, description="响应时间(秒)")
    error_message: Optional[str] = Field(None, description="错误消息")
    check_time: datetime = Field(default_factory=datetime.now, description="检查时间")
    connection_name: Optional[str] = Field(None, description="连接名称")


class ConnectionPoolStatus(BaseModel):
    """连接池状态模型"""
    connection_name: str = Field(..., description="连接名称")
    total_connections: int = Field(0, description="总连接数")
    used_connections: int = Field(0, description="已用连接数")
    idle_connections: int = Field(0, description="空闲连接数")
    usage_rate: float = Field(0.0, description="使用率(百分比)")
    pool_available: bool = Field(True, description="连接池是否可用")
    last_check_time: Optional[datetime] = Field(None, description="最后检查时间")


class UsageRecord(BaseModel):
    """使用记录模型"""
    connection_name: str = Field(..., description="连接名称")
    usage_rate: float = Field(..., description="使用率")
    used_connections: int = Field(..., description="已用连接数")
    total_connections: int = Field(..., description="总连接数")
    is_healthy: bool = Field(True, description="是否健康")
    pool_available: bool = Field(True, description="连接池是否可用")
    record_time: datetime = Field(default_factory=datetime.now, description="记录时间")


class TrendAnalysis(BaseModel):
    """趋势分析结果模型"""
    trend_type: TrendType = Field(..., description="趋势类型")
    slope: float = Field(..., description="线性回归斜率")
    confidence: float = Field(..., description="置信度")
    data_points: int = Field(..., description="数据点数量")


class LeakDetectionResult(BaseModel):
    """泄漏检测结果模型"""
    leak_detected: bool = Field(..., description="是否检测到泄漏")
    severity: LeakSeverity = Field(..., description="严重程度")
    usage_rate: float = Field(0.0, description="当前使用率")
    avg_usage_rate: float = Field(0.0, description="平均使用率")
    max_usage_rate: float = Field(0.0, description="最高使用率")
    health_check_failure_rate: float = Field(0.0, description="健康检查失败率")
    trend: Optional[TrendAnalysis] = Field(None, description="趋势分析")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")
    detection_time: datetime = Field(default_factory=datetime.now, description="检测时间")


class AlertMessage(BaseModel):
    """告警消息模型"""
    alert_id: str = Field(..., description="告警ID")
    alert_type: AlertType = Field(..., description="告警类型")
    alert_level: AlertLevel = Field(..., description="告警级别")
    connection_name: str = Field(..., description="连接名称")
    message: str = Field(..., description="告警消息")
    details: Dict[str, Any] = Field(default_factory=dict, description="详细信息")
    suggestion: Optional[str] = Field(None, description="处理建议")
    alert_time: datetime = Field(default_factory=datetime.now, description="告警时间")


class PendingCleanupItem(BaseModel):
    """待清理项模型"""
    connection: Any = Field(..., description="连接对象")
    connection_name: str = Field(..., description="连接名称")
    reason: str = Field(..., description="清理原因")
    add_time: datetime = Field(default_factory=datetime.now, description="添加时间")
    retry_count: int = Field(0, description="重试次数")
    max_retries: int = Field(3, description="最大重试次数")


class PoolManagerConfig(BaseModel):
    """连接池管理器配置模型"""
    health_check_timeout: float = Field(5.0, description="健康检查超时时间(秒)")
    health_check_sql: str = Field("SELECT 1", description="健康检查SQL")
    cleanup_interval: int = Field(300, description="清理任务间隔(秒)")
    max_cleanup_time: int = Field(30, description="单次清理最大时间(秒)")
    max_cleanup_queue_size: int = Field(100, description="清理队列最大大小")
    leak_warning_threshold: int = Field(80, description="泄漏警告阈值(百分比)")
    leak_critical_threshold: int = Field(90, description="泄漏严重阈值(百分比)")
    leak_emergency_threshold: int = Field(95, description="泄漏紧急阈值(百分比)")
    leak_history_size: int = Field(100, description="泄漏检测历史数据大小")
    leak_analysis_window: int = Field(300, description="泄漏检测分析窗口(秒)")
    state_lock_timeout: float = Field(10.0, description="状态锁超时时间(秒)")
    alert_cooldown: int = Field(300, description="告警冷却时间(秒)")