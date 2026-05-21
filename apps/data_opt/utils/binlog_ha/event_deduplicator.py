"""
Binlog 监听器 - 事件去重管理器

提供基于 Redis 的事件去重功能
"""
import hashlib
import time
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .models import EventType, EventMeta
from .prometheus_metrics import prometheus_metrics
from globalobjects import logger


class EventDeduplicator:
    """事件去重管理器"""
    
    REDIS_KEY_PREFIX = "binlog:dedup:"
    STATS_KEY = "binlog:dedup:stats"
    
    def __init__(
        self,
        ttl_hours: int = 24,
        use_redis: bool = True,
        fallback_file: Optional[str] = None
    ):
        """
        初始化事件去重管理器
        
        Args:
            ttl_hours: 去重记录TTL（小时）
            use_redis: 是否使用Redis
            fallback_file: 降级文件路径
        """
        self.ttl_hours = ttl_hours
        self._use_redis = use_redis
        self._fallback_file = fallback_file or "storage/binlog_dedup.json"
        self._fallback_cache: Dict[str, float] = {}
        self._stats = {
            "total_checked": 0,
            "total_duplicates": 0,
            "last_check_time": 0
        }
        self._redis_client = None
    
    def _get_redis_client(self):
        """获取Redis客户端"""
        if self._redis_client is None:
            try:
                from apps.common.utils.redis_pool_manager import get_redis_pool_manager
                pool_manager = get_redis_pool_manager()
                self._redis_client = pool_manager.get_client()
            except Exception as e:
                logger.warning(f"⚠️ 获取Redis客户端失败: {e}")
                return None
        return self._redis_client
    
    def generate_event_id(
        self,
        event_type: str,
        table_name: str,
        primary_key: str,
        timestamp: float
    ) -> str:
        """
        生成事件唯一标识符
        
        公式：SHA256(event_type + table_name + primary_key + timestamp)
        
        Args:
            event_type: 事件类型（INSERT/UPDATE/DELETE）
            table_name: 表名
            primary_key: 主键值
            timestamp: 时间戳
        
        Returns:
            64位十六进制字符串
        """
        raw = f"{event_type}|{table_name}|{primary_key}|{timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()
    
    def generate_event_id_from_event(self, event: Any) -> str:
        """
        从事件对象生成唯一标识符
        
        Args:
            event: Binlog事件对象
        
        Returns:
            事件唯一标识符
        """
        event_type = type(event).__name__.replace("RowsEvent", "").upper()
        
        table = getattr(event, 'table', 'unknown_table')
        schema = getattr(event, 'schema', 'unknown_db')
        log_file = getattr(event, 'log_file', '')
        log_pos = getattr(event, 'log_pos', 0)
        
        primary_key = f"{schema}.{table}:{log_file}:{log_pos}"
        timestamp = time.time()
        
        return self.generate_event_id(event_type, table, primary_key, timestamp)
    
    def is_duplicate(self, event_id: str) -> bool:
        """
        检查事件是否已处理
        
        Args:
            event_id: 事件唯一标识符
        
        Returns:
            是否为重复事件
        """
        self._stats["total_checked"] += 1
        self._stats["last_check_time"] = time.time()
        
        if self._use_redis:
            return self._is_duplicate_redis(event_id)
        else:
            return self._is_duplicate_fallback(event_id)
    
    def _is_duplicate_redis(self, event_id: str) -> bool:
        """Redis去重检查"""
        try:
            client = self._get_redis_client()
            if not client:
                return self._is_duplicate_fallback(event_id)
            
            key = f"{self.REDIS_KEY_PREFIX}{event_id}"
            exists = client.exists(key)
            
            if exists:
                self._stats["total_duplicates"] += 1
                prometheus_metrics.inc_dedup_hits()
                logger.debug(f"🔄 检测到重复事件: {event_id[:16]}...")
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Redis去重检查失败: {e}，降级到文件存储")
            return self._is_duplicate_fallback(event_id)
    
    def _is_duplicate_fallback(self, event_id: str) -> bool:
        """文件存储降级去重检查"""
        current_time = time.time()
        
        if event_id in self._fallback_cache:
            return True
        
        try:
            import os
            if os.path.exists(self._fallback_file):
                with open(self._fallback_file, 'r') as f:
                    data = json.load(f)
                    if event_id in data:
                        timestamp = data[event_id].get('timestamp', 0)
                        if current_time - timestamp < self.ttl_hours * 3600:
                            return True
        except Exception as e:
            logger.warning(f"⚠️ 文件去重检查失败: {e}")
        
        return False
    
    def mark_processed(
        self,
        event_id: str,
        event_type: str,
        table_name: str,
        database_name: str,
        log_file: str,
        log_pos: int
    ) -> bool:
        """
        标记事件已处理
        
        Args:
            event_id: 事件唯一标识符
            event_type: 事件类型
            table_name: 表名
            database_name: 数据库名
            log_file: Binlog文件名
            log_pos: Binlog位置
        
        Returns:
            是否成功标记
        """
        event_meta = {
            "timestamp": time.time(),
            "event_type": event_type,
            "table_name": table_name,
            "database_name": database_name,
            "log_file": log_file,
            "log_pos": log_pos
        }
        
        if self._use_redis:
            return self._mark_processed_redis(event_id, event_meta)
        else:
            return self._mark_processed_fallback(event_id, event_meta)
    
    def _mark_processed_redis(self, event_id: str, event_meta: Dict[str, Any]) -> bool:
        """Redis标记已处理"""
        try:
            client = self._get_redis_client()
            if not client:
                return self._mark_processed_fallback(event_id, event_meta)
            
            key = f"{self.REDIS_KEY_PREFIX}{event_id}"
            ttl_seconds = self.ttl_hours * 3600
            
            client.setex(key, ttl_seconds, json.dumps(event_meta))
            
            try:
                client.hincrby(self.STATS_KEY, "total_marked", 1)
            except:
                pass
            
            logger.debug(f"✅ 事件已标记: {event_id[:16]}...")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Redis标记失败: {e}，降级到文件存储")
            return self._mark_processed_fallback(event_id, event_meta)
    
    def _mark_processed_fallback(self, event_id: str, event_meta: Dict[str, Any]) -> bool:
        """文件存储降级标记"""
        try:
            import os
            
            self._fallback_cache[event_id] = event_meta['timestamp']
            
            os.makedirs(os.path.dirname(self._fallback_file), exist_ok=True)
            
            data = {}
            if os.path.exists(self._fallback_file):
                with open(self._fallback_file, 'r') as f:
                    data = json.load(f)
            
            data[event_id] = event_meta
            
            with open(self._fallback_file, 'w') as f:
                json.dump(data, f)
            
            logger.debug(f"✅ 事件已标记(文件): {event_id[:16]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ 文件标记失败: {e}")
            return False
    
    def cleanup_expired(self):
        """清理过期记录（Redis TTL自动完成，仅用于文件降级）"""
        if self._use_redis:
            return
        
        try:
            import os
            if not os.path.exists(self._fallback_file):
                return
            
            with open(self._fallback_file, 'r') as f:
                data = json.load(f)
            
            current_time = time.time()
            cutoff_time = current_time - self.ttl_hours * 3600
            
            expired_keys = [
                key for key, value in data.items()
                if isinstance(value, dict) and value.get('timestamp', 0) < cutoff_time
            ]
            
            for key in expired_keys:
                del data[key]
                self._fallback_cache.pop(key, None)
            
            if expired_keys:
                with open(self._fallback_file, 'w') as f:
                    json.dump(data, f)
                logger.info(f"🗑️ 已清理 {len(expired_keys)} 条过期去重记录")
                
        except Exception as e:
            logger.warning(f"⚠️ 清理过期记录失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取去重统计信息"""
        return {
            **self._stats,
            "ttl_hours": self.ttl_hours,
            "use_redis": self._use_redis,
            "duplicate_rate": (
                self._stats["total_duplicates"] / self._stats["total_checked"] * 100
                if self._stats["total_checked"] > 0 else 0
            )
        }


event_deduplicator = EventDeduplicator()
