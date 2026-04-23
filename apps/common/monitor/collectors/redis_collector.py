"""
Redis 监控采集器

用于采集 Redis 连接池和操作的监控指标
"""

import logging
from typing import Dict, Any

from apps.common.utils.redis_pool_manager import get_redis_pool_manager

logger = logging.getLogger(__name__)


class RedisCollector:
    """Redis 监控采集器"""
    
    def __init__(self):
        self.pool_manager = get_redis_pool_manager()
    
    def collect(self) -> Dict[str, Any]:
        """采集 Redis 监控指标"""
        try:
            # 获取监控指标
            metrics = self.pool_manager.get_monitoring_metrics()
            
            # 构建采集数据
            data = {
                'healthy': metrics.get('redis_healthy', False),
                'connections_used': metrics.get('redis_connections_used', 0),
                'connections_max': metrics.get('redis_connections_max', 0),
                'connection_usage': metrics.get('redis_connection_usage', 0),
                'buffer_size': metrics.get('redis_buffer_size', 0),
                'buffer_threshold': metrics.get('buffer_threshold', 0),
                'buffer_usage': metrics.get('buffer_usage', 0),
                'needs_alert': metrics.get('needs_alert', False),
                'alerts': metrics.get('alerts', []),
                'timestamp': None  # 时间戳将由调用方添加
            }
            
            # 获取连接池状态的更多信息
            pool_status = self.pool_manager.get_pool_status()
            data.update({
                'host': pool_status.get('host', ''),
                'port': pool_status.get('port', ''),
                'db': pool_status.get('db', ''),
                'initialized': pool_status.get('initialized', False)
            })
            
            return data
        except Exception as e:
            logger.error(f"❌ Redis 监控采集失败: {e}")
            return {
                'healthy': False,
                'connections_used': 0,
                'connections_max': 0,
                'connection_usage': 0,
                'buffer_size': 0,
                'buffer_threshold': 0,
                'buffer_usage': 0,
                'needs_alert': True,
                'alerts': [f'监控采集失败: {str(e)}'],
                'host': '',
                'port': '',
                'db': '',
                'initialized': False,
                'timestamp': None
            }


# 创建全局 Redis 采集器实例
redis_collector = RedisCollector()
