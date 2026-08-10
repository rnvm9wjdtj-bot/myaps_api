"""
安全连接刷新器

实现安全刷新连接池，包含完整的状态管理、健康验证和失败回滚机制。
"""
import asyncio
from typing import Optional, Any
from datetime import datetime
from tortoise import Tortoise
from globalobjects.db_pool.db_pool_models import ConnectionPoolState, PoolManagerConfig
from globalobjects.db_pool.db_pool_state_manager import ConnectionPoolStateManager
from globalobjects.db_pool.db_health_checker import HealthChecker
from globalobjects.db_pool.db_cleanup_task import BackgroundCleanupTask
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
        self._cleanup_task = BackgroundCleanupTask.get_instance(self._config)
        
    async def refresh(self, fast_mode: bool = False) -> bool:
        """
        安全刷新连接池
        
        流程：标记 REFRESHING → 关闭旧池 → 重建连接 → 健康检查 → 标记 OPEN。
        任一环节失败均回滚状态为 OPEN，便于业务侧重试。
        
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
            
            # 记录进入时的状态，用于失败回滚（避免将原本 CLOSED 的连接池误回滚为 OPEN）
            original_state = self._state_manager.state
            try:
                # 1. 标记为 REFRESHING（业务侧 is_available 仍为 False，拒绝获取连接）
                await self._state_manager.mark_refreshing(reason="refresh_start")
                
                # 2. 关闭旧的（可能已损坏的）连接池
                await self._close_pool_safely()
                
                # 3. 重新创建连接对象（懒加载，实际网络连接在健康检查时建立）
                recreated = await self._recreate_connection()
                if not recreated:
                    logger.error(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        "重新创建连接对象失败"
                    )
                    return False
                
                # 4. 等待连接稳定
                wait_time = 0.5 if fast_mode else 1.0
                await asyncio.sleep(wait_time)
                
                # 5. 健康检查（force=True 绕过状态门，因为当前处于 REFRESHING）
                health_result = await self._health_checker.check(force=True)
                
                if health_result.is_healthy:
                    await self._state_manager.mark_open(reason="refresh_success")
                    
                    logger.info(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        f"连接池刷新成功，响应时间: {health_result.response_time:.3f}秒"
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
                # 刷新流程已结束；若状态仍停留在 REFRESHING（无论本次标记还是历史残留），
                # 回滚到进入时的状态，避免连接池永久停留在不可用状态（is_available 恒为 False）
                if (not self._state_manager.is_available
                        and self._state_manager.state == ConnectionPoolState.REFRESHING):
                    logger.warning(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        "刷新未成功，回滚连接池状态"
                    )
                    try:
                        if original_state == ConnectionPoolState.CLOSED:
                            await self._state_manager.mark_closed(reason="refresh_fallback")
                        else:
                            await self._state_manager.mark_open(reason="refresh_fallback")
                    except Exception as rollback_e:
                        logger.error(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            f"状态回滚失败: {str(rollback_e)}"
                        )
    
    async def _recreate_connection(self) -> bool:
        """
        重新创建数据库连接对象

        通过 Tortoise 的连接存储机制：
        1. 获取旧连接对象并完成关闭（Tortoise 契约：discard 前必须 close，否则产生悬挂连接）
        2. discard 移除旧的（已关闭的）连接对象
        3. get 触发懒加载创建新连接对象（实际网络连接在首次查询时建立）

        Returns:
            是否成功创建新连接对象
        """
        try:
            from tortoise.connection import connections

            # 1. 获取旧连接对象（若存在），按 Tortoise 契约在 discard 前完成关闭
            old_conn = connections.get(self._connection_name)
            if old_conn is not None and hasattr(old_conn, "close"):
                try:
                    # 限时关闭：Tortoise close() 内部会等待已借出连接归还，
                    # 防止业务连接未归还导致无限挂起
                    await asyncio.wait_for(old_conn.close(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        "关闭旧连接超时（存在未及时归还的连接）"
                    )
                except Exception as e:
                    logger.warning(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        f"关闭旧连接时出错: {str(e)}"
                    )

            # 2. 移除旧连接（即使已关闭也要从存储中删除）
            try:
                connections.discard(self._connection_name)
                logger.debug(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    "已从连接存储中移除旧连接"
                )
            except Exception as e:
                logger.warning(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    f"移除旧连接时出错: {str(e)}"
                )

            # 3. 触发懒加载创建新连接对象
            new_conn = connections.get(self._connection_name)
            if not new_conn:
                logger.error(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    "无法创建新连接对象"
                )
                return False
            
            logger.debug(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                "已创建新连接对象"
            )
            return True
            
        except Exception as e:
            logger.error(
                "SafeConnectionRefresher",
                f"@{self._connection_name}",
                f"重新创建连接失败: {str(e)}"
            )
            return False
    
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
                    "检测到事件循环冲突，将连接提交到后台清理任务"
                )
                try:
                    await self._cleanup_task.add_to_cleanup_queue(
                        conn,
                        self._connection_name,
                        reason="event_loop_conflict"
                    )
                except Exception as queue_error:
                    logger.error(
                        "SafeConnectionRefresher",
                        f"@{self._connection_name}",
                        f"提交到清理队列失败: {str(queue_error)}"
                    )
            else:
                logger.warning(
                    "SafeConnectionRefresher",
                    f"@{self._connection_name}",
                    f"关闭连接池时出错: {str(e)}"
                )
    
    async def _force_close_pool(self, conn: Any):
        """
        强制关闭连接池

        兼容不同数据库驱动的连接池关闭接口：
        - aiomysql/asyncmy 的 Pool.close() 为同步方法（返回 None）
        - asyncpg 的 Pool.close() 为协程（需 await）
        - 均有 wait_closed()（asyncpg 除外），用于等待空闲连接关闭

        Args:
            conn: 连接对象
        """
        if not conn:
            return
        
        try:
            if hasattr(conn, '_pool') and conn._pool:
                pool = conn._pool

                # 关闭连接池（同步/异步实现兼容）
                if hasattr(pool, 'close'):
                    try:
                        close_result = pool.close()
                        if asyncio.iscoroutine(close_result):
                            await close_result
                    except Exception as e:
                        logger.warning(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            f"关闭连接池对象时出错: {str(e)}"
                        )

                # 等待空闲连接关闭；仅限时等待，已借出的连接由业务归还时自动关闭
                if hasattr(pool, 'wait_closed'):
                    try:
                        await asyncio.wait_for(pool.wait_closed(), timeout=2.0)
                    except asyncio.TimeoutError:
                        logger.warning(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            "等待连接池关闭超时（存在未归还的连接）"
                        )
                    except Exception as e:
                        logger.warning(
                            "SafeConnectionRefresher",
                            f"@{self._connection_name}",
                            f"等待连接池关闭时出错: {str(e)}"
                        )

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
    
    def get_cleanup_queue_size(self) -> int:
        """
        获取后台清理队列大小
        
        Returns:
            清理队列大小
        """
        return self._cleanup_task.get_queue_size()