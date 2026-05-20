from fastapi import HTTPException
from tortoise import Tortoise
from globalobjects import logger as log_config
from core.settings import THIS_DB_NAME
from typing import Optional


async def get_db_connection_safely(db_name: Optional[str] = None):
    """
    安全获取数据库连接，包含异常处理和友好提示
    
    Args:
        db_name: 数据库连接名称，默认使用THIS_DB_NAME
    
    Returns:
        数据库连接对象
    
    Raises:
        HTTPException: 数据库连接失败时返回500错误
    """
    if db_name is None:
        db_name = THIS_DB_NAME
    
    try:
        if not Tortoise._inited:
            log_config.error(f"❌ Tortoise ORM 未初始化，无法获取连接: {db_name}")
            raise HTTPException(
                status_code=500,
                detail="数据库服务初始化失败，请检查服务配置或稍后重试"
            )
        
        conn = Tortoise.get_connection(db_name)
        return conn
        
    except KeyError:
        log_config.error(f"❌ 数据库连接不存在: {db_name}")
        raise HTTPException(
            status_code=500,
            detail="数据库连接配置错误，请联系管理员"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        log_config.error(f"❌ 获取数据库连接异常: {db_name} - {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail="数据库连接失败，请检查服务配置或稍后重试"
        )
