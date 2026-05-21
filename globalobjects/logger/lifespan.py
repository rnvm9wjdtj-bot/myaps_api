"""
统一日志系统 - FastAPI生命周期集成
"""

import sys
from typing import Any, Callable, Optional

from .core import SmartLogger
from .factory import get_logger, get_default_logger, get_config, clear_cache
from .models import LoggerConfig


async def initialize_logging(config: Optional[LoggerConfig] = None) -> SmartLogger:
    """
    初始化日志系统
    
    Args:
        config: 日志配置
        
    Returns:
        SmartLogger实例
    """
    if config:
        from . import factory
        factory.set_config(config)
    
    logger = get_default_logger()
    
    await logger.initialize()
    
    logger.info("✅ 统一日志系统初始化完成")
    
    return logger


async def shutdown_logging() -> None:
    """关闭日志系统"""
    logger = get_default_logger()
    
    logger.info("🛑 正在关闭日志系统...")
    
    await logger.shutdown()
    
    clear_cache()


def set_db_initialized(initialized: bool = True) -> None:
    """
    设置数据库初始化状态
    
    Args:
        initialized: 是否已初始化
    """
    logger = get_default_logger()
    logger.set_db_initialized(initialized)


def get_logger_lifespan():
    """
    获取日志系统的FastAPI生命周期上下文管理器
    
    用法:
        app = FastAPI(lifespan=get_logger_lifespan())
    """
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def lifespan(app: Any):
        await initialize_logging()
        try:
            yield
        finally:
            await shutdown_logging()
    
    return lifespan


def create_logging_context(app: Any) -> Any:
    """
    创建日志上下文（用于FastAPI startup/shutdown事件）
    
    用法:
        app = FastAPI()
        logging_ctx = create_logging_context(app)
        
        @app.on_event("startup")
        async def startup():
            await initialize_logging()
        
        @app.on_event("shutdown")
        async def shutdown():
            await shutdown_logging()
    """
    return {
        'initialize': initialize_logging,
        'shutdown': shutdown_logging,
        'set_db_initialized': set_db_initialized
    }


def setup_logging_events(app: Any) -> None:
    """
    为FastAPI应用设置日志事件
    
    Args:
        app: FastAPI应用实例
    """
    @app.on_event("startup")
    async def _startup_logging():
        await initialize_logging()
    
    @app.on_event("shutdown")
    async def _shutdown_logging():
        await shutdown_logging()
