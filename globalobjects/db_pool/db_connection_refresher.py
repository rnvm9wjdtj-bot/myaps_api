"""
安全连接刷新器

实现安全刷新连接池，包含完整的状态管理、健康验证和失败回滚机制。
"""
import asyncio
from typing import Optional, List, Any
from datetime import datetime
from tortoise import Tortoise
from globalobjects.db_pool.db_pool_models import PoolManagerConfig
from globalobjects.db_pool.db_pool_state_manager import ConnectionPoolStateManager
from globalobjects.db_pool.db_health_checker import HealthChecker
from globalobjects.db_pool.db_pool_exceptions import (
    ConnectionRefreshError,
    ForceCloseError
)
from globalobjects import logger


class SafeConnectionRefresher:
    """
    安全连接刷新器
    
    负责安全刷新连接池，确保刷新过程中的状态一致性。
    刷新前标记状态，刷新后健康验证，失败时回滚。
    """
    
    def __init__(
        self,
        connection_name: str,
        state_manager: ConnectionPoolStateManager,
        health_checker: HealthChecker,
        config: Optional[PoolManagerConfig] = None
    ):
        """
        初始化安全连接刷新器
        
        Args:
            connection_name: 连接名称
            state_manager: 状态管理器
            health_checker: 健康检查器
            config: 配置对象
        """
        self._connection_name = connection_name
        self._state_manager = state_manager
        self._health_checker = health_checker
        self._config = config or PoolManagerConfig()
        self._refresh_lock = asyncio.Lock()
        self._pending_cleanup: List[Any] = []
        
    async def refresh(self, fast_mode: bool = False) -> bool:
        """
        安全刷新连接池
        
        Args:
            fast_mode: 是否使用快速模式（较短等待时间）
            
        Returns:
            是否刷新成功
        """
        async with self._refresh_lock:
            logger.info(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                f"开始刷新连接池，快速模式: {fast_mode}"
            )
            
            was_closed = False
            try:
                result = await self._state_manager.mark_closed(reason="refresh_start")
                was_closed = result is not False
                
                await self._close_pool_safely()
                
                wait_time = 0.5 if fast_mode else 1.0
                await asyncio.sleep(wait_time)
                
                health_result = await self._health_checker.check()
                
                if health_result.is_healthy:
                    await self._state_manager.mark_open(reason="refresh_success")
                    
                    logger.info(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        "连接池刷新成功"
                    )
                    return True
                else:
                    logger.error(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        f"刷新后健康检查失败: {health_result.error_message}"
                    )
                    return False
                    
            except Exception as e:
                logger.error(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    f"连接池刷新失败: {str(e)}"
                )
                return False
            finally:
                if was_closed and not self._state_manager.is_available:
                    logger.warning(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        "刷新失败，回滚状态为OPEN"
                    )
                    try:
                        await self._state_manager.mark_open(reason="refresh_fallback")
                    except Exception as rollback_e:
                        logger.error(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            f"状态回滚失败: {str(rollback_e)}"
                        )
    
    async def _close_pool_safely(self):
        """
        安全关闭连接池
        
        处理各种异常情况，包括事件循环冲突。
        """
        try:
            conn = Tortoise.get_connection(self._connection_name)
            
            if not conn:
                logger.debug(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    "连接不存在，跳过关闭"
                )
                return
            
            await self._force_close_pool(conn)
            
        except Exception as e:
            if "bound to a different event loop" in str(e):
                logger.warning(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    "检测到事件循环冲突，将连接加入待清理队列"
                )
                self._pending_cleanup.append({
                    "connection": conn,
                    "reason": "event_loop_conflict",
                    "time": datetime.now()
                })
            else:
                logger.warning(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    f"关闭连接池时出错: {str(e)}"
                )
    
    async def _force_close_pool(self, conn: Any):
        """
        强制关闭连接池
        
        Args:
            conn: 连接对象
        """
        if not conn:
            return
        
        try:
            if hasattr(conn, '_pool') and conn._pool:
                pool = conn._pool
                
                if hasattr(pool, 'close'):
                    try:
                        await pool.close()
                    except Exception as e:
                        logger.warning(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            f"关闭连接池对象时出错: {str(e)}"
                        )
                
                if hasattr(pool, '_connections'):
                    pool._connections.clear()
                if hasattr(pool, '_used'):
                    pool._used.clear()
                if hasattr(pool, '_idle'):
                    pool._idle.clear()
            
            await self._mark_connection_invalid(conn)
            
            logger.debug(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                "连接池已强制关闭"
            )
            
        except Exception as e:
            logger.warning(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                f"强制关闭连接池时出错: {str(e)}"
            )
    
    async def _mark_connection_invalid(self, conn: Any):
        """
        标记连接为无效状态
        
        Args:
            conn: 连接对象
        """
        if not conn:
            return
        
        try:
            if hasattr(conn, '_valid'):
                conn._valid = False
            if hasattr(conn, '_closed'):
                conn._closed = True
            
            if hasattr(conn, '_pool') and conn._pool:
                pool = conn._pool
                if hasattr(pool, '_closed'):
                    pool._closed = True
            
            logger.debug(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                "连接已标记为无效"
            )
            
        except Exception as e:
            logger.warning(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                f"标记连接状态时出错: {str(e)}"
            )
    
    def get_pending_cleanup_count(self) -> int:
        """
        获取待清理连接数量
        
        Returns:
            待清理连接数量
        """
        return len(self._pending_cleanup)
    
    def get_pending_cleanup_items(self) -> List[dict]:
        """
        获取待清理连接列表
        
        Returns:
            待清理连接列表
        """
        return self._pending_cleanup.copy()
    
    def clear_pending_cleanup(self):
        """
        清空待清理队列
        """
        self._pending_cleanup.clear()
        logger.debug(
            "SafeConnectionRefresher",
            f"@{self._connection_name}",
            "待清理队列已清空"
        )