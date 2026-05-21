"""
Binlog 监听器 - 背压控制管理器

提供主动背压检测和限流机制
"""
import time
import threading
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from .models import PressureState
from .prometheus_metrics import prometheus_metrics
from globalobjects import logger


@dataclass
class QueueMetrics:
    """队列指标"""
    current_size: int = 0
    avg_delay: float = 0.0
    max_delay: float = 0.0
    throttle_count: int = 0
    throttle_duration_total: float = 0.0


class BackpressureController:
    """背压控制管理器"""
    
    def __init__(
        self,
        warning_threshold: int = 1000,
        limit_threshold: int = 5000,
        pause_duration: int = 5,
        check_interval: int = 10,
        delay_threshold: float = 10.0,
        on_throttle: Optional[Callable[[PressureState], None]] = None
    ):
        """
        初始化背压控制管理器
        
        Args:
            warning_threshold: 告警阈值（队列大小）
            limit_threshold: 限流阈值（队列大小）
            pause_duration: 暂停时长（秒）
            check_interval: 检查间隔（事件数）
            delay_threshold: 延迟阈值（秒）
            on_throttle: 限流回调函数
        """
        self.warning_threshold = warning_threshold
        self.limit_threshold = limit_threshold
        self.pause_duration = pause_duration
        self.check_interval = check_interval
        self.delay_threshold = delay_threshold
        self._on_throttle = on_throttle
        
        self._lock = threading.RLock()
        self._last_check_time = 0.0
        self._throttle_count = 0
        self._total_throttle_duration = 0.0
        self._processing_delays: list = []
        self._current_state = PressureState.NORMAL
        self._is_paused = False
        self._pause_until = 0.0
    
    def check_pressure(
        self,
        queue_size: int,
        processing_delay: Optional[float] = None
    ) -> PressureState:
        """
        检测背压状态
        
        Args:
            queue_size: 当前队列大小
            processing_delay: 处理延迟（秒）
        
        Returns:
            背压状态
        """
        with self._lock:
            if processing_delay is not None:
                self._processing_delays.append(processing_delay)
                if len(self._processing_delays) > 100:
                    self._processing_delays.pop(0)
            
            state = PressureState.NORMAL
            
            if queue_size >= self.limit_threshold:
                state = PressureState.CRITICAL
            elif queue_size >= self.warning_threshold:
                state = PressureState.WARNING
            
            if processing_delay and processing_delay >= self.delay_threshold:
                state = PressureState.CRITICAL
            
            self._current_state = state
            self._last_check_time = time.time()
            
            prometheus_metrics.set_queue_size(queue_size)
            prometheus_metrics.inc_backpressure_events(state.value)
            
            return state
    
    def should_pause(self) -> bool:
        """
        判断是否应暂停拉取
        
        Returns:
            是否应暂停
        """
        with self._lock:
            if time.time() < self._pause_until:
                return True
            
            return self._current_state == PressureState.CRITICAL
    
    def apply_throttling(self, state: Optional[PressureState] = None) -> bool:
        """
        应用限流策略
        
        Args:
            state: 背压状态（不传则使用当前状态）
        
        Returns:
            是否触发了限流
        """
        with self._lock:
            if state is None:
                state = self._current_state
            
            if state == PressureState.NORMAL:
                logger.debug("✅ 背压状态正常，继续拉取事件")
                return False
            
            elif state == PressureState.WARNING:
                queue_size = prometheus_metrics.queue_size._value.get() if hasattr(prometheus_metrics.queue_size, '_value') else 0
                logger.warning(
                    f"⚠️ 背压告警: 队列大小超过阈值 "
                    f"(current={queue_size}, warning_threshold={self.warning_threshold})"
                )
                return False
            
            elif state == PressureState.CRITICAL:
                self._throttle_count += 1
                self._pause_until = time.time() + self.pause_duration
                self._total_throttle_duration += self.pause_duration
                
                prometheus_metrics.inc_throttle_duration(self.pause_duration)
                
                queue_size = prometheus_metrics.queue_size._value.get() if hasattr(prometheus_metrics.queue_size, '_value') else 0
                logger.error(
                    f"🚨 背压严重: 触发限流，暂停拉取 {self.pause_duration}秒 "
                    f"(current={queue_size}, limit_threshold={self.limit_threshold}, "
                    f"throttle_count={self._throttle_count})"
                )
                
                if self._on_throttle:
                    self._on_throttle(state)
                
                return True
            
            return False
    
    def get_queue_metrics(self) -> QueueMetrics:
        """
        获取队列指标
        
        Returns:
            队列指标对象
        """
        with self._lock:
            avg_delay = 0.0
            max_delay = 0.0
            
            if self._processing_delays:
                avg_delay = sum(self._processing_delays) / len(self._processing_delays)
                max_delay = max(self._processing_delays)
            
            queue_size = prometheus_metrics.queue_size._value.get() if hasattr(prometheus_metrics.queue_size, '_value') else 0
            
            return QueueMetrics(
                current_size=int(queue_size),
                avg_delay=avg_delay,
                max_delay=max_delay,
                throttle_count=self._throttle_count,
                throttle_duration_total=self._total_throttle_duration
            )
    
    def get_state(self) -> PressureState:
        """获取当前背压状态"""
        with self._lock:
            return self._current_state
    
    def reset(self):
        """重置背压状态"""
        with self._lock:
            self._current_state = PressureState.NORMAL
            self._is_paused = False
            self._pause_until = 0.0
            self._processing_delays.clear()
            logger.info("✅ 背压状态已重置")
    
    def update_thresholds(
        self,
        warning_threshold: Optional[int] = None,
        limit_threshold: Optional[int] = None
    ):
        """
        更新阈值配置
        
        Args:
            warning_threshold: 新的告警阈值
            limit_threshold: 新的限流阈值
        """
        with self._lock:
            if warning_threshold is not None:
                self.warning_threshold = warning_threshold
                logger.info(f"✅ 背压告警阈值已更新: {warning_threshold}")
            
            if limit_threshold is not None:
                if limit_threshold <= self.warning_threshold:
                    logger.warning(f"⚠️ 限流阈值必须大于告警阈值，更新失败")
                    return
                self.limit_threshold = limit_threshold
                logger.info(f"✅ 背压限流阈值已更新: {limit_threshold}")


backpressure_controller = BackpressureController()
