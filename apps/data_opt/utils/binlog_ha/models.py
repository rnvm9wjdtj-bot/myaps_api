"""
Binlog 监听器高可用增强 - 数据模型定义

包含配置模型、监控指标模型、事件模型等
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List, Literal
from enum import Enum
from datetime import datetime


class EnvMode(str, Enum):
    """运行环境模式"""
    SINGLE_NODE = "single_node"
    MULTI_WORKER = "multi_worker"


class FallbackMode(str, Enum):
    """降级模式"""
    REDIS = "redis"
    SINGLE_INSTANCE = "single_instance"
    REJECT = "reject"


class ListenerStatus(str, Enum):
    """监听器状态"""
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class ConnectionStatus(str, Enum):
    """连接状态"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


class ListenerRole(str, Enum):
    """监听器角色"""
    MASTER = "master"
    SLAVE = "slave"
    STANDALONE = "standalone"


class PressureState(str, Enum):
    """背压状态"""
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"


class ErrorType(str, Enum):
    """错误类型（用于重试策略分类）"""
    NETWORK_TIMEOUT = "network_timeout"
    TEMPORARY_ERROR = "temporary_error"
    RESOURCE_LIMIT = "resource_limit"
    PERMANENT_ERROR = "permanent_error"


class EventType(str, Enum):
    """事件类型"""
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class BinlogConfig(BaseModel):
    """Binlog监听器配置"""
    
    turnon_binlog_listener: bool = Field(
        default=False,
        description="监听器总开关"
    )
    enable_binlog_position: bool = Field(
        default=False,
        description="Binlog位置持久化开关"
    )
    
    redis_host: str = Field(
        default="127.0.0.1",
        description="Redis服务地址"
    )
    redis_port: int = Field(
        default=6379,
        ge=1, le=65535,
        description="Redis服务端口"
    )
    redis_password: Optional[str] = Field(
        default=None,
        description="Redis访问密码"
    )
    
    lock_timeout_seconds: int = Field(
        default=30,
        ge=10, le=300,
        description="分布式锁超时时间（秒）"
    )
    environment_mode: EnvMode = Field(
        default=EnvMode.SINGLE_NODE,
        description="运行环境模式"
    )
    
    heartbeat_interval_seconds: int = Field(
        default=5,
        ge=1, le=60,
        description="心跳间隔时间（秒）"
    )
    heartbeat_timeout_seconds: int = Field(
        default=30,
        ge=10, le=120,
        description="心跳超时时间（秒）"
    )
    
    max_retry_attempts: int = Field(
        default=10,
        ge=1, le=20,
        description="最大重试次数"
    )
    base_retry_delay_seconds: float = Field(
        default=5.0,
        ge=1.0, le=60.0,
        description="基础重试延迟（秒）"
    )
    max_retry_delay_seconds: float = Field(
        default=300.0,
        ge=60.0, le=600.0,
        description="最大重试延迟（秒）"
    )
    
    enable_deduplication: bool = Field(
        default=True,
        description="启用事件去重"
    )
    dedup_ttl_hours: int = Field(
        default=24,
        ge=1, le=168,
        description="事件去重TTL（小时）"
    )
    
    backpressure_warning_threshold: int = Field(
        default=1000,
        ge=100, le=10000,
        description="背压告警阈值"
    )
    backpressure_limit_threshold: int = Field(
        default=5000,
        ge=1000, le=50000,
        description="背压限流阈值"
    )
    backpressure_pause_seconds: int = Field(
        default=5,
        ge=1, le=30,
        description="背压暂停时长（秒）"
    )
    backpressure_check_interval: int = Field(
        default=10,
        ge=1, le=100,
        description="背压检查间隔（事件数）"
    )
    
    @field_validator('backpressure_limit_threshold')
    @classmethod
    def validate_thresholds(cls, v, info):
        """限流阈值必须大于告警阈值"""
        warning = info.data.get('backpressure_warning_threshold', 1000)
        if v <= warning:
            raise ValueError(f'限流阈值({v})必须大于告警阈值({warning})')
        return v
    
    class Config:
        use_enum_values = True


class MetricsSnapshot(BaseModel):
    """监控指标快照"""
    
    listener_status: ListenerStatus
    connection_status: ConnectionStatus
    listener_role: ListenerRole
    
    events_processed_total: int = Field(ge=0)
    events_dropped_total: int = Field(ge=0)
    events_queue_size: int = Field(ge=0)
    processing_delay_seconds: float = Field(ge=0)
    
    retry_attempts_total: int = Field(ge=0)
    error_count_total: int = Field(ge=0)
    
    backpressure_state: PressureState
    throttle_count_total: int = Field(ge=0)
    throttle_duration_total: float = Field(ge=0)
    
    failover_count_total: int = Field(ge=0)
    heartbeat_delay_seconds: float = Field(ge=0)
    
    connection_pool_active: int = Field(ge=0)
    memory_usage_mb: float = Field(ge=0)
    
    timestamp: datetime
    
    class Config:
        use_enum_values = True


class BinlogEvent(BaseModel):
    """Binlog事件"""
    
    event_type: EventType
    table_name: str
    database_name: str
    primary_key: str
    timestamp: float
    log_file: str
    log_pos: int
    data: Dict[str, Any]
    
    def generate_identifier(self) -> str:
        """生成事件唯一标识符"""
        import hashlib
        raw = f"{self.event_type}|{self.table_name}|{self.primary_key}|{self.timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()


class EventMeta(BaseModel):
    """事件元数据"""
    
    event_id: str
    event_type: EventType
    table_name: str
    database_name: str
    log_file: str
    log_pos: int
    timestamp: float
    processed_at: datetime


class HealthCheck(BaseModel):
    """单个健康检查项"""
    status: Literal["pass", "warn", "fail"]
    message: str
    details: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: Literal["healthy", "degraded", "unhealthy"]
    checks: Dict[str, HealthCheck]
    timestamp: datetime


class AuditAction(str, Enum):
    """审计操作类型"""
    UPDATE_CONFIG = "UPDATE_CONFIG"
    MANUAL_FAILOVER = "MANUAL_FAILOVER"
    CLEAR_POSITION = "CLEAR_POSITION"
    START_LISTENER = "START_LISTENER"
    STOP_LISTENER = "STOP_LISTENER"


class AuditEntry(BaseModel):
    """审计日志条目"""
    
    audit_id: str
    timestamp: datetime
    operator: str
    action: AuditAction
    changes: Optional[List[Dict[str, Any]]] = None
    result: Literal["success", "failure"]
    reason: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        use_enum_values = True
