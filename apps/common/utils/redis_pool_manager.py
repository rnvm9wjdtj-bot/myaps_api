"""
Redis 连接池管理器 - 提供全局 Redis 连接池单例

功能特性：
1. 全局连接池单例，避免连接泄漏
2. 支持连接池参数配置
3. 提供获取 Redis 客户端的方法
4. 支持本地文件缓冲，Redis 不可用时降级

使用示例：
    from apps.common.utils.redis_pool_manager import get_redis_client, get_redis_pool

    # 获取 Redis 客户端（自动从连接池获取）
    client = get_redis_client()
    client.lpush('key', 'value')

    # 或直接使用连接池
    pool = get_redis_pool()
"""

import os
import json
import time
import threading
import logging
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime, timezone

import redis
from redis.connection import ConnectionPool

from core.settings import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
from globalobjects import logger as log_config

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)

# Redis 连接池配置
# 根据系统负载和网络环境调整
MAX_CONNECTIONS = 50  # 调整最大连接数，避免过度占用资源
SOCKET_CONNECT_TIMEOUT = 5  # 调整连接超时时间，避免长时间阻塞
SOCKET_TIMEOUT = 5  # 调整读取超时时间，避免长时间阻塞

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'storage'
BUFFER_DIR = STORAGE_DIR / 'event_buffer'
BUFFER_FILE = BUFFER_DIR / 'event_buffer.jsonl'
# 本地缓冲配置
# 根据系统流量和磁盘空间调整
BUFFER_MAX_SIZE = 20000  # 增加缓冲大小，适应高流量场景
BUFFER_CLEANUP_THRESHOLD = 50 * 1024 * 1024  # 50MB，缓冲文件清理阈值


