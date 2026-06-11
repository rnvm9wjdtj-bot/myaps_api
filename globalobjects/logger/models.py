"""
统一日志系统 - 数据模型

基于Pydantic定义日志记录和配置的数据结构
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import logging


class LogRecord(BaseModel):
    """
    日志记录数据模型
    
    表示一条完整的日志记录，包含时间戳、级别、消息和调用位置信息
    """
    
    timestamp: datetime = Field(default_factory=datetime.now)
    level: int = Field(default=logging.INFO)
    level_name: str = Field(default="INFO")
    message: str = Field(default="", max_length=65535)
    
    module: Optional[str] = Field(default=None, max_length=255)
    function: Optional[str] = Field(default=None, max_length=255)
    line: Optional[int] = Field(default=None, ge=0)
    
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    stack_trace: Optional[str] = Field(default=None, max_length=65535)
    
    process_id: Optional[int] = None
    thread_id: Optional[int] = None
    thread_name: Optional[str] = None
    
    extra: Optional[Dict[str, Any]] = None
    
    @field_validator('level_name', mode='before')
    @classmethod
    def validate_level_name(cls, v: str) -> str:
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            return 'INFO'
        return v.upper()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'level_name': self.level_name,
            'message': self.message,
            'module': self.module,
            'function': self.function,
            'line': self.line,
            'exception_type': self.exception_type,
            'exception_message': self.exception_message,
            'stack_trace': self.stack_trace,
            'process_id': self.process_id,
            'thread_id': self.thread_id,
            'thread_name': self.thread_name,
            'extra': self.extra
        }


class LoggerConfig(BaseModel):
    """
    日志配置数据模型
    
    通过环境变量或代码配置日志系统行为
    """
    
    log_level: str = Field(default="INFO")
    
    log_dir: str = Field(default="logs")
    log_file_prefix: str = Field(default="app")
    max_file_size: int = Field(default=100 * 1024 * 1024, gt=0)
    retention_days: int = Field(default=7, gt=0)
    
    to_console: bool = Field(default=True)
    to_file: bool = Field(default=True)
    to_database: bool = Field(default=True)
    to_websocket: bool = Field(default=True)
    
    async_write: bool = Field(default=True)
    queue_size: int = Field(default=10000, gt=0)
    batch_size: int = Field(default=100, gt=0)
    flush_interval: float = Field(default=1.0, gt=0)
    
    stack_trace: bool = Field(default=False)
    
    sensitive_fields: list = Field(default_factory=lambda: [
        'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token',
        'secret', 'secret_key', 'api_key', 'key', 'credential', 'auth'
    ])
    
    @field_validator('log_level', mode='before')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if str(v).upper() not in valid_levels:
            return 'INFO'
        return str(v).upper()
    
    @classmethod
    def from_env(cls) -> 'LoggerConfig':
        """
        从环境变量加载配置
        
        Returns:
            LoggerConfig: 配置实例
        """
        import os
        
        def get_bool(key: str, default: bool = True) -> bool:
            val = os.getenv(key)
            if val is None:
                return default
            return val.lower() in ('true', '1', 'yes')
        
        def get_int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, default))
            except ValueError:
                return default
        
        def get_float(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, default))
            except ValueError:
                return default
        
        return cls(
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            log_dir=os.getenv('LOG_DIR', 'logs'),
            log_file_prefix=os.getenv('LOG_FILE_PREFIX', 'app'),
            max_file_size=get_int('MAX_FILE_SIZE', 100) * 1024 * 1024,
            retention_days=get_int('RETENTION_DAYS', 7),
            to_console=get_bool('TO_CONSOLE', True),
            to_file=get_bool('TO_FILE', True),
            to_database=get_bool('TO_DATABASE', True),
            to_websocket=get_bool('TO_WEBSOCKET', True),
            async_write=get_bool('ASYNC_WRITE', True),
            queue_size=get_int('LOG_QUEUE_SIZE', 10000),
            batch_size=get_int('LOG_BATCH_SIZE', 100),
            flush_interval=get_float('LOG_FLUSH_INTERVAL', 1.0),
            stack_trace=get_bool('LOG_STACK_TRACE', True)
        )
    
    def get_level_int(self) -> int:
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        return level_map.get(self.log_level, logging.INFO)
