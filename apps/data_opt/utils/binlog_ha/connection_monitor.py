"""
Binlog 监听器 - 连接池监控器

提供连接追踪、泄漏检测功能
"""
import threading
import time
import traceback
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

from globalobjects import logger


@dataclass
class ConnectionInfo:
    """连接信息"""
    conn_id: int
    checkout_time: float
    stack_trace: str
    thread_id: int
    database: Optional[str] = None


@dataclass
class LeakInfo:
    """泄漏信息"""
    conn_id: int
    holding_time: float
    stack_trace: str
    thread_id: int


@dataclass
class PoolStats:
    """连接池统计"""
    active_count: int
    idle_count: int
    wait_count: int
    total_checkout: int
    total_checkin: int
    leak_detected: int


class ConnectionPoolMonitor:
    """连接池监控器"""
    
    def __init__(self, leak_threshold: int = 30):
        """
        初始化连接池监控器
        
        Args:
            leak_threshold: 泄漏检测阈值（秒）
        """
        self._active_connections: Dict[int, ConnectionInfo] = {}
        self._leak_threshold = leak_threshold
        self._lock = threading.RLock()
        self._stats = PoolStats(
            active_count=0,
            idle_count=0,
            wait_count=0,
            total_checkout=0,
            total_checkin=0,
            leak_detected=0
        )
    
    def track_connection(
        self,
        conn_id: int,
        database: Optional[str] = None
    ) -> ConnectionInfo:
        """
        追踪新签出的连接
        
        Args:
            conn_id: 连接ID
            database: 数据库名称
        
        Returns:
            连接信息对象
        """
        with self._lock:
            stack_trace = ''.join(traceback.format_stack()[-5:-1])
            
            info = ConnectionInfo(
                conn_id=conn_id,
                checkout_time=time.time(),
                stack_trace=stack_trace,
                thread_id=threading.get_ident(),
                database=database
            )
            
            self._active_connections[conn_id] = info
            self._stats.active_count = len(self._active_connections)
            self._stats.total_checkout += 1
            
            logger.debug(f"📥 连接签出: id={conn_id}, database={database}")
            
            return info
    
    def release_connection(self, conn_id: int) -> bool:
        """
        标记连接归还
        
        Args:
            conn_id: 连接ID
        
        Returns:
            是否成功释放
        """
        with self._lock:
            if conn_id in self._active_connections:
                info = self._active_connections.pop(conn_id)
                holding_time = time.time() - info.checkout_time
                
                self._stats.active_count = len(self._active_connections)
                self._stats.total_checkin += 1
                
                if holding_time > self._leak_threshold:
                    logger.warning(
                        f"⚠️ 连接持有时间过长: id={conn_id}, "
                        f"holding_time={holding_time:.1f}s, threshold={self._leak_threshold}s"
                    )
                
                logger.debug(f"📤 连接归还: id={conn_id}, holding_time={holding_time:.2f}s")
                return True
            else:
                logger.warning(f"⚠️ 尝试释放未追踪的连接: id={conn_id}")
                return False
    
    def detect_leak(self) -> List[LeakInfo]:
        """
        检测超时未归还的连接
        
        Returns:
            泄漏连接列表
        """
        with self._lock:
            leaks = []
            current_time = time.time()
            
            for conn_id, info in self._active_connections.items():
                holding_time = current_time - info.checkout_time
                
                if holding_time > self._leak_threshold:
                    leak = LeakInfo(
                        conn_id=conn_id,
                        holding_time=holding_time,
                        stack_trace=info.stack_trace,
                        thread_id=info.thread_id
                    )
                    leaks.append(leak)
            
            if leaks:
                self._stats.leak_detected += len(leaks)
                for leak in leaks:
                    logger.warning(
                        f"🚨 连接泄漏检测: id={leak.conn_id}, "
                        f"holding_time={leak.holding_time:.1f}s\n"
                        f"Stack trace:\n{leak.stack_trace}"
                    )
            
            return leaks
    
    def get_pool_stats(self) -> PoolStats:
        """
        获取连接池统计
        
        Returns:
            连接池统计对象
        """
        with self._lock:
            self._stats.active_count = len(self._active_connections)
            return self._stats
    
    def get_active_connections(self) -> List[ConnectionInfo]:
        """获取所有活跃连接"""
        with self._lock:
            return list(self._active_connections.values())
    
    def clear(self):
        """清空追踪记录"""
        with self._lock:
            self._active_connections.clear()
            self._stats.active_count = 0


class ManagedConnection:
    """连接上下文管理器"""
    
    _monitor: Optional[ConnectionPoolMonitor] = None
    _next_conn_id: int = 0
    _id_lock = threading.Lock()
    
    @classmethod
    def set_monitor(cls, monitor: ConnectionPoolMonitor):
        """设置全局监控器"""
        cls._monitor = monitor
    
    @classmethod
    def _generate_conn_id(cls) -> int:
        """生成唯一连接ID"""
        with cls._id_lock:
            cls._next_conn_id += 1
            return cls._next_conn_id
    
    def __init__(self, connection, database: Optional[str] = None):
        """
        初始化连接上下文管理器
        
        Args:
            connection: 数据库连接对象
            database: 数据库名称
        """
        self._connection = connection
        self._database = database
        self._conn_id = self._generate_conn_id()
        self._checkout_time = None
        self._info = None
    
    def __enter__(self):
        """获取连接，记录签出时间"""
        self._checkout_time = time.time()
        
        if self._monitor:
            self._info = self._monitor.track_connection(
                self._conn_id,
                self._database
            )
        
        return self._connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """确保连接释放，检测泄漏"""
        if self._monitor:
            self._monitor.release_connection(self._conn_id)
        
        holding_time = time.time() - self._checkout_time
        
        if exc_type is not None:
            logger.error(
                f"❌ 连接使用异常: id={self._conn_id}, "
                f"error={exc_type.__name__}: {exc_val}"
            )
        
        return False


@contextmanager
def tracked_connection(connection, database: Optional[str] = None, monitor: Optional[ConnectionPoolMonitor] = None):
    """
    追踪连接的上下文管理器
    
    用法：
        with tracked_connection(conn, "my_db", monitor) as conn:
            cursor = conn.cursor()
            ...
    """
    conn_id = int(time.time() * 1000000) % (2**31)
    checkout_time = time.time()
    
    if monitor:
        monitor.track_connection(conn_id, database)
    
    try:
        yield connection
    finally:
        if monitor:
            monitor.release_connection(conn_id)


connection_pool_monitor = ConnectionPoolMonitor()
