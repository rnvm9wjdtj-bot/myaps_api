"""
Binlog 监听器 - 健康检查模块

提供全面的健康检查功能
"""
import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional

from .models import HealthResponse, HealthCheck, ListenerRole
from .prometheus_metrics import prometheus_metrics
from .connection_monitor import connection_pool_monitor
from globalobjects import logger


class HealthChecker:
    """健康检查器"""
    
    def __init__(
        self,
        check_timeout: int = 5,
        binlog_listener: Optional[Any] = None
    ):
        """
        初始化健康检查器
        
        Args:
            check_timeout: 单个检查超时时间（秒）
            binlog_listener: Binlog监听器实例
        """
        self.check_timeout = check_timeout
        self._binlog_listener = binlog_listener
    
    def set_listener(self, listener: Any):
        """设置监听器实例"""
        self._binlog_listener = listener
    
    async def check_mysql_connection(self) -> HealthCheck:
        """检查 MySQL 连接"""
        try:
            import pymysql
            from core.settings import MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD
            
            conn = pymysql.connect(
                host=MYAPS_DB_HOST,
                port=int(MYAPS_DB_PORT),
                user=MYAPS_DB_USER,
                password=MYAPS_DB_PASSWORD,
                connect_timeout=self.check_timeout
            )
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            
            conn.close()
            
            return HealthCheck(
                status="pass",
                message="Connected",
                details={"host": MYAPS_DB_HOST, "port": MYAPS_DB_PORT}
            )
            
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Connection failed: {e}",
                details={"error": str(e)}
            )
    
    async def check_redis_connection(self) -> HealthCheck:
        """检查 Redis 连接"""
        try:
            from apps.common.utils.redis_pool_manager import get_redis_pool_manager
            
            pool_manager = get_redis_pool_manager()
            client = pool_manager.get_client()
            
            client.ping()
            
            return HealthCheck(
                status="pass",
                message="Connected"
            )
            
        except Exception as e:
            return HealthCheck(
                status="warn",
                message=f"Redis unavailable: {e}",
                details={"note": "Fallback to single-instance mode if enabled"}
            )
    
    async def check_binlog_position(self) -> HealthCheck:
        """检查 Binlog 位置同步"""
        if not self._binlog_listener:
            return HealthCheck(
                status="warn",
                message="Listener not initialized"
            )
        
        try:
            position = getattr(self._binlog_listener, '_current_position', None)
            
            if position and position.get('log_file') and position.get('log_pos'):
                return HealthCheck(
                    status="pass",
                    message="Position synced",
                    details={
                        "log_file": position['log_file'],
                        "log_pos": position['log_pos']
                    }
                )
            else:
                return HealthCheck(
                    status="warn",
                    message="Position not available"
                )
                
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Position check failed: {e}"
            )
    
    async def check_listener_role(self) -> HealthCheck:
        """检查监听器角色"""
        if not self._binlog_listener:
            return HealthCheck(
                status="warn",
                message="Listener not initialized"
            )
        
        try:
            running = getattr(self._binlog_listener, 'running', False)
            
            if running:
                role = getattr(self._binlog_listener, '_role', ListenerRole.STANDALONE)
                return HealthCheck(
                    status="pass",
                    message=f"Running as {role.value}",
                    details={"role": role.value}
                )
            else:
                return HealthCheck(
                    status="warn",
                    message="Listener stopped"
                )
                
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Role check failed: {e}"
            )
    
    async def check_backpressure(self) -> HealthCheck:
        """检查背压状态"""
        if not self._binlog_listener:
            return HealthCheck(
                status="warn",
                message="Listener not initialized"
            )
        
        try:
            pending = self._binlog_listener.get_pending_events_count()
            threshold = getattr(self._binlog_listener, '_backpressure_threshold', 10000)
            
            usage_percent = (pending / threshold) * 100
            
            if usage_percent < 50:
                status = "pass"
            elif usage_percent < 75:
                status = "warn"
            else:
                status = "fail"
            
            return HealthCheck(
                status=status,
                message=f"Queue size: {pending}/{threshold}",
                details={
                    "queue_size": pending,
                    "threshold": threshold,
                    "usage_percent": round(usage_percent, 2)
                }
            )
            
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Backpressure check failed: {e}"
            )
    
    async def check_event_loop(self) -> HealthCheck:
        """检查事件循环"""
        if not self._binlog_listener:
            return HealthCheck(
                status="warn",
                message="Listener not initialized"
            )
        
        try:
            event_loop = getattr(self._binlog_listener, '_event_loop', None)
            
            if event_loop and event_loop.is_running():
                return HealthCheck(
                    status="pass",
                    message="Event loop running"
                )
            else:
                return HealthCheck(
                    status="warn",
                    message="Event loop not running"
                )
                
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Event loop check failed: {e}"
            )
    
    async def check_connection_pool(self) -> HealthCheck:
        """检查连接池状态"""
        try:
            stats = connection_pool_monitor.get_pool_stats()
            leaks = connection_pool_monitor.detect_leak()
            
            if leaks:
                status = "fail"
                message = f"Detected {len(leaks)} connection leaks"
            elif stats.active_count > 10:
                status = "warn"
                message = f"High active connections: {stats.active_count}"
            else:
                status = "pass"
                message = f"Active: {stats.active_count}"
            
            return HealthCheck(
                status=status,
                message=message,
                details={
                    "active_count": stats.active_count,
                    "total_checkout": stats.total_checkout,
                    "total_checkin": stats.total_checkin,
                    "leak_detected": stats.leak_detected
                }
            )
            
        except Exception as e:
            return HealthCheck(
                status="fail",
                message=f"Connection pool check failed: {e}"
            )
    
    async def check_all(self) -> HealthResponse:
        """
        执行所有健康检查
        
        Returns:
            健康检查响应
        """
        checks: Dict[str, HealthCheck] = {}
        
        check_tasks = {
            "mysql_connection": self.check_mysql_connection(),
            "redis_connection": self.check_redis_connection(),
            "binlog_position": self.check_binlog_position(),
            "listener_role": self.check_listener_role(),
            "backpressure": self.check_backpressure(),
            "event_loop": self.check_event_loop(),
            "connection_pool": self.check_connection_pool(),
        }
        
        for name, task in check_tasks.items():
            try:
                checks[name] = await asyncio.wait_for(
                    task,
                    timeout=self.check_timeout
                )
            except asyncio.TimeoutError:
                checks[name] = HealthCheck(
                    status="fail",
                    message=f"Check timeout ({self.check_timeout}s)"
                )
            except Exception as e:
                checks[name] = HealthCheck(
                    status="fail",
                    message=f"Check error: {e}"
                )
        
        statuses = [check.status for check in checks.values()]
        
        if "fail" in statuses:
            overall_status = "unhealthy"
        elif "warn" in statuses:
            overall_status = "degraded"
        else:
            overall_status = "healthy"
        
        return HealthResponse(
            status=overall_status,
            checks=checks,
            timestamp=datetime.now()
        )


health_checker = HealthChecker()
