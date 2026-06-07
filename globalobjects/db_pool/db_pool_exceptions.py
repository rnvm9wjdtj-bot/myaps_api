"""
数据库连接池管理异常类

定义连接池管理所需的所有异常类。
"""
from typing import Optional, Dict, Any


class DbPoolError(Exception):
    """数据库连接池异常基类"""
    
    def __init__(
        self,
        message: str,
        connection_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.connection_name = connection_name
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.connection_name:
            return f"[{self.connection_name}] {self.message}"
        return self.message
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "connection_name": self.connection_name,
            "details": self.details
        }


class ConnectionPoolUnavailableError(DbPoolError):
    """连接池不可用异常"""
    
    def __init__(
        self,
        connection_name: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"连接池不可用: {connection_name}"
        if reason:
            message += f", 原因: {reason}"
        super().__init__(message, connection_name, details)
        self.reason = reason


class ConnectionPoolStateError(DbPoolError):
    """连接池状态异常"""
    
    def __init__(
        self,
        connection_name: str,
        expected_state: str,
        actual_state: str,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"连接池状态错误: 期望 {expected_state}, 实际 {actual_state}"
        super().__init__(message, connection_name, details)
        self.expected_state = expected_state
        self.actual_state = actual_state


class HealthCheckError(DbPoolError):
    """健康检查异常"""
    
    def __init__(
        self,
        connection_name: str,
        error_message: Optional[str] = None,
        timeout: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"健康检查失败: {connection_name}"
        if error_message:
            message += f", 错误: {error_message}"
        if timeout:
            message += f", 超时: {timeout}秒"
        super().__init__(message, connection_name, details)
        self.error_message = error_message
        self.timeout = timeout


class ConnectionRefreshError(DbPoolError):
    """连接刷新异常"""
    
    def __init__(
        self,
        connection_name: str,
        error_message: Optional[str] = None,
        phase: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"连接刷新失败: {connection_name}"
        if phase:
            message += f", 阶段: {phase}"
        if error_message:
            message += f", 错误: {error_message}"
        super().__init__(message, connection_name, details)
        self.error_message = error_message
        self.phase = phase


class CleanupQueueFullError(DbPoolError):
    """清理队列满异常"""
    
    def __init__(
        self,
        connection_name: str,
        queue_size: int,
        max_size: int,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"清理队列已满: {connection_name}, 当前大小: {queue_size}, 最大大小: {max_size}"
        super().__init__(message, connection_name, details)
        self.queue_size = queue_size
        self.max_size = max_size


class ForceCloseError(DbPoolError):
    """强制关闭连接异常"""
    
    def __init__(
        self,
        connection_name: str,
        error_message: Optional[str] = None,
        retry_count: int = 0,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"强制关闭连接失败: {connection_name}"
        if error_message:
            message += f", 错误: {error_message}"
        if retry_count > 0:
            message += f", 重试次数: {retry_count}"
        super().__init__(message, connection_name, details)
        self.error_message = error_message
        self.retry_count = retry_count


class StateTransitionError(DbPoolError):
    """状态转换异常"""
    
    def __init__(
        self,
        connection_name: str,
        from_state: str,
        to_state: str,
        reason: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"状态转换失败: {connection_name}, {from_state} -> {to_state}"
        if reason:
            message += f", 原因: {reason}"
        super().__init__(message, connection_name, details)
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason