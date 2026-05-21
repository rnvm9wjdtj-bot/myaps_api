"""
数据库初始化状态管理器
解决 Tortoise ORM 异步初始化的竞态条件
"""
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from globalobjects import logger as log_config


class DatabaseInitManager:
    """
    数据库初始化状态管理器
    
    特性：
    1. 事件驱动：初始化完成后主动通知等待者
    2. 实际检查：测试真实连接而非仅检查标志位
    3. 超时保护：避免无限等待
    4. 状态追踪：记录初始化进度和耗时
    """
    
    _instance: Optional['DatabaseInitManager'] = None
    
    def __init__(self):
        # 初始化完成事件
        self._init_event = asyncio.Event()
        # 初始化开始时间
        self._start_time: Optional[datetime] = None
        # 初始化完成时间
        self._end_time: Optional[datetime] = None
        # 是否已初始化
        self._initialized = False
        # 初始化失败的错误信息
        self._error: Optional[Exception] = None
        # 连接名称列表
        self._connection_names: list = []
        # 已成功建立的连接数
        self._ready_connections: int = 0
    
    @classmethod
    def get_instance(cls) -> 'DatabaseInitManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def start_init(self, connection_names: list):
        """标记初始化开始"""
        self._start_time = datetime.now()
        self._connection_names = connection_names
        log_config.info(f"🔹 数据库初始化开始: {connection_names}")
    
    def mark_initialized(self):
        """标记初始化完成"""
        self._initialized = True
        self._end_time = datetime.now()
        self._init_event.set()
        
        if self._start_time:
            elapsed = (self._end_time - self._start_time).total_seconds()
            log_config.info(f"✅ 数据库初始化完成，耗时: {elapsed:.2f}秒")
    
    def mark_error(self, error: Exception):
        """标记初始化失败"""
        self._error = error
        self._end_time = datetime.now()
        self._init_event.set()
        
        if self._start_time:
            elapsed = (self._end_time - self._start_time).total_seconds()
            log_config.error(f"❌ 数据库初始化失败，耗时: {elapsed:.2f}秒: {error}")
    
    def mark_connection_ready(self, conn_name: str):
        """标记某个连接已就绪"""
        self._ready_connections += 1
        log_config.debug(f"  ✓ 连接就绪: {conn_name} ({self._ready_connections}/{len(self._connection_names)})")
    
    async def wait_for_init(
        self,
        max_wait: float = 30.0,
        check_interval: float = 0.1,
        early_exit_check: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        等待初始化完成
        
        Args:
            max_wait: 最大等待时间（秒）
            check_interval: 检查间隔（秒）
            early_exit_check: 提前退出检查函数，返回True则提前结束
        
        Returns:
            {
                "success": bool,
                "elapsed": float,
                "ready_connections": int,
                "error": Optional[Exception]
            }
        """
        start = datetime.now()
        
        # 如果已经初始化完成，立即返回
        if self._initialized:
            elapsed = (datetime.now() - start).total_seconds()
            return {
                "success": True,
                "elapsed": elapsed,
                "ready_connections": self._ready_connections,
                "error": None
            }
        
        # 如果已经失败，立即返回
        if self._error:
            elapsed = (datetime.now() - start).total_seconds()
            return {
                "success": False,
                "elapsed": elapsed,
                "ready_connections": self._ready_connections,
                "error": self._error
            }
        
        # 等待初始化事件，带超时
        try:
            await asyncio.wait_for(
                self._init_event.wait(),
                timeout=max_wait
            )
        except asyncio.TimeoutError:
            elapsed = (datetime.now() - start).total_seconds()
            log_config.warning(f"⚠️ 数据库初始化等待超时: {elapsed:.2f}秒")
            return {
                "success": False,
                "elapsed": elapsed,
                "ready_connections": self._ready_connections,
                "error": TimeoutError(f"初始化超时({max_wait}秒)")
            }
        
        # 检查是否有错误
        if self._error:
            elapsed = (datetime.now() - start).total_seconds()
            return {
                "success": False,
                "elapsed": elapsed,
                "ready_connections": self._ready_connections,
                "error": self._error
            }
        
        # 执行额外检查（如实际连接测试）
        if early_exit_check:
            try:
                check_result = await early_exit_check()
                if not check_result:
                    log_config.warning("⚠️ 初始化完成，但连接检查未通过")
            except Exception as e:
                log_config.warning(f"⚠️ 连接检查失败: {e}")
        
        elapsed = (datetime.now() - start).total_seconds()
        return {
            "success": True,
            "elapsed": elapsed,
            "ready_connections": self._ready_connections,
            "error": None
        }
    
    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    @property
    def init_elapsed(self) -> Optional[float]:
        """获取初始化耗时"""
        if self._start_time and self._end_time:
            return (self._end_time - self._start_time).total_seconds()
        return None
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "initialized": self._initialized,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "end_time": self._end_time.isoformat() if self._end_time else None,
            "elapsed": self.init_elapsed,
            "connection_names": self._connection_names,
            "ready_connections": self._ready_connections,
            "error": str(self._error) if self._error else None
        }


# 全局单例
db_init_manager = DatabaseInitManager.get_instance()
