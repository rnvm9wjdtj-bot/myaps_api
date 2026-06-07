"""
后台清理任务

定期清理可能泄漏的连接，处理待清理队列中的连接对象。
"""
import asyncio
from typing import Optional, List, Any
from datetime import datetime
from globalobjects.db_pool.db_pool_models import (
    PendingCleanupItem,
    PoolManagerConfig
)
from globalobjects.db_pool.db_pool_exceptions import (
    CleanupQueueFullError,
    ForceCloseError
)
from globalobjects import logger


class BackgroundCleanupTask:
    """
    后台清理任务
    
    定期清理可能泄漏的连接，处理待清理队列中的连接对象。
    """
    
    _instance: Optional['BackgroundCleanupTask'] = None
    
    @classmethod
    def get_instance(cls, config: Optional[PoolManagerConfig] = None) -> 'BackgroundCleanupTask':
        """
        获取单例实例
        
        Args:
            config: 配置对象
            
        Returns:
            后台清理任务实例
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance
    
    def __init__(self, config: Optional[PoolManagerConfig] = None):
        """
        初始化后台清理任务
        
        Args:
            config: 配置对象
        """
        self._config = config or PoolManagerConfig()
        self._pending_queue: asyncio.Queue = asyncio.Queue(
            maxsize=self._config.max_cleanup_queue_size
        )
        self._is_running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_count = 0
        self._last_cleanup_time: Optional[datetime] = None
        
    async def start(self):
        """
        启动后台清理任务
        """
        if self._is_running:
            logger.warning(
                "BackgroundCleanup",
                "后台清理任务已在运行"
            )
            return
        
        self._is_running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info(
            "BackgroundCleanup",
            f"后台清理任务已启动，间隔: {self._config.cleanup_interval}秒"
        )
    
    async def stop(self):
        """
        停止后台清理任务
        """
        if not self._is_running:
            return
        
        self._is_running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        
        logger.info("BackgroundCleanup", "后台清理任务已停止")
    
    async def add_to_cleanup_queue(
        self,
        connection: Any,
        connection_name: str,
        reason: str = "unknown"
    ) -> bool:
        """
        添加连接到清理队列
        
        Args:
            connection: 连接对象
            connection_name: 连接名称
            reason: 清理原因
            
        Returns:
            是否成功添加
            
        Raises:
            CleanupQueueFullError: 队列已满
        """
        try:
            item = PendingCleanupItem(
                connection=connection,
                connection_name=connection_name,
                reason=reason
            )
            
            self._pending_queue.put_nowait(item)
            
            logger.debug(
                "BackgroundCleanup",
                f"@{connection_name}",
                f"添加到清理队列: {reason}"
            )
            return True
            
        except asyncio.QueueFull:
            logger.error(
                "BackgroundCleanup",
                f"@{connection_name}",
                f"清理队列已满，无法添加: {reason}"
            )
            raise CleanupQueueFullError(
                connection_name,
                self._pending_queue.qsize(),
                self._config.max_cleanup_queue_size
            )
    
    async def _cleanup_loop(self):
        """
        清理循环
        """
        while self._is_running:
            try:
                await asyncio.sleep(self._config.cleanup_interval)
                
                await self._process_cleanup()
                
            except asyncio.CancelledError:
                logger.info("BackgroundCleanup", "清理循环被取消")
                break
            except Exception as e:
                logger.error(
                    "BackgroundCleanup",
                    f"清理循环异常: {str(e)}"
                )
                await asyncio.sleep(60)
    
    async def _process_cleanup(self):
        """
        处理待清理队列
        """
        if self._pending_queue.empty():
            return
        
        logger.info(
            "BackgroundCleanup",
            f"开始处理清理队列，队列大小: {self._pending_queue.qsize()}"
        )
        
        start_time = datetime.now()
        processed_count = 0
        failed_count = 0
        
        try:
            async with asyncio.timeout(self._config.max_cleanup_time):
                while not self._pending_queue.empty():
                    try:
                        item = self._pending_queue.get_nowait()
                        
                        success = await self._force_close_with_retry(item)
                        
                        if success:
                            processed_count += 1
                        else:
                            failed_count += 1
                            
                    except asyncio.QueueEmpty:
                        break
                    except Exception as e:
                        logger.error(
                            "BackgroundCleanup",
                            f"处理清理项异常: {str(e)}"
                        )
                        failed_count += 1
                        
        except asyncio.TimeoutError:
            logger.warning(
                "BackgroundCleanup",
                f"清理任务超时，已处理: {processed_count}, 失败: {failed_count}"
            )
        
        self._cleanup_count += processed_count
        self._last_cleanup_time = datetime.now()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            "BackgroundCleanup",
            f"清理完成，处理: {processed_count}, 失败: {failed_count}, 耗时: {elapsed:.2f}秒"
        )
    
    async def _force_close_with_retry(self, item: PendingCleanupItem) -> bool:
        """
        带重试的强制关闭
        
        Args:
            item: 待清理项
            
        Returns:
            是否成功关闭
        """
        for attempt in range(item.max_retries):
            try:
                await self._force_close_connection(item.connection, item.connection_name)
                
                logger.debug(
                    "BackgroundCleanup",
                    f"@{item.connection_name}",
                    f"强制关闭成功，重试次数: {attempt}"
                )
                return True
                
            except Exception as e:
                if attempt < item.max_retries - 1:
                    logger.debug(
                        "BackgroundCleanup",
                        f"@{item.connection_name}",
                        f"强制关闭失败，将重试（{attempt + 1}/{item.max_retries}）: {str(e)}"
                    )
                    await asyncio.sleep(1.0)
                else:
                    logger.error(
                        "BackgroundCleanup",
                        f"@{item.connection_name}",
                        f"强制关闭失败，已达最大重试次数: {str(e)}"
                    )
                    return False
        
        return False
    
    async def _force_close_connection(self, conn: Any, connection_name: str):
        """
        强制关闭连接
        
        Args:
            conn: 连接对象
            connection_name: 连接名称
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
                            "BackgroundCleanup",
                            f"@{connection_name}",
                            f"关闭连接池时出错: {str(e)}"
                        )
                
                if hasattr(pool, '_connections'):
                    pool._connections.clear()
                if hasattr(pool, '_used'):
                    pool._used.clear()
                if hasattr(pool, '_idle'):
                    pool._idle.clear()
            
            if hasattr(conn, '_valid'):
                conn._valid = False
            if hasattr(conn, '_closed'):
                conn._closed = True
            
            logger.debug(
                "BackgroundCleanup",
                f"@{connection_name}",
                "连接已强制关闭"
            )
            
        except Exception as e:
            logger.warning(
                "BackgroundCleanup",
                f"@{connection_name}",
                f"强制关闭连接时出错: {str(e)}"
            )
            raise
    
    def get_queue_size(self) -> int:
        """
        获取队列大小
        
        Returns:
            队列大小
        """
        return self._pending_queue.qsize()
    
    def get_status(self) -> dict:
        """
        获取任务状态
        
        Returns:
            状态信息
        """
        return {
            "is_running": self._is_running,
            "queue_size": self.get_queue_size(),
            "max_queue_size": self._config.max_cleanup_queue_size,
            "cleanup_count": self._cleanup_count,
            "last_cleanup_time": self._last_cleanup_time.isoformat() if self._last_cleanup_time else None
        }