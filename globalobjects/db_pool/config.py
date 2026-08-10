"""
数据库连接池配置管理

从环境变量读取配置参数，提供默认值和验证。
"""
import os
from typing import Optional
from globalobjects.db_pool.db_pool_models import PoolManagerConfig


def get_pool_config() -> PoolManagerConfig:
    """
    从环境变量获取连接池管理配置
    
    环境变量:
        DBPOOL_USE_ENHANCED: 是否使用增强的连接池管理(默认True)
        DBPOOL_STATE_LOCK_TIMEOUT: 状态锁超时时间(默认10.0秒)
        DBPOOL_HEALTH_CHECK_TIMEOUT: 健康检查超时时间(默认10.0秒)
        DBPOOL_HEALTH_CHECK_SQL: 健康检查SQL语句(默认"SELECT 1")
        DBPOOL_CLEANUP_INTERVAL: 后台清理任务间隔(默认300秒)
        DBPOOL_MAX_CLEANUP_TIME: 单次清理最大时间(默认30秒)
        DBPOOL_MAX_CLEANUP_QUEUE_SIZE: 清理队列最大大小(默认100)
        DBPOOL_LEAK_WARNING_THRESHOLD: 泄漏警告阈值(默认80%)
        DBPOOL_LEAK_CRITICAL_THRESHOLD: 泄漏严重阈值(默认90%)
        DBPOOL_LEAK_EMERGENCY_THRESHOLD: 泄漏紧急阈值(默认95%)
        DBPOOL_LEAK_HISTORY_SIZE: 泄漏检测历史数据大小(默认100)
        DBPOOL_LEAK_ANALYSIS_WINDOW: 泄漏检测分析窗口(默认300秒)
        DBPOOL_ALERT_COOLDOWN: 告警冷却时间(默认300秒)
    
    Returns:
        PoolManagerConfig: 配置对象
    """
    return PoolManagerConfig(
        health_check_timeout=float(os.getenv("DBPOOL_HEALTH_CHECK_TIMEOUT", "10")),
        health_check_sql=os.getenv("DBPOOL_HEALTH_CHECK_SQL", "SELECT 1"),
        cleanup_interval=int(os.getenv("DBPOOL_CLEANUP_INTERVAL", "300")),
        max_cleanup_time=int(os.getenv("DBPOOL_MAX_CLEANUP_TIME", "30")),
        max_cleanup_queue_size=int(os.getenv("DBPOOL_MAX_CLEANUP_QUEUE_SIZE", "100")),
        leak_warning_threshold=int(os.getenv("DBPOOL_LEAK_WARNING_THRESHOLD", "80")),
        leak_critical_threshold=int(os.getenv("DBPOOL_LEAK_CRITICAL_THRESHOLD", "90")),
        leak_emergency_threshold=int(os.getenv("DBPOOL_LEAK_EMERGENCY_THRESHOLD", "95")),
        leak_history_size=int(os.getenv("DBPOOL_LEAK_HISTORY_SIZE", "100")),
        leak_analysis_window=int(os.getenv("DBPOOL_LEAK_ANALYSIS_WINDOW", "300")),
        state_lock_timeout=float(os.getenv("DBPOOL_STATE_LOCK_TIMEOUT", "10.0")),
        alert_cooldown=int(os.getenv("DBPOOL_ALERT_COOLDOWN", "300"))
    )


def is_enhanced_pool_enabled() -> bool:
    """
    检查是否启用增强的连接池管理
    
    Returns:
        bool: 是否启用
    """
    return os.getenv("DBPOOL_USE_ENHANCED", "true").lower() in ("true", "1", "yes")


_config_cache: Optional[PoolManagerConfig] = None


def get_cached_config() -> PoolManagerConfig:
    """
    获取缓存的配置对象(单例)
    
    Returns:
        PoolManagerConfig: 配置对象
    """
    global _config_cache
    if _config_cache is None:
        _config_cache = get_pool_config()
    return _config_cache


def clear_config_cache():
    """清除配置缓存"""
    global _config_cache
    _config_cache = None