class RedisPoolManager:
    """Redis 连接池管理器 - 单例模式"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._pool: Optional[ConnectionPool] = None
        self._lock = threading.Lock()
        self._buffer_lock = threading.Lock()
        self._initialized = True
        self._buffer_size = 0

        self._init_pool()
        self._ensure_buffer_dir()

    def _init_pool(self):
        """初始化连接池"""
        try:
            self._pool = ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
                max_connections=MAX_CONNECTIONS,
                socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
                socket_timeout=SOCKET_TIMEOUT,
                health_check_interval=30,  # 每30秒检测连接有效性，防止复用僵尸连接
                decode_responses=False
            )
            logger.success("Redis 连接池", "", f"已初始化 (max_connections={MAX_CONNECTIONS})")
        except Exception as e:
            logger.error(f"❌ Redis 连接池初始化失败: {e}")
            self._pool = None

    def _ensure_buffer_dir(self):
        """确保缓冲目录存在"""
        try:
            BUFFER_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"⚠️ 创建缓冲目录失败: {e}")

    def get_client(self) -> Optional[redis.Redis]:
        """获取 Redis 客户端（从连接池）"""
        if self._pool is None:
            logger.warning("⚠️ Redis 连接池未初始化，尝试重新初始化...")
            self._init_pool()
            if self._pool is None:
                return None

        try:
            client = redis.Redis(connection_pool=self._pool)
            return client
        except Exception as e:
            logger.error(f"❌ 获取 Redis 客户端失败: {e}")
            return None

    def _reconnect(self):
        """尝试重新连接 Redis"""
        try:
            self._init_pool()
            if self._pool is not None:
                logger.success("Redis 连接", "", "已重新建立")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Redis 重新连接失败: {e}")
            return False

    def get_client_with_retry(self, max_retries=3) -> Optional[redis.Redis]:
        """获取 Redis 客户端，支持重试"""
        for i in range(max_retries):
            client = self.get_client()
            if client:
                try:
                    client.ping()
                    return client
                except Exception as e:
                    logger.warning(f"⚠️ Redis 客户端 ping 失败 (尝试 {i+1}/{max_retries}): {e}")
                    self._reconnect()
                    continue
        return None

    def is_healthy(self) -> bool:
        """检查 Redis 连接是否健康"""
        client = self.get_client()
        if client is None:
            return False

        try:
            client.ping()
            return True
        except Exception:
            return False

    def lpush_safe(self, key: str, value: str) -> bool:
        """
        安全地推送数据到 Redis，失败时写入本地缓冲

        Returns:
            bool: True 如果成功写入 Redis，False 如果写入缓冲
        """
        client = self.get_client_with_retry()
        if client is None:
            self._write_to_buffer(key, value)
            return False

        try:
            # 设置操作超时
            with client.pipeline() as pipe:
                pipe.lpush(key, value)
                pipe.execute()
            return True
        except redis.ConnectionError as e:
            logger.warning(f"⚠️ Redis 连接错误，写入本地缓冲: {e}")
            self._reconnect()
            self._write_to_buffer(key, value)
            return False
        except redis.TimeoutError as e:
            logger.warning(f"⚠️ Redis 超时错误，写入本地缓冲: {e}")
            self._write_to_buffer(key, value)
            return False
        except Exception as e:
            logger.warning(f"⚠️ Redis lpush 失败，写入本地缓冲: {e}")
            self._write_to_buffer(key, value)
            return False

    def lpush_safe_batch(self, key: str, values: list) -> dict:
        """
        安全地批量推送数据到 Redis，失败时写入本地缓冲

        Args:
            key: Redis 键名
            values: 要推送的值列表

        Returns:
            dict: 包含成功和失败数量的字典
        """
        if not values:
            return {"success": 0, "failed": 0}

        client = self.get_client_with_retry()
        if client is None:
            # 全部写入本地缓冲
            for value in values:
                self._write_to_buffer(key, value)
            return {"success": 0, "failed": len(values)}

        try:
            # 使用 pipeline 批量执行，提高效率
            with client.pipeline() as pipe:
                for value in values:
                    pipe.lpush(key, value)
                pipe.execute()
            return {"success": len(values), "failed": 0}
        except redis.ConnectionError as e:
            logger.warning(f"⚠️ Redis 连接错误，批量写入本地缓冲: {e}")
            self._reconnect()
            # 全部写入本地缓冲
            for value in values:
                self._write_to_buffer(key, value)
            return {"success": 0, "failed": len(values)}
        except redis.TimeoutError as e:
            logger.warning(f"⚠️ Redis 超时错误，批量写入本地缓冲: {e}")
            # 全部写入本地缓冲
            for value in values:
                self._write_to_buffer(key, value)
            return {"success": 0, "failed": len(values)}
        except Exception as e:
            logger.warning(f"⚠️ Redis 批量 lpush 失败，写入本地缓冲: {e}")
            # 全部写入本地缓冲
            for value in values:
                self._write_to_buffer(key, value)
            return {"success": 0, "failed": len(values)}

    def _write_to_buffer(self, key: str, value: str):
        """写入本地缓冲文件"""
        with self._buffer_lock:
            try:
                buffer_entry = {
                    'key': key,
                    'value': value,
                    'timestamp': time.time()
                }
                with open(BUFFER_FILE, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(buffer_entry, ensure_ascii=False) + '\n')
                self._buffer_size += 1

                if self._buffer_size >= BUFFER_MAX_SIZE:
                    self._cleanup_buffer()
            except Exception as e:
                logger.error(f"❌ 写入本地缓冲失败: {e}")

    def _cleanup_buffer(self):
        """清理过大的缓冲文件"""
        try:
            if os.path.exists(BUFFER_FILE):
                file_size = os.path.getsize(BUFFER_FILE)
                # 当文件大小超过阈值或记录数超过阈值时清理
                if file_size > BUFFER_CLEANUP_THRESHOLD or self._buffer_size >= BUFFER_MAX_SIZE:
                    lines = []
                    with open(BUFFER_FILE, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    # 保留最近的一半记录
                    if len(lines) > BUFFER_MAX_SIZE // 2:
                        with open(BUFFER_FILE, 'w', encoding='utf-8') as f:
                            f.writelines(lines[-BUFFER_MAX_SIZE // 2:])
                        logger.info_console(f"🗑️ 缓冲文件已清理，保留最近 {BUFFER_MAX_SIZE // 2} 条记录")
                    
                    # 重新计算缓冲大小
                    self._buffer_size = len(lines[-BUFFER_MAX_SIZE // 2:]) if len(lines) > BUFFER_MAX_SIZE // 2 else len(lines)
        except Exception as e:
            logger.warning(f"⚠️ 清理缓冲文件失败: {e}")

    def flush_buffer(self, redis_key: str = 'db_events') -> int:
        """
        将本地缓冲数据刷新到 Redis

        Returns:
            int: 成功刷新的事件数量
        """
        flushed_count = 0
        failed_count = 0
        total_count = 0

        with self._buffer_lock:
            if not os.path.exists(BUFFER_FILE):
                return 0

            try:
                # 使用带重试的客户端获取方法
                client = self.get_client_with_retry()
                if client is None:
                    logger.warning("⚠️ Redis 不可用，无法刷新缓冲")
                    return 0

                temp_file = BUFFER_FILE.with_suffix('.jsonl.tmp')
                batch_size = 100  # 批量处理大小
                batch_values = []
                
                start_time = time.time()
                
                with open(BUFFER_FILE, 'r', encoding='utf-8') as f_in:
                    with open(temp_file, 'w', encoding='utf-8') as f_out:
                        for line in f_in:
                            total_count += 1
                            try:
                                entry = json.loads(line.strip())
                                value = entry.get('value', '')
                                if value:
                                    batch_values.append(value)
                                    
                                    # 达到批量大小或文件结束时执行批量操作
                                    if len(batch_values) >= batch_size:
                                        # 使用 pipeline 批量执行，提高效率
                                        with client.pipeline() as pipe:
                                            for val in batch_values:
                                                pipe.lpush(redis_key, val)
                                            pipe.execute()
                                        flushed_count += len(batch_values)
                                        batch_values = []
                            except json.JSONDecodeError as e:
                                logger.debug(f"⚠️ 解析缓冲数据失败: {e}")
                                f_out.write(line)
                                failed_count += 1
                            except redis.ConnectionError as e:
                                logger.warning(f"⚠️ Redis 连接错误，保留缓冲数据: {e}")
                                # 保存当前批次到失败文件
                                for val in batch_values:
                                    f_out.write(json.dumps({"key": redis_key, "value": val, "timestamp": time.time()}) + '\n')
                                failed_count += len(batch_values)
                                batch_values = []
                                f_out.write(line)
                                failed_count += 1
                                # 尝试重新连接
                                self._reconnect()
                            except redis.TimeoutError as e:
                                logger.warning(f"⚠️ Redis 超时错误，保留缓冲数据: {e}")
                                # 保存当前批次到失败文件
                                for val in batch_values:
                                    f_out.write(json.dumps({"key": redis_key, "value": val, "timestamp": time.time()}) + '\n')
                                failed_count += len(batch_values)
                                batch_values = []
                                f_out.write(line)
                                failed_count += 1
                            except Exception as e:
                                logger.warning(f"⚠️ 处理缓冲数据失败: {e}")
                                # 保存当前批次到失败文件
                                for val in batch_values:
                                    f_out.write(json.dumps({"key": redis_key, "value": val, "timestamp": time.time()}) + '\n')
                                failed_count += len(batch_values)
                                batch_values = []
                                f_out.write(line)
                                failed_count += 1
                
                # 处理剩余的批次
                if batch_values:
                    try:
                        with client.pipeline() as pipe:
                            for val in batch_values:
                                pipe.lpush(redis_key, val)
                            pipe.execute()
                        flushed_count += len(batch_values)
                    except Exception as e:
                        logger.warning(f"⚠️ 处理剩余批次失败: {e}")
                        # 保存剩余批次到失败文件
                        with open(temp_file, 'a', encoding='utf-8') as f_out:
                            for val in batch_values:
                                f_out.write(json.dumps({"key": redis_key, "value": val, "timestamp": time.time()}) + '\n')
                        failed_count += len(batch_values)
                
                os.replace(temp_file, BUFFER_FILE)
                
                elapsed_time = time.time() - start_time
                if total_count > 0:
                    success_rate = (flushed_count / total_count) * 100
                    logger.info(f"缓冲刷新完成: 总计 {total_count} 个事件，成功 {flushed_count} 个，失败 {failed_count} 个，成功率: {success_rate:.2f}%，耗时: {elapsed_time:.2f}秒")
                if flushed_count > 0:
                    logger.success("缓冲刷新", "", f"成功刷新 {flushed_count} 个事件到 Redis，耗时: {elapsed_time:.2f}秒")
                if failed_count > 0:
                    logger.warning(f"⚠️ 缓冲刷新失败，保留 {failed_count} 个事件")

                self._buffer_size = failed_count
                return flushed_count

            except Exception as e:
                logger.error(f"❌ 刷新缓冲失败: {e}")
                return 0

    def get_buffer_size(self) -> int:
        """获取缓冲文件中的事件数量"""
        if not os.path.exists(BUFFER_FILE):
            return 0

        try:
            with open(BUFFER_FILE, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def get_pool_status(self) -> dict:
        """获取连接池状态"""
        if self._pool is None:
            return {
                'initialized': False,
                'max_connections': 0,
                'current_connections': 0,
                'buffer_size': self.get_buffer_size(),
                'healthy': False
            }

        try:
            # 尝试获取连接池使用情况
            current_connections = 0
            if hasattr(self._pool, '_in_use_connections'):
                current_connections = len(self._pool._in_use_connections)
            elif hasattr(self._pool, '_connections'):
                current_connections = len(self._pool._connections)
            
            # 检查连接健康状态
            healthy = self.is_healthy()
            
            return {
                'initialized': True,
                'max_connections': self._pool.max_connections,
                'current_connections': current_connections,
                'buffer_size': self.get_buffer_size(),
                'healthy': healthy,
                'host': REDIS_HOST,
                'port': REDIS_PORT,
                'db': REDIS_DB
            }
        except Exception as e:
            logger.warning(f"⚠️ 获取连接池状态失败: {e}")
            return {
                'initialized': True,
                'healthy': False,
                'error': str(e),
                'buffer_size': self.get_buffer_size()
            }

    def get_monitoring_metrics(self) -> dict:
        """获取监控指标"""
        try:
            status = self.get_pool_status()
            metrics = {
                'redis_healthy': status.get('healthy', False),
                'redis_connections_used': status.get('current_connections', 0),
                'redis_connections_max': status.get('max_connections', 0),
                'redis_buffer_size': status.get('buffer_size', 0),
                'redis_connection_usage': 0,
                'buffer_threshold': BUFFER_MAX_SIZE
            }
            
            # 计算连接使用率
            if status.get('max_connections', 0) > 0:
                metrics['redis_connection_usage'] = (
                    status.get('current_connections', 0) / status.get('max_connections', 1)
                ) * 100
            
            # 计算缓冲使用率
            if BUFFER_MAX_SIZE > 0:
                metrics['buffer_usage'] = (status.get('buffer_size', 0) / BUFFER_MAX_SIZE) * 100
            
            # 检查是否需要告警
            metrics['needs_alert'] = False
            alerts = []
            
            if not status.get('healthy', False):
                alerts.append('Redis 连接不健康')
                metrics['needs_alert'] = True
            
            if metrics['redis_connection_usage'] > 80:
                alerts.append(f'Redis 连接使用率过高: {metrics["redis_connection_usage"]:.2f}%')
                metrics['needs_alert'] = True
            
            if status.get('buffer_size', 0) > BUFFER_MAX_SIZE * 0.8:
                alerts.append(f'Redis 本地缓冲过大: {status.get("buffer_size", 0)} 条记录')
                metrics['needs_alert'] = True
            
            metrics['alerts'] = alerts
            return metrics
        except Exception as e:
            logger.error(f"⚠️ 获取监控指标失败: {e}")
            return {
                'redis_healthy': False,
                'redis_connections_used': 0,
                'redis_connections_max': 0,
                'redis_buffer_size': 0,
                'redis_connection_usage': 0,
                'buffer_threshold': BUFFER_MAX_SIZE,
                'buffer_usage': 0,
                'needs_alert': True,
                'alerts': [f'获取监控指标失败: {str(e)}']
            }


_redis_pool_manager: Optional[RedisPoolManager] = None


def get_redis_pool_manager() -> RedisPoolManager:
    """获取 Redis 连接池管理器单例"""
    global _redis_pool_manager
    if _redis_pool_manager is None:
        _redis_pool_manager = RedisPoolManager()
    return _redis_pool_manager


def get_redis_client() -> Optional[redis.Redis]:
    """获取 Redis 客户端（便捷函数）"""
    return get_redis_pool_manager().get_client()


def get_redis_pool() -> Optional[ConnectionPool]:
    """获取 Redis 连接池（便捷函数）"""
    return get_redis_pool_manager()._pool


def flush_event_buffer(redis_key: str = 'db_events') -> int:
    """刷新本地事件缓冲到 Redis（便捷函数）"""
    return get_redis_pool_manager().flush_buffer(redis_key)
