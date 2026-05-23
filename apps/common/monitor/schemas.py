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


class JobExecutionRecord(BaseModel):
    """任务执行记录"""
    time: Optional[str] = Field(None, description="执行时间")
    error: Optional[str] = Field(None, description="错误信息")


class JobInfo(BaseModel):
    """定时任务信息"""
    id: str = Field(description="任务 ID")
    name: str = Field(description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    trigger: str = Field(description="触发器")
    next_run_time: Optional[str] = Field(None, description="下次执行时间")
    last_run_time: Optional[str] = Field(None, description="上次执行时间")
    last_error: Optional[str] = Field(None, description="最后一次错误信息")
    execution_history: List[JobExecutionRecord] = Field(default_factory=list, description="执行历史记录")
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


class EventTypeStats(BaseModel):
    """单个事件类型的统计数据"""
    event_type: str = Field(description="事件类型标识")
    description: str = Field(description="事件描述")
    
    total_received: int = Field(0, description="总接收数")
    total_processed: int = Field(0, description="已处理数")
    total_failed: int = Field(0, description="失败数")
    pending_count: int = Field(0, description="待处理数")
    
    success_rate: float = Field(0.0, description="成功率 (%)")
    
    avg_processing_latency: float = Field(0.0, description="平均处理延迟 (ms)")
    
    last_activity_time: Optional[float] = Field(None, description="最后活动时间戳")
    first_received_time: Optional[float] = Field(None, description="首次接收时间戳")
    
    batch_size: int = Field(description="批量大小")
    flush_interval: float = Field(description="刷新间隔 (秒)")
    current_buffer_size: int = Field(0, description="当前缓冲区大小")
    
    events_last_minute: int = Field(0, description="最近1分钟事件数")
    events_last_hour: int = Field(0, description="最近1小时事件数")
    events_today: int = Field(0, description="今日事件数")


class EventMetrics(BaseModel):
    """事件监控指标"""
    timestamp: float = Field(description="时间戳")
    event_stats: Dict[str, EventTypeStats] = Field(default_factory=dict, description="各事件类型统计")
    summary: Dict[str, Any] = Field(default_factory=dict, description="汇总信息")


class PaginationMeta(BaseModel):
    """分页元数据"""
    page: int = Field(description="当前页码（从1开始）")
    page_size: int = Field(description="每页条数")
    total_count: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")
    start_index: int = Field(description="当前页起始索引")
    end_index: int = Field(description="当前页结束索引")


class QueryResponse(BaseModel):
    """查询响应基类（包含分页）"""
    pagination: Optional[PaginationMeta] = Field(None, description="分页元数据")
    time_range: Optional[Dict[str, Any]] = Field(None, description="时间范围")
    filter_params: Optional[Dict[str, Any]] = Field(None, description="过滤条件")


class HistoryQueryResponse(QueryResponse):
    """历史查询响应"""
    http_requests: List[Dict[str, Any]] = Field(default_factory=list, description="接收请求列表")
    outbound_requests: List[Dict[str, Any]] = Field(default_factory=list, description="发送请求列表")
    logs: List[Dict[str, Any]] = Field(default_factory=list, description="系统日志列表")
