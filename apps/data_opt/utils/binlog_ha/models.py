"""
Binlog 监听器简化版 - 数据模型定义

仅保留核心功能相关模型
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


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


class BinlogPosition(BaseModel):
    """Binlog位置"""
    
    log_file: str
    log_pos: int
    timestamp: datetime
    
    class Config:
        use_enum_values = True


class QueueMetrics(BaseModel):
    """队列指标"""
    
    queue_size: int = Field(ge=0)
    max_size: int = Field(ge=1)
    usage_percent: float = Field(ge=0, le=100)
    
    @property
    def is_overloaded(self) -> bool:
        """队列是否过载"""
        return self.usage_percent > 80
