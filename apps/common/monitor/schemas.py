"""
监控模块数据模型

定义监控相关的 Pydantic 模型
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class MemoryMetrics(BaseModel):
    """内存指标"""
    rss: float = Field(description="实际使用内存 (MB)")
    vms: float = Field(description="虚拟内存 (MB)")
    percent: float = Field(description="内存使用百分比")


class CPUMetrics(BaseModel):
    """CPU 指标"""
    system: float = Field(description="系统 CPU 使用率 (%)")
    process: float = Field(description="进程 CPU 使用率 (%)")
    process_system_percent: float = Field(description="进程相对于系统的 CPU 使用率 (%)")
    count: int = Field(description="CPU 核心数")


class ResourceMetrics(BaseModel):
    """资源使用指标"""
    timestamp: float = Field(description="时间戳")
    memory: Optional[MemoryMetrics] = Field(None, description="内存指标")
    cpu: Optional[CPUMetrics] = Field(None, description="CPU 指标")
    threads: int = Field(description="线程数")
    uptime: float = Field(description="运行时间 (秒)")
    error: Optional[str] = Field(None, description="错误信息")


class DBConnectionStatus(BaseModel):
    """数据库连接状态"""
    healthy: bool = Field(description="是否健康")
    last_check: Optional[float] = Field(None, description="最后检查时间")
    error: Optional[str] = Field(None, description="错误信息")


class DBConnectionSummary(BaseModel):
    """数据库连接汇总"""
    total: int = Field(description="总连接数")
    healthy: int = Field(description="健康连接数")
    unhealthy: int = Field(description="不健康连接数")


class DBMetrics(BaseModel):
    """数据库监控指标"""
    timestamp: float = Field(description="时间戳")
    connections: Dict[str, Any] = Field(description="数据库连接状态信息")
    pool: Dict[str, Any] = Field(description="连接池状态信息")


class JobInfo(BaseModel):
    """定时任务信息"""
    id: str = Field(description="任务 ID")
    name: str = Field(description="任务名称")
    trigger: str = Field(description="触发器")
    next_run_time: Optional[str] = Field(None, description="下次执行时间")
    pending: bool = Field(description="是否等待执行")


class SchedulerStatus(BaseModel):
    """调度器状态"""
    timestamp: float = Field(description="时间戳")
    running: bool = Field(description="是否运行中")
    initialized: bool = Field(description="是否已初始化")
    error: Optional[str] = Field(None, description="错误信息")


class SchedulerMetrics(BaseModel):
    """定时任务监控指标"""
    timestamp: float = Field(description="时间戳")
    scheduler: SchedulerStatus = Field(description="调度器状态")
    jobs: List[JobInfo] = Field(description="任务列表")
    job_count: int = Field(description="任务数量")


class HealthStatus(BaseModel):
    """健康检查状态"""
    status: str = Field(description="整体状态: healthy/degraded/unhealthy")
    timestamp: float = Field(description="时间戳")
    checks: Dict[str, Any] = Field(description="各项检查结果")
    message: Optional[str] = Field(None, description="状态说明")


class AlertInfo(BaseModel):
    """告警信息"""
    level: str = Field(description="告警级别: info/warning/error/critical")
    message: str = Field(description="告警内容")
    timestamp: float = Field(description="告警时间")
    source: str = Field(description="告警来源")


class MonitorOverview(BaseModel):
    """监控总览"""
    timestamp: float = Field(description="时间戳")
    resource: ResourceMetrics = Field(description="资源指标")
    database: DBMetrics = Field(description="数据库指标")
    scheduler: SchedulerMetrics = Field(description="定时任务指标")
    alerts: List[AlertInfo] = Field(default_factory=list, description="当前告警")
