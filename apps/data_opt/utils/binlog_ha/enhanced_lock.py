"""
Binlog 监听器 - 分布式锁增强

提供安全降级策略的主备选举机制
"""
import os
import time
import threading
import uuid
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from .models import EnvMode, FallbackMode
from globalobjects import logger


class LockResult:
    """锁获取结果"""
    
    def __init__(
        self,
        success: bool,
        mode: FallbackMode = FallbackMode.REDIS,
        reason: Optional[str] = None
    ):
        self.success = success
        self.mode = mode
        self.reason = reason
    
    def __bool__(self) -> bool:
        return self.success


class EnhancedDistributedLock:
    """分布式锁（增强版 - 支持安全降级）"""
    
    def __init__(
        self,
        lock_name: str = "binlog_listener_lock",
        ttl: int = 30,
        environment_mode: EnvMode = EnvMode.SINGLE_NODE,
        redis_failure_threshold: int = 3
    ):
        """
        初始化增强分布式锁
        
        Args:
            lock_name: 锁名称
            ttl: 锁TTL（秒）
            environment_mode: 运行环境模式
            redis_failure_threshold: Redis连续失败阈值，超过此值触发告警
        """
        self.lock_name = lock_name
        self.ttl = ttl
        self.environment_mode = environment_mode
        
        self._lock_holder = False
        self._lock_value: Optional[str] = None
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        self._redis_health = True
        self._last_redis_check = 0.0
        self._redis_check_interval = 10.0
        
        # P3优化：Redis连续失败计数器
        self._redis_failure_count = 0
        self._redis_failure_threshold = redis_failure_threshold
    
    def _get_redis_client(self):
        """获取Redis客户端"""
        try:
            from apps.common.utils.redis_pool_manager import get_redis_pool_manager
            pool_manager = get_redis_pool_manager()
            return pool_manager.get_client()
        except Exception as e:
            logger.warning(f"⚠️ 获取Redis客户端失败: {e}")
            return None
    
    def _check_redis_health(self) -> bool:
        """检查Redis健康状态"""
        current_time = time.time()
        
        if current_time - self._last_redis_check < self._redis_check_interval:
            return self._redis_health
        
        self._last_redis_check = current_time
        
        try:
            client = self._get_redis_client()
            if not client:
                self._redis_health = False
                return False
            
            client.ping()
            self._redis_health = True
            return True
            
        except Exception as e:
            self._redis_health = False
            logger.warning(f"⚠️ Redis健康检查失败: {e}")
            return False
    
    def _detect_environment(self) -> EnvMode:
        """检测运行环境"""
        return self.environment_mode
    
    def acquire(self) -> LockResult:
        """
        获取分布式锁（增强降级逻辑）
        
        降级策略：
        - 单机模式 + Redis可用 → 使用Redis锁
        - 单机模式 + Redis不可用 → 允许单实例启动
        - 多worker模式 + Redis可用 → 使用Redis锁
        - 多worker模式 + Redis不可用 → 拒绝启动（安全策略）
        
        Returns:
            锁获取结果
        """
        redis_healthy = self._check_redis_health()
        env_mode = self._detect_environment()
        
        if not redis_healthy:
            if env_mode == EnvMode.MULTI_WORKER:
                logger.error(
                    f"❌ 多worker模式下Redis不可用，拒绝启动 "
                    f"(lock={self.lock_name})"
                )
                return LockResult(
                    success=False,
                    mode=FallbackMode.REJECT,
                    reason="multi_worker_requires_redis"
                )
            else:
                logger.warning(
                    f"⚠️ Redis不可用，降级为单实例模式 "
                    f"(lock={self.lock_name}, env={env_mode.value})"
                )
                self._lock_holder = True
                return LockResult(
                    success=True,
                    mode=FallbackMode.SINGLE_INSTANCE,
                    reason="redis_unavailable_fallback"
                )
        
        try:
            client = self._get_redis_client()
            if not client:
                return LockResult(
                    success=False,
                    mode=FallbackMode.REJECT,
                    reason="redis_client_unavailable"
                )
            
            self._lock_value = f"{os.getpid()}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            
            if client.set(self.lock_name, self._lock_value, nx=True, ex=self.ttl):
                logger.info(f"✅ 成功获取分布式锁: {self.lock_name}")
                self._lock_holder = True
                self._start_refresh_thread()
                return LockResult(
                    success=True,
                    mode=FallbackMode.REDIS
                )
            else:
                logger.info(f"⏳ 分布式锁已被其他节点持有: {self.lock_name}")
                self._lock_holder = False
                return LockResult(
                    success=False,
                    mode=FallbackMode.REDIS,
                    reason="lock_already_held"
                )
                
        except Exception as e:
            logger.error(f"❌ 获取分布式锁异常: {e}")
            
            if env_mode == EnvMode.MULTI_WORKER:
                return LockResult(
                    success=False,
                    mode=FallbackMode.REJECT,
                    reason=f"redis_error_in_multi_worker: {e}"
                )
            else:
                self._lock_holder = True
                return LockResult(
                    success=True,
                    mode=FallbackMode.SINGLE_INSTANCE,
                    reason=f"redis_error_fallback: {e}"
                )
    
    def _start_refresh_thread(self):
        """启动锁刷新线程"""
        if self._refresh_thread is not None:
            return
        
        def refresh_loop():
            while not self._stop_event.is_set():
                try:
                    time.sleep(self.ttl // 2)
                    
                    if self._lock_holder and self._lock_value:
                        client = self._get_redis_client()
                        if client:
                            current_value = client.get(self.lock_name)
                            if current_value and current_value.decode() == self._lock_value:
                                client.expire(self.lock_name, self.ttl)
                                logger.debug(f"🔄 已刷新分布式锁: {self.lock_name}")
                            else:
                                logger.warning(f"⚠️ 锁已被其他节点抢占: {self.lock_name}")
                                self._lock_holder = False
                                break
                except Exception as e:
                    logger.debug(f"刷新分布式锁失败: {e}")
        
        self._refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info("✅ 分布式锁刷新线程已启动")
    
    def release(self):
        """释放分布式锁"""
        try:
            self._stop_event.set()
            
            if self._refresh_thread and self._refresh_thread.is_alive():
                self._refresh_thread.join(timeout=1)
            
            if self._lock_holder and self._lock_value:
                client = self._get_redis_client()
                if client:
                    current_value = client.get(self.lock_name)
                    if current_value and current_value.decode() == self._lock_value:
                        client.delete(self.lock_name)
                        logger.info(f"✅ 已释放分布式锁: {self.lock_name}")
                    
        except Exception as e:
            logger.error(f"❌ 释放分布式锁失败: {e}")
        finally:
            self._lock_holder = False
            self._lock_value = None
    
    def verify_hold(self) -> bool:
        """
        主动向 Redis 校验锁是否仍由本节点持有
        
        与 is_holder 不同，此方法会实际查询 Redis，
        消除内存状态滞后窗口（如网络分区后锁已被抢占）。
        
        Returns:
            是否仍持有锁（Redis 不可达时信任内存状态）
        """
        if not self._lock_holder or not self._lock_value:
            return False
        
        try:
            client = self._get_redis_client()
            if not client:
                # P3优化：Redis不可达，增加失败计数
                self._redis_failure_count += 1
                if self._redis_failure_count >= self._redis_failure_threshold:
                    logger.error(
                        f"❌ Redis连续失败{self._redis_failure_count}次，"
                        f"可能存在网络故障或脑裂风险"
                    )
                # 信任内存状态（避免误伤）
                return self._lock_holder
            
            # Redis可达，重置失败计数
            self._redis_failure_count = 0
            
            current_value = client.get(self.lock_name)
            if current_value is None:
                # 锁已过期/被删除
                self._lock_holder = False
                return False
            
            if current_value.decode() != self._lock_value:
                # 锁已被其他节点抢占
                self._lock_holder = False
                return False
            
            return True
            
        except Exception as e:
            # P3优化：异常时增加失败计数
            self._redis_failure_count += 1
            logger.warning(f"⚠️ 锁状态校验失败（信任内存状态）: {e}")
            return self._lock_holder
    
    @property
    def is_holder(self) -> bool:
        """当前节点是否是锁持有者（内存状态，可能有滞后）"""
        return self._lock_holder
    
    @property
    def redis_failure_count(self) -> int:
        """当前 Redis 连续失败次数"""
        return self._redis_failure_count


enhanced_distributed_lock = EnhancedDistributedLock()
