"""
增强连接泄漏检测器

基于历史数据分析连接使用趋势，实现泄漏检测和分级告警。
"""
import uuid
from typing import Dict, List, Optional
from collections import deque
from datetime import datetime
from globalobjects.db_pool.db_pool_models import (
    UsageRecord,
    LeakDetectionResult,
    LeakSeverity,
    TrendType,
    TrendAnalysis,
    AlertMessage,
    AlertLevel,
    AlertType,
    ConnectionPoolStatus,
    PoolManagerConfig
)
from globalobjects import logger


class EnhancedConnectionLeakDetector:
    """
    增强连接泄漏检测器
    
    基于历史数据分析连接使用趋势，检测连接泄漏并生成分级告警。
    支持告警冷却机制，避免重复告警。
    """
    
    _alert_timestamps: Dict[str, float] = {}
    
    def __init__(self, config: Optional[PoolManagerConfig] = None):
        """
        初始化泄漏检测器
        
        Args:
            config: 配置对象
        """
        self._config = config or PoolManagerConfig()
        self._usage_history: Dict[str, deque] = {}
    
    def _should_log_alert(self, connection_name: str) -> bool:
        """
        检查是否应该记录告警（基于冷却机制）
        
        Args:
            connection_name: 连接名称
            
        Returns:
            True 如果应该记录，False 如果在冷却期内
        """
        from globalobjects.db_pool.db_pool_models import check_cooldown
        return check_cooldown(
            self._alert_timestamps,
            connection_name,
            self._config.alert_cooldown
        )
    
    @classmethod
    def cleanup_alert_timestamps(cls, connection_name: str = None):
        """
        清理告警时间戳记录
        
        Args:
            connection_name: 连接名称（None则清空所有）
        """
        if connection_name:
            cls._alert_timestamps.pop(connection_name, None)
        else:
            cls._alert_timestamps.clear()
        
    def record_usage(
        self,
        connection_name: str,
        pool_status: ConnectionPoolStatus,
        is_healthy: bool = True
    ):
        """
        记录连接使用情况
        
        Args:
            connection_name: 连接名称
            pool_status: 连接池状态
            is_healthy: 是否健康
        """
        if connection_name not in self._usage_history:
            self._usage_history[connection_name] = deque(
                maxlen=self._config.leak_history_size
            )
        
        record = UsageRecord(
            connection_name=connection_name,
            usage_rate=pool_status.usage_rate,
            used_connections=pool_status.used_connections,
            total_connections=pool_status.total_connections,
            is_healthy=is_healthy,
            pool_available=pool_status.pool_available
        )
        
        self._usage_history[connection_name].append(record)
        
        logger.debug(
            "LeakDetector",
            f"@{connection_name}",
            f"记录使用情况: 使用率={pool_status.usage_rate:.1f}%, 健康={is_healthy}, 可用={pool_status.pool_available}"
        )
    
    def detect_leak(self, connection_name: str) -> LeakDetectionResult:
        """
        检测连接泄漏
        
        Args:
            connection_name: 连接名称
            
        Returns:
            泄漏检测结果
        """
        if connection_name not in self._usage_history:
            return LeakDetectionResult(
                leak_detected=False,
                severity=LeakSeverity.NORMAL,
                details={"message": "无历史数据"}
            )
        
        history = list(self._usage_history[connection_name])
        
        if not history:
            return LeakDetectionResult(
                leak_detected=False,
                severity=LeakSeverity.NORMAL,
                details={"message": "历史数据为空"}
            )
        
        pool_unavailable_count = sum(1 for r in history if not r.pool_available)
        pool_unavailable_rate = pool_unavailable_count / len(history) if history else 0.0
        
        if pool_unavailable_rate > 0.5:
            return LeakDetectionResult(
                leak_detected=False,
                severity=LeakSeverity.NORMAL,
                details={"message": "连接池不可用，跳过泄漏检测"}
            )
        
        available_history = [r for r in history if r.pool_available]
        
        if not available_history:
            return LeakDetectionResult(
                leak_detected=False,
                severity=LeakSeverity.NORMAL,
                details={"message": "无可用连接池历史数据"}
            )
        
        usage_rates = [r.usage_rate for r in available_history]
        avg_usage_rate = sum(usage_rates) / len(usage_rates)
        max_usage_rate = max(usage_rates)
        current_usage_rate = usage_rates[-1] if usage_rates else 0.0
        
        health_failure_count = sum(1 for r in available_history if not r.is_healthy)
        health_check_failure_rate = health_failure_count / len(available_history) if available_history else 0.0
        
        trend = self._analyze_trend(connection_name)
        
        severity = self._determine_severity(
            avg_usage_rate,
            max_usage_rate,
            health_check_failure_rate,
            trend
        )
        
        leak_detected = severity != LeakSeverity.NORMAL
        
        result = LeakDetectionResult(
            leak_detected=leak_detected,
            severity=severity,
            usage_rate=current_usage_rate,
            avg_usage_rate=avg_usage_rate,
            max_usage_rate=max_usage_rate,
            health_check_failure_rate=health_check_failure_rate,
            trend=trend,
            details={
                "history_size": len(history),
                "available_history_size": len(available_history),
                "current_usage": current_usage_rate,
                "avg_usage": avg_usage_rate,
                "max_usage": max_usage_rate,
                "health_failure_rate": health_check_failure_rate,
                "pool_unavailable_rate": pool_unavailable_rate
            }
        )
        
        if leak_detected:
            if self._should_log_alert(connection_name):
                if health_check_failure_rate > 0.5:
                    logger.error(
                        "LeakDetector",
                        f"@{connection_name}",
                        f"健康检查持续失败: 失败率={health_check_failure_rate:.1%}, 请检查数据库连接"
                    )
                elif current_usage_rate >= 80:
                    logger.warning(
                        "LeakDetector",
                        f"@{connection_name}",
                        f"检测到连接泄漏: 严重程度={severity.value}, 使用率={current_usage_rate:.1f}%, 平均={avg_usage_rate:.1f}%"
                    )
                else:
                    logger.warning(
                        "LeakDetector",
                        f"@{connection_name}",
                        f"连接池异常: 严重程度={severity.value}, 使用率={current_usage_rate:.1f}%"
                    )
            else:
                logger.debug(
                    "LeakDetector",
                    f"@{connection_name}",
                    f"检测到异常但在冷却期内: 严重程度={severity.value}, 使用率={current_usage_rate:.1f}%"
                )
        
        return result
    
    def _analyze_trend(self, connection_name: str) -> TrendAnalysis:
        """
        分析使用率趋势（线性回归）
        
        Args:
            connection_name: 连接名称
            
        Returns:
            趋势分析结果
        """
        if connection_name not in self._usage_history:
            return TrendAnalysis(
                trend_type=TrendType.STABLE,
                slope=0.0,
                confidence=0.0,
                data_points=0
            )
        
        history = list(self._usage_history[connection_name])
        
        if len(history) < 2:
            return TrendAnalysis(
                trend_type=TrendType.STABLE,
                slope=0.0,
                confidence=0.0,
                data_points=len(history)
            )
        
        n = len(history)
        x = list(range(n))
        y = [r.usage_rate for r in history]
        
        x_mean = sum(x) / n
        y_mean = sum(y) / n
        
        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        slope = numerator / denominator if denominator != 0 else 0.0
        
        variance = sum((y[i] - y_mean) ** 2 for i in range(n)) / n
        confidence = min(1.0, abs(slope) * 10 / (variance + 1))
        
        if abs(slope) < 0.1:
            trend_type = TrendType.STABLE
        elif slope > 0:
            trend_type = TrendType.INCREASING
        else:
            trend_type = TrendType.DECREASING
        
        return TrendAnalysis(
            trend_type=trend_type,
            slope=slope,
            confidence=confidence,
            data_points=n
        )
    
    def _determine_severity(
        self,
        avg_usage_rate: float,
        max_usage_rate: float,
        health_check_failure_rate: float,
        trend: TrendAnalysis
    ) -> LeakSeverity:
        """
        判断泄漏严重程度
        
        Args:
            avg_usage_rate: 平均使用率
            max_usage_rate: 最高使用率
            health_check_failure_rate: 健康检查失败率
            trend: 趋势分析
            
        Returns:
            严重程度
        """
        if max_usage_rate >= self._config.leak_emergency_threshold:
            return LeakSeverity.EMERGENCY
        
        if health_check_failure_rate > 0.5:
            return LeakSeverity.EMERGENCY
        
        if avg_usage_rate >= self._config.leak_critical_threshold:
            return LeakSeverity.CRITICAL
        
        if trend.trend_type == TrendType.INCREASING and trend.confidence > 0.5:
            if avg_usage_rate >= self._config.leak_warning_threshold:
                return LeakSeverity.CRITICAL
        
        if avg_usage_rate >= self._config.leak_warning_threshold:
            return LeakSeverity.WARNING
        
        return LeakSeverity.NORMAL
    
    def generate_alert(
        self,
        connection_name: str,
        leak_result: LeakDetectionResult
    ) -> Optional[AlertMessage]:
        """
        生成告警消息
        
        Args:
            connection_name: 连接名称
            leak_result: 泄漏检测结果
            
        Returns:
            告警消息（如果检测到泄漏）
        """
        if not leak_result.leak_detected:
            return None
        
        alert_level_map = {
            LeakSeverity.WARNING: AlertLevel.WARNING,
            LeakSeverity.CRITICAL: AlertLevel.CRITICAL,
            LeakSeverity.EMERGENCY: AlertLevel.EMERGENCY
        }
        
        alert_level = alert_level_map.get(leak_result.severity, AlertLevel.WARNING)
        
        message = f"检测到连接泄漏: {connection_name}, "
        message += f"使用率={leak_result.usage_rate:.1f}%, "
        message += f"平均使用率={leak_result.avg_usage_rate:.1f}%, "
        message += f"严重程度={leak_result.severity.value}"
        
        suggestion = self._generate_suggestion(leak_result)
        
        alert = AlertMessage(
            alert_id=str(uuid.uuid4()),
            alert_type=AlertType.LEAK_DETECTED,
            alert_level=alert_level,
            connection_name=connection_name,
            message=message,
            details=leak_result.details,
            suggestion=suggestion
        )
        
        logger.warning(
            "LeakDetector",
            f"@{connection_name}",
            f"生成告警: {message}"
        )
        
        return alert
    
    def _generate_suggestion(self, leak_result: LeakDetectionResult) -> str:
        """
        生成处理建议
        
        Args:
            leak_result: 泄漏检测结果
            
        Returns:
            处理建议
        """
        suggestions = []
        
        if leak_result.usage_rate >= 90:
            suggestions.append("立即检查应用是否存在连接未释放的情况")
            suggestions.append("考虑增加连接池最大连接数配置")
        
        if leak_result.health_check_failure_rate > 0.3:
            suggestions.append("检查数据库服务是否正常运行")
            suggestions.append("检查网络连接是否稳定")
        
        if leak_result.trend and leak_result.trend.trend_type == TrendType.INCREASING:
            suggestions.append("连接使用率呈上升趋势，建议持续监控")
            suggestions.append("检查是否存在慢查询或长事务")
        
        if not suggestions:
            suggestions.append("建议持续监控连接池使用情况")
        
        return "; ".join(suggestions)
    
    def get_history_size(self, connection_name: str) -> int:
        """
        获取历史数据大小
        
        Args:
            connection_name: 连接名称
            
        Returns:
            历史数据大小
        """
        if connection_name in self._usage_history:
            return len(self._usage_history[connection_name])
        return 0
    
    def clear_history(self, connection_name: Optional[str] = None):
        """
        清空历史数据
        
        Args:
            connection_name: 连接名称（None则清空所有）
        """
        if connection_name:
            self._usage_history.pop(connection_name, None)
            logger.debug(
                "LeakDetector",
                f"@{connection_name}",
                "历史数据已清空"
            )
        else:
            self._usage_history.clear()
            logger.debug("LeakDetector", "所有历史数据已清空")