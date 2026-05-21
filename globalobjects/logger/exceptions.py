"""
统一日志系统 - 异常类

定义日志系统专用的异常类型
"""


class LoggerException(Exception):
    """日志系统基础异常"""
    pass


class LogQueueOverflowError(LoggerException):
    """
    日志队列溢出异常
    
    当异步队列已满且无法放入新日志时抛出
    """
    
    def __init__(self, message: str = "Log queue overflow, message dropped"):
        super().__init__(message)


class LogWriteError(LoggerException):
    """
    日志写入失败异常
    
    当写入文件、数据库或其他目标失败时抛出
    """
    
    def __init__(self, target: str, reason: str = ""):
        message = f"Failed to write log to {target}"
        if reason:
            message = f"{message}: {reason}"
        super().__init__(message)
        self.target = target
        self.reason = reason


class ConfigurationError(LoggerException):
    """
    配置错误异常
    
    当配置项无效或不完整时抛出
    """
    
    def __init__(self, config_name: str, value: str = "", reason: str = ""):
        message = f"Invalid configuration: {config_name}"
        if value:
            message = f"{message}={value}"
        if reason:
            message = f"{message}, {reason}"
        super().__init__(message)
        self.config_name = config_name
        self.value = value
        self.reason = reason


class HandlerInitError(LoggerException):
    """
    处理器初始化失败异常
    
    当输出处理器初始化失败时抛出
    """
    
    def __init__(self, handler_name: str, reason: str = ""):
        message = f"Failed to initialize handler: {handler_name}"
        if reason:
            message = f"{message}, {reason}"
        super().__init__(message)
        self.handler_name = handler_name
        self.reason = reason
