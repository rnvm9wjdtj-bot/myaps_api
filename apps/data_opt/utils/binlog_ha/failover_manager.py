"""
Binlog 监听器 - 主备故障转移管理器

提供主备选举、心跳维护、故障转移功能
"""
import os
import time
import json
import threading
import socket
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum

from .models import ListenerRole
from .enhanced_lock import EnhancedDistributedLock, LockResult
from .prometheus_metrics import prometheus_metrics
from globalobjects import logger


class FailoverManager:
    """主备故障转移管理器"""
    
    HEARTBEAT_KEY = "binlog:heartbeat"
    MASTER_LOCK_NAME = "binlog:master_lock"
    
    def __init__(
        self,
        heartbeat_interval: int = 10,
        heartbeat_timeout: int = 60,
        lock_ttl: int = 60
    ):
        """
        初始化故障转移管理器
        
        Args:
            heartbeat_interval: 心跳间隔（秒）
            heartbeat_timeout: 心跳超时（秒）
            lock_ttl: 锁TTL（秒）
        """
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.lock_ttl = lock_ttl
        
        self._role = ListenerRole.STANDALONE
        self._lock = EnhancedDistributedLock(
            lock_name=self.MASTER_LOCK_NAME,
            ttl=lock_ttl
        )
        
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._failover_count = 0
        self._last_heartbeat = 0.0
        self._promoted_time: Optional[float] = None
        
        # 升级为主节点时的回调（由 MySQLBinlogListener 注册）
        self._on_promoted_callback = None
        
        # P1修复：线程安全锁 + 关闭标志
        self._state_lock = threading.Lock()
        self._shutdown_requested = False
    
    def register_on_promoted_callback(self, callback):
        """注册升级为主节点时的回调函数"""
        self._on_promoted_callback = callback
    
    def is_master(self) -> bool:
        """
        检查当前节点是否仍是主节点
        
        先快速过内存状态，再主动向 Redis 校验锁持有状态，
        消除网络分区后锁被抢占但内存尚未感知的误判窗口。
        Redis 不可达时信任内存状态，避免误伤。
        """
        if self._role != ListenerRole.MASTER:
            return False
        
        # 主动向 Redis 验证锁仍由本节点持有
        return self._lock.verify_hold()
    
    def _get_redis_client(self):
        """获取Redis客户端"""
        try:
            from apps.common.utils.redis_pool_manager import get_redis_pool_manager
            pool_manager = get_redis_pool_manager()
            return pool_manager.get_client()
        except Exception as e:
            logger.warning(f"⚠️ 获取Redis客户端失败: {e}")
            return None
    
    def acquire_master_role(self) -> bool:
        """
        竞争主节点角色
        
        流程：
        1. 尝试获取分布式锁
        2. 成功 → 升级为主节点，启动心跳线程
        3. 失败 → 降级为备节点，启动监控线程
        
        Returns:
            是否成功成为主节点
        """
        result = self._lock.acquire()
        
        if result.success:
            self._role = ListenerRole.MASTER
            self._promoted_time = time.time()
            
            prometheus_metrics.set_listener_role("master")
            
            self._start_heartbeat_thread()
            
            logger.success(
                "主节点选举",
                "FailoverManager",
                f"已升级为主节点 (mode={result.mode.value})"
            )
            
            return True
        else:
            self._role = ListenerRole.SLAVE
            
            prometheus_metrics.set_listener_role("slave")
            
            self._start_monitor_thread()
            
            logger.info(
                f"⏳ 已降级为备节点 (reason={result.reason})"
            )
            
            return False
    
    def _start_heartbeat_thread(self):
        """启动心跳线程（主节点专用）"""
        if self._heartbeat_thread is not None:
            return
        
        def heartbeat_loop():
            while not self._stop_event.is_set():
                try:
                    self.update_heartbeat()
                    self._stop_event.wait(self.heartbeat_interval)
                except Exception as e:
                    logger.error(f"心跳更新失败: {e}")
        
        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            daemon=True,
            name='binlog-heartbeat'
        )
        self._heartbeat_thread.start()
        logger.info_console("✅ 心跳线程已启动（主节点）")
    
    def _start_monitor_thread(self):
        """启动监控线程（备节点专用）"""
        if self._monitor_thread is not None:
            return
        
        def monitor_loop():
            while not self._stop_event.is_set():
                try:
                    master_healthy = self.monitor_master()
                    
                    if not master_healthy:
                        logger.warning("⚠️ 主节点心跳超时，尝试接管...")
                        if self.promote_to_master():
                            break
                    
                    self._stop_event.wait(self.heartbeat_interval)
                    
                except Exception as e:
                    logger.error(f"主节点监控失败: {e}")
        
        self._monitor_thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name='binlog-monitor'
        )
        self._monitor_thread.start()
        logger.info("✅ 监控线程已启动（备节点）")
    
    def update_heartbeat(self):
        """
        更新心跳时间戳（主节点专用）
        
        Redis存储：
        - Key: binlog:heartbeat
        - Value: {timestamp, pid, hostname, binlog_file, binlog_pos}
        - TTL: heartbeat_timeout × 2
        """
        try:
            client = self._get_redis_client()
            if not client:
                return
            
            heartbeat_data = {
                "timestamp": time.time(),
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "role": "master",
                "promoted_at": self._promoted_time
            }
            
            ttl = self.heartbeat_timeout * 2
            client.setex(
                self.HEARTBEAT_KEY,
                ttl,
                json.dumps(heartbeat_data)
            )
            
            self._last_heartbeat = time.time()
            
            prometheus_metrics.set_heartbeat_delay(0)
            
            logger.debug(f"💓 心跳已更新: timestamp={heartbeat_data['timestamp']}")
            
        except Exception as e:
            logger.warning(f"⚠️ 心跳更新失败: {e}")
    
    def monitor_master(self) -> bool:
        """
        监控主节点心跳（备节点专用）
        
        Returns:
            主节点是否健康
        """
        try:
            client = self._get_redis_client()
            if not client:
                return True
            
            data = client.get(self.HEARTBEAT_KEY)
            
            if not data:
                logger.warning("⚠️ 主节点心跳不存在")
                return False
            
            heartbeat = json.loads(data.decode())
            last_heartbeat = heartbeat.get("timestamp", 0)
            
            delay = time.time() - last_heartbeat
            prometheus_metrics.set_heartbeat_delay(delay)
            
            if delay > self.heartbeat_timeout:
                logger.warning(
                    f"⚠️ 主节点心跳超时: delay={delay:.1f}s, "
                    f"timeout={self.heartbeat_timeout}s, "
                    f"master_pid={heartbeat.get('pid')}, "
                    f"master_host={heartbeat.get('hostname')}"
                )
                return False
            
            logger.debug(
                f"✅ 主节点健康: delay={delay:.1f}s, "
                f"master_pid={heartbeat.get('pid')}"
            )
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 主节点心跳检查失败: {e}")
            return True
    
    def promote_to_master(self) -> bool:
        """
        升级为主节点
        
        流程：
        1. 尝试获取分布式锁
        2. 从持久化存储恢复Binlog位置
        3. 启动监听循环
        4. 发送故障转移告警
        
        Returns:
            是否成功升级
        """
        logger.info("🔄 开始故障转移...")
        
        result = self._lock.acquire()
        
        if not result.success:
            logger.warning("⚠️ 故障转移失败：无法获取锁")
            return False
        
        self._role = ListenerRole.MASTER
        self._promoted_time = time.time()
        self._failover_count += 1
        
        prometheus_metrics.set_listener_role("master")
        prometheus_metrics.inc_failover_count()
        
        if self._monitor_thread:
            self._stop_event.set()
            self._monitor_thread = None
        self._stop_event.clear()
        
        self._start_heartbeat_thread()
        
        # 执行升级回调（启动 binlog 监听），异步重试避免阻塞心跳线程
        if self._on_promoted_callback:
            self._execute_callback_async()
        
        logger.success(
            "故障转移",
            "FailoverManager",
            f"已成功升级为主节点 (failover_count={self._failover_count})"
        )
        
        return True
    
    def _execute_callback_async(self):
        """异步执行升级回调（独立线程，避免阻塞心跳）"""
        def _retry_callback():
            callback_max_retries = 3
            callback_ok = False
            
            for attempt in range(1, callback_max_retries + 1):
                try:
                    self._on_promoted_callback()
                    callback_ok = True
                    break
                except Exception as e:
                    if attempt < callback_max_retries:
                        wait = attempt * 2  # 2s, 4s
                        logger.warning(
                            f"⚠️ 主节点升级回调执行失败 (attempt={attempt}/{callback_max_retries})，"
                            f"{wait}s 后重试: {e}"
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"❌ 主节点升级回调执行失败 (attempt={attempt}/{callback_max_retries})，"
                            f"已耗尽重试次数: {e}"
                        )
            
            if not callback_ok:
                logger.error("❌ 升级回调全部失败，降级为备节点")
                # P1修复：加锁保护降级逻辑，防止与 stop() 竞态
                with self._state_lock:
                    self._stop_event.set()
                    if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                        self._heartbeat_thread.join(timeout=5)
                        self._heartbeat_thread = None
                    
                    # 仅在未请求关闭时清除 stop_event，避免覆盖 stop() 的关闭信号
                    if not self._shutdown_requested:
                        self._stop_event.clear()
                    
                    # 释放锁前检查是否仍持有
                    if self._lock.is_holder:
                        self._lock.release()
                    
                    self._role = ListenerRole.SLAVE
                
                prometheus_metrics.set_listener_role("slave")
                self._start_monitor_thread()
                
                logger.info("⏳ 已降级为备节点，继续监控主节点心跳")
        
        callback_thread = threading.Thread(
            target=_retry_callback,
            daemon=True,
            name='binlog-callback-retry'
        )
        callback_thread.start()
        logger.info("✅ 升级回调线程已启动（异步重试）")
    
    def get_role(self) -> ListenerRole:
        """获取当前角色"""
        return self._role
    
    def get_master_info(self) -> Optional[Dict[str, Any]]:
        """获取主节点信息（备节点专用）"""
        try:
            client = self._get_redis_client()
            if not client:
                return None
            
            data = client.get(self.HEARTBEAT_KEY)
            if not data:
                return None
            
            heartbeat = json.loads(data.decode())
            heartbeat["delay"] = time.time() - heartbeat.get("timestamp", 0)
            
            return heartbeat
            
        except Exception as e:
            logger.warning(f"⚠️ 获取主节点信息失败: {e}")
            return None
    
    def get_failover_count(self) -> int:
        """获取故障转移次数"""
        return self._failover_count
    
    def stop(self):
        """停止故障转移管理器"""
        with self._state_lock:
            self._shutdown_requested = True
            self._stop_event.set()
        
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        
        # P1修复：释放锁前检查是否仍持有
        if self._lock.is_holder:
            self._lock.release()
        
        logger.info("🛑 故障转移管理器已停止")


failover_manager = FailoverManager()
