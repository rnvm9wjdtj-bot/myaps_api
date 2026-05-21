from fastapi import HTTPException
from tortoise import Tortoise
from globalobjects import logger as log_config
from core.settings import THIS_DB_NAME
from typing import Optional
import asyncio


async def get_db_connection_safely(db_name: Optional[str] = None, max_wait: float = 15.0):
    """
    安全获取数据库连接，包含异常处理和友好提示
    
    Args:
        db_name: 数据库连接名称，默认使用THIS_DB_NAME
        max_wait: 最大等待时间（秒），用于等待ORM初始化
    
    Returns:
        数据库连接对象
    
    Raises:
        HTTPException: 数据库连接失败时返回500错误
    """
    if db_name is None:
        db_name = THIS_DB_NAME
    
    try:
        if not Tortoise._inited:
            # 使用智能等待管理器
            from core.db_init_manager import db_init_manager
            
            log_config.info(f"⏳ 等待数据库初始化完成: {db_name}")
            result = await db_init_manager.wait_for_init(max_wait=max_wait)
            
            if not result["success"]:
                error_msg = f"数据库初始化失败({result['elapsed']:.1f}秒)"
                log_config.error(f"❌ {error_msg}: {result.get('error')}")
                raise HTTPException(
                    status_code=500,
                    detail=f"数据库服务初始化失败，请稍后重试"
                )
            
            log_config.info(f"✅ 数据库就绪，获取连接: {db_name}")
        
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
