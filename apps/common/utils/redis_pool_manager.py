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

MAX_CONNECTIONS = 50
SOCKET_CONNECT_TIMEOUT = 5
SOCKET_TIMEOUT = 5

STORAGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'storage'
BUFFER_DIR = STORAGE_DIR / 'event_buffer'
BUFFER_FILE = BUFFER_DIR / 'event_buffer.jsonl'
BUFFER_MAX_SIZE = 10000


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
        client = self.get_client()
        if client is None:
            self._write_to_buffer(key, value)
            return False

        try:
            client.lpush(key, value)
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis lpush 失败，写入本地缓冲: {e}")
            self._write_to_buffer(key, value)
            return False

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
                if file_size > 50 * 1024 * 1024:
                    lines = []
                    with open(BUFFER_FILE, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    if len(lines) > BUFFER_MAX_SIZE // 2:
                        with open(BUFFER_FILE, 'w', encoding='utf-8') as f:
                            f.writelines(lines[-BUFFER_MAX_SIZE // 2:])
                        logger.info(f"🗑️ 缓冲文件已清理，保留最近 {BUFFER_MAX_SIZE // 2} 条记录")
            self._buffer_size = 0
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

        with self._buffer_lock:
            if not os.path.exists(BUFFER_FILE):
                return 0

            try:
                client = self.get_client()
                if client is None:
                    logger.warning("⚠️ Redis 不可用，无法刷新缓冲")
                    return 0

                temp_file = BUFFER_FILE.with_suffix('.jsonl.tmp')
                with open(BUFFER_FILE, 'r', encoding='utf-8') as f_in:
                    with open(temp_file, 'w', encoding='utf-8') as f_out:
                        for line in f_in:
                            try:
                                entry = json.loads(line.strip())
                                value = entry.get('value', '')
                                if value:
                                    client.lpush(redis_key, value)
                                    flushed_count += 1
                            except json.JSONDecodeError:
                                continue
                            except Exception as e:
                                f_out.write(line)
                                failed_count += 1

                os.replace(temp_file, BUFFER_FILE)

                if flushed_count > 0:
                    logger.success("缓冲刷新", "", f"成功刷新 {flushed_count} 个事件到 Redis")
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
                'current_connections': 0
            }

        try:
            return {
                'initialized': True,
                'max_connections': self._pool.max_connections,
                'current_connections': len(self._pool._in_use_connections) if hasattr(self._pool, '_in_use_connections') else 'unknown',
                'buffer_size': self.get_buffer_size()
            }
        except Exception as e:
            logger.warning(f"⚠️ 获取连接池状态失败: {e}")
            return {'initialized': True, 'error': str(e)}


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
