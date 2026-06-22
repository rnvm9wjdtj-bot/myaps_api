"""
Binlog 监听器 - Prometheus 指标暴露器

提供标准 Prometheus 指标采集和暴露功能
"""
from prometheus_client import Counter, Gauge, Histogram, Info, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response
from typing import Optional
import time

from globalobjects import logger


class PrometheusMetrics:
    """Prometheus 指标暴露器"""
    
    _instance = None
    _registry: Optional[CollectorRegistry] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._registry = CollectorRegistry()
        self._register_metrics()
        self._initialized = True
        logger.info("✅ Prometheus 指标暴露器已初始化")
    
    def _register_metrics(self):
        """注册所有指标"""
        
        self.listener_status = Gauge(
            'binlog_listener_status',
            'Listener running status (1=running, 0=stopped)',
            registry=self._registry
        )
        
        self.connection_status = Gauge(
            'binlog_connection_status',
            'MySQL connection status (1=connected, 0=disconnected)',
            registry=self._registry
        )
        
        self.binlog_position = Gauge(
            'binlog_position',
            'Current binlog position',
            ['file'],
            registry=self._registry
        )
        
        self.events_processed = Counter(
            'binlog_events_processed_total',
            'Total number of events processed',
            ['type'],
            registry=self._registry
        )
        
        self.events_dropped = Counter(
            'binlog_events_dropped_total',
            'Total number of events dropped',
            ['reason'],
            registry=self._registry
        )
        
        self.processing_delay = Histogram(
            'binlog_processing_delay_seconds',
            'Event processing delay in seconds',
            registry=self._registry,
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        )
        
        self.retry_attempts = Counter(
            'binlog_retry_attempts_total',
            'Total number of retry attempts',
            ['error_type'],
            registry=self._registry
        )
        
        self.error_count = Counter(
            'binlog_errors_total',
            'Total number of errors',
            ['type'],
            registry=self._registry
        )
        
        self.queue_size = Gauge(
            'binlog_queue_size',
            'Current event queue size',
            registry=self._registry
        )
        
        self.connection_pool_active = Gauge(
            'binlog_connection_pool_active',
            'Number of active connections in pool',
            registry=self._registry
        )
        
        self.memory_usage = Gauge(
            'binlog_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self._registry
        )
        
        self.backpressure_events = Counter(
            'binlog_backpressure_events_total',
            'Total number of backpressure events',
            ['state'],
            registry=self._registry
        )
        
        self.throttle_duration = Counter(
            'binlog_throttle_duration_seconds_total',
            'Total throttle duration in seconds',
            registry=self._registry
        )
        

        self.dedup_hits = Counter(
            'binlog_dedup_hits_total',
            'Total number of duplicate events detected',
            registry=self._registry
        )
        
        self.listener_info = Info(
            'binlog_listener',
            'Listener information',
            registry=self._registry
        )
    
    def set_listener_status(self, running: bool):
        """设置监听器状态"""
        self.listener_status.set(1 if running else 0)
    
    def set_connection_status(self, connected: bool):
        """设置连接状态"""
        self.connection_status.set(1 if connected else 0)
    
    def set_binlog_position(self, log_file: str, log_pos: int):
        """设置 Binlog 位置"""
        self.binlog_position.labels(file=log_file).set(log_pos)
    
    def inc_events_processed(self, event_type: str, count: int = 1):
        """增加已处理事件计数"""
        self.events_processed.labels(type=event_type).inc(count)
    
    def inc_events_dropped(self, reason: str, count: int = 1):
        """增加丢弃事件计数"""
        self.events_dropped.labels(reason=reason).inc(count)
    
    def observe_processing_delay(self, delay: float):
        """记录处理延迟"""
        self.processing_delay.observe(delay)
    
    def inc_retry_attempts(self, error_type: str):
        """增加重试次数"""
        self.retry_attempts.labels(error_type=error_type).inc()
    
    def inc_error_count(self, error_type: str):
        """增加错误计数"""
        self.error_count.labels(type=error_type).inc()
    
    def set_queue_size(self, size: int):
        """设置队列大小"""
        self.queue_size.set(size)
    
    def set_connection_pool_active(self, count: int):
        """设置活跃连接数"""
        self.connection_pool_active.set(count)
    
    def set_memory_usage(self, bytes_size: int):
        """设置内存使用"""
        self.memory_usage.set(bytes_size)
    
    def inc_backpressure_events(self, state: str):
        """增加背压事件计数"""
        self.backpressure_events.labels(state=state).inc()
    
    def inc_throttle_duration(self, duration: float):
        """增加限流时长"""
        self.throttle_duration.inc(duration)
    

    def inc_dedup_hits(self):
        """增加去重命中次数"""
        self.dedup_hits.inc()
    
    def set_listener_info(self, version: str, hostname: str, pid: int):
        """设置监听器信息"""
        self.listener_info.info({
            'version': version,
            'hostname': hostname,
            'pid': str(pid)
        })
    
    async def expose_endpoint(self) -> Response:
        """暴露 /metrics 端点"""
        try:
            metrics_data = generate_latest(self._registry)
            return Response(
                content=metrics_data,
                media_type=CONTENT_TYPE_LATEST,
                status_code=200
            )
        except Exception as e:
            logger.error(f"❌ Prometheus 指标暴露失败: {e}")
            return Response(
                content=f"# ERROR: {e}\n",
                media_type=CONTENT_TYPE_LATEST,
                status_code=500
            )


prometheus_metrics = PrometheusMetrics()
