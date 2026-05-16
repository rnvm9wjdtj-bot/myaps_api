import time
import asyncio
from collections import defaultdict
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from tortoise.contrib.fastapi import register_tortoise
from core.settings import (
    BASE_DIR, SQLITE_FILE,
    MYAPS_MAIN_DB, MYAPS_DBSET_LIST, MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD,
    THIS_DB_NAME, THIS_DB_HOST, THIS_DB_PORT, THIS_DB_USER, THIS_DB_PASSWORD,
    TIMEZONE_NAME
)
from globalobjects import logger as log_config

# 计算连接池大小：根据账套数量动态调整，避免连接总数过多
# 总连接数 = 账套数 × maxsize，应控制在合理范围内（建议不超过150）
import os
cpu_count = os.cpu_count() or 4
db_count = len(MYAPS_DBSET_LIST)

# 动态计算连接池大小：
# - 单账套：maxsize=20
# - 多账套：根据账套数量递减，最小为5
# - 确保总连接数不超过 50（优化后的限制）
maxsize_per_db = min(20, max(5, 50 // max(db_count, 1)))
minsize_per_db = min(5, maxsize_per_db // 2)


# 数据库配置
connections = {}
# 为每个账套创建MySQL连接配置
for db in MYAPS_DBSET_LIST:
    connections[db] = {
        "engine": "tortoise.backends.mysql",
        "credentials": {
            "host": MYAPS_DB_HOST,
            "port": MYAPS_DB_PORT,
            "user": MYAPS_DB_USER,
            "password": MYAPS_DB_PASSWORD,
            "database": db,
            "charset": "utf8mb4",
            "connect_timeout": 30,
            "ssl": None,
            "echo": False,
        },
        "maxsize": maxsize_per_db,  # 最大连接数
        "minsize": minsize_per_db,  # 最小连接数
        "pool_recycle": 3600,  # 连接回收时间（秒）
    }

# 添加SQLite数据库连接配置
connections[SQLITE_FILE] = {
    "engine": "tortoise.backends.sqlite",
    "credentials": {
        "file_path": BASE_DIR / "storage" / f"{SQLITE_FILE}.sqlite3",  # 统一管理数据文件
        "journal_mode": "WAL",  # 写前日志，提升并发性能
        "synchronous": "NORMAL",  # 性能与安全的平衡
        "cache_size": -100000,  # 100MB 内存缓存
        "foreign_keys": True,  # 启用外键约束
        "timeout": 30,  # 连接超时时间
        "check_same_thread": False,
    },
    "maxsize": 5,  # 最大连接数
    "minsize": 1,  # 最小连接数
}

# 添加 default 连接别名（用于 Aerich 迁移）
if MYAPS_MAIN_DB and MYAPS_MAIN_DB in connections:
    connections['default'] = connections[MYAPS_MAIN_DB]
elif SQLITE_FILE in connections:
    # 如果主数据库不存在，使用 SQLite 作为 default
    connections['default'] = connections[SQLITE_FILE]

TORTOISE_ORM_CONFIG = {
    "connections": connections,
    "apps": {
        "io_api_models": {
            "models": ["apps.io_api.models",],
            "default_connection": MYAPS_MAIN_DB  # 使用MyAPS账套
        },
        "monitor_models": {
            "models": ["apps.common.monitor.models", "aerich.models"],
            "default_connection": SQLITE_FILE  # 使用SQLite数据库
        },
    },
}

if THIS_DB_NAME:
    connections[THIS_DB_NAME] = {
        "engine": "tortoise.backends.asyncpg",
        "credentials": {
            "host": THIS_DB_HOST,
            "port": THIS_DB_PORT,
            "user": THIS_DB_USER,
            "password": THIS_DB_PASSWORD,
            "database": THIS_DB_NAME,
            "server_settings": {"TimeZone": TIMEZONE_NAME},
        },
        "min_size": 3,
        "max_size": 10,
        "use_tz": False,
    }
    TORTOISE_ORM_CONFIG["apps"]["data_opt_models"] = {
        "models": ["apps.data_opt.mds.staging_models", "aerich.models"],
        "default_connection": THIS_DB_NAME,
    }


class ConnectionLeakDetector:
    """连接泄漏检测器"""
    
    def __init__(self, warning_threshold: int = 80, critical_threshold: int = 95):
        """
        初始化连接泄漏检测器
        
        Args:
            warning_threshold: 使用率警告阈值（百分比）
            critical_threshold: 使用率危险阈值（百分比）
        """
        self._warning_threshold = warning_threshold
        self._critical_threshold = critical_threshold
        self._connection_history = defaultdict(list)
        self._max_history_size = 100
        
    def record_connection_usage(self, db_name: str, pool_status: Dict[str, Any]):
        """记录连接使用情况"""
        current_time = time.time()
        
        # 计算使用率
        used = pool_status.get('used_connections', 0)
        max_size = pool_status.get('max_size', 1)
        utilization = (used / max_size * 100) if max_size > 0 else 0
        
        self._connection_history[db_name].append({
            'timestamp': current_time,
            'utilization': utilization,
            'used': used,
            'max_size': max_size
        })
        
        # 限制历史记录大小
        if len(self._connection_history[db_name]) > self._max_history_size:
            self._connection_history[db_name] = self._connection_history[db_name][-self._max_history_size:]
        
        return utilization
    
    def detect_leak(self, db_name: str) -> Dict[str, Any]:
        """检测连接泄漏"""
        history = self._connection_history.get(db_name, [])
        
        if len(history) < 10:  # 需要足够的历史数据
            return {'leak_detected': False, 'reason': 'insufficient_data'}
        
        # 获取最近1分钟的数据
        recent_time = time.time() - 60
        recent_data = [h for h in history if h['timestamp'] >= recent_time]
        
        if len(recent_data) < 5:
            return {'leak_detected': False, 'reason': 'no_recent_data'}
        
        # 计算平均使用率
        avg_utilization = sum(h['utilization'] for h in recent_data) / len(recent_data)
        max_utilization = max(h['utilization'] for h in recent_data)
        
        # 检测条件：
        # 1. 平均使用率超过警告阈值
        # 2. 使用率持续高位（超过80%的数据点超过警告阈值）
        high_usage_count = sum(1 for h in recent_data if h['utilization'] > self._warning_threshold)
        high_usage_ratio = high_usage_count / len(recent_data)
        
        leak_detected = (
            avg_utilization > self._warning_threshold or 
            (high_usage_ratio > 0.8 and max_utilization > self._critical_threshold)
        )
        
        return {
            'leak_detected': leak_detected,
            'avg_utilization': avg_utilization,
            'max_utilization': max_utilization,
            'high_usage_ratio': high_usage_ratio,
            'current_used': recent_data[-1]['used'] if recent_data else 0,
            'current_max': recent_data[-1]['max_size'] if recent_data else 0,
            'warning_threshold': self._warning_threshold,
            'critical_threshold': self._critical_threshold
        }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有数据库的统计信息"""
        stats = {}
        for db_name in self._connection_history.keys():
            stats[db_name] = self.detect_leak(db_name)
        return stats


class SmartConnectionPoolManager:
    """智能连接池管理器"""
    
    def __init__(self):
        self._pool_stats = defaultdict(dict)
        self._last_adjust_time = defaultdict(float)
        self._adjust_interval = 300  # 调整间隔（秒）
        self._min_pool_size = 5  # 最小连接池大小
        self._max_pool_size = 50  # 最大连接池大小
        self._target_utilization = 0.7  # 目标利用率
        self._scale_up_threshold = 0.8  # 扩容阈值
        self._scale_down_threshold = 0.3  # 缩容阈值
        self._scale_step = 2  # 每次调整步长
        self._leak_detector = ConnectionLeakDetector()
        
    async def monitor_and_adjust(self):
        """监控并调整连接池大小，包含泄漏检测"""
        if not MYAPS_MAIN_DB:
            return
        
        try:
            from globalobjects.db_manager import get_db_managers
            db_managers = get_db_managers()
            
            for db_name, manager in db_managers.items():
                try:
                    # 获取连接池状态
                    pool_status = await manager.get_connection_pool_status()
                    current_time = time.time()
                    
                    # 计算使用率
                    utilization = self._calculate_utilization(pool_status)
                    
                    # 记录统计数据
                    self._record_stats(db_name, pool_status, utilization)
                    
                    # 记录连接使用历史（用于泄漏检测）
                    self._leak_detector.record_connection_usage(db_name, pool_status)
                    
                    # 检测连接泄漏
                    leak_info = self._leak_detector.detect_leak(db_name)
                    if leak_info.get('leak_detected'):
                        log_config.warning(
                            f"⚠️ 检测到可能的连接泄漏: {db_name} - "
                            f"平均使用率: {leak_info['avg_utilization']:.1f}%, "
                            f"最大使用率: {leak_info['max_utilization']:.1f}%, "
                            f"当前使用: {leak_info['current_used']}/{leak_info['current_max']}"
                        )
                        # 尝试刷新连接
                        try:
                            await manager.refresh_connection(fast_mode=True)
                            log_config.info(f"✅ 已尝试刷新连接: {db_name}")
                        except Exception as refresh_error:
                            log_config.error(f"❌ 刷新连接失败: {db_name} - {refresh_error}")
                    
                    # 检查是否需要调整
                    time_since_last_adjust = current_time - self._last_adjust_time.get(db_name, 0)
                    if time_since_last_adjust >= self._adjust_interval:
                        await self._adjust_pool_size(db_name, manager, pool_status, utilization)
                        self._last_adjust_time[db_name] = current_time
                        
                except Exception as e:
                    log_config.error(f"监控连接池异常: {db_name} - {str(e)}")
                    
        except Exception as e:
            log_config.error(f"智能连接池管理异常: {str(e)}")
    
    def _calculate_utilization(self, pool_status: Dict[str, Any]) -> float:
        """计算连接池使用率"""
        if not pool_status.get('pool_available', False):
            return 0.0
        
        used = pool_status.get('used_connections', 0)
        total = pool_status.get('current_size', 1)
        
        return used / total if total > 0 else 0.0
    
    def _record_stats(self, db_name: str, pool_status: Dict[str, Any], utilization: float):
        """记录连接池统计数据"""
        self._pool_stats[db_name] = {
            'timestamp': time.time(),
            'utilization': utilization,
            'pool_status': pool_status
        }
    
    async def _adjust_pool_size(self, db_name: str, manager: Any, pool_status: Dict[str, Any], utilization: float):
        """调整连接池大小"""
        if not pool_status.get('pool_available', False):
            return
        
        current_size = pool_status.get('current_size', self._min_pool_size)
        max_size = pool_status.get('max_size', self._max_pool_size)
        
        # 扩容逻辑
        if utilization > self._scale_up_threshold and current_size < max_size:
            new_size = min(current_size + self._scale_step, max_size)
            log_config.info(f"连接池扩容: {db_name} 从 {current_size} 到 {new_size}, 使用率: {utilization:.2f}")
            # 注意：Tortoise ORM的连接池大小通常在配置时固定，这里记录需要调整的信息
        
        # 缩容逻辑
        elif utilization < self._scale_down_threshold and current_size > self._min_pool_size:
            new_size = max(current_size - self._scale_step, self._min_pool_size)
            log_config.info(f"连接池缩容: {db_name} 从 {current_size} 到 {new_size}, 使用率: {utilization:.2f}")
            # 同样，实际调整可能需要重启服务
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计数据"""
        return dict(self._pool_stats)


# 全局智能连接池管理器实例
smart_pool_manager = SmartConnectionPoolManager()


def register_database(app):
    register_tortoise(
        app=app,
        config=TORTOISE_ORM_CONFIG,
    )
    
    # 标记数据库已初始化，允许日志写入数据库
    from globalobjects.logger import get_logger
    logger = get_logger("database")
    logger.set_db_initialized_all(True)
    
    # 启动监控服务（使用现有的监控架构）
    from apps.common.monitor.service import monitor_service
    log_config.info("✅ 系统监控服务已集成")


async def warmup_connections():
    """预热数据库连接"""
    if not MYAPS_MAIN_DB:
        return
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            try:
                start_time = time.time()
                # 使用较短的超时时间，避免启动时被阻塞
                is_healthy = await asyncio.wait_for(
                    manager.check_connection_health(timeout=5, fast_mode=True),
                    timeout=10
                )
                response_time = time.time() - start_time
                if is_healthy:
                    log_config.info(f"连接预热成功: {db_name} - 响应时间: {response_time:.3f}秒")
                else:
                    log_config.warning(f"连接预热失败: {db_name}")
                    # 尝试刷新连接（使用快速模式）
                    await asyncio.wait_for(
                        manager.refresh_connection(fast_mode=True),
                        timeout=15
                    )
            except asyncio.TimeoutError:
                log_config.warning(f"连接预热超时: {db_name}，跳过预热")
            except Exception as e:
                log_config.error(f"连接预热异常: {db_name} - {str(e)}")
        log_config.info("数据库连接预热完成")
    except Exception as e:
        log_config.error(f"连接预热异常: {str(e)}")


async def check_db_connections():
    """定期检查数据库连接状态"""
    if not MYAPS_MAIN_DB:
        return
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            try:
                # 检查连接健康状态（添加超时控制）
                start_time = time.time()
                is_healthy = await asyncio.wait_for(
                    manager.check_connection_health(timeout=3, fast_mode=True),
                    timeout=8
                )
                response_time = time.time() - start_time
                
                # 记录响应时间，超过1秒时预警
                if response_time > 1.0:
                    log_config.warning(f"数据库连接响应缓慢: {db_name} - {response_time:.3f}秒")
                
                if not is_healthy:
                    log_config.warning(f"数据库连接 {db_name} 不健康，尝试刷新连接")
                    await asyncio.wait_for(
                        manager.refresh_connection(fast_mode=True),
                        timeout=10
                    )
                # 获取连接池状态
                pool_status = await manager.get_connection_pool_status()
                log_config.debug(f"连接池状态 - {db_name}: {pool_status}")
            except asyncio.TimeoutError:
                log_config.warning(f"数据库连接检查超时: {db_name}")
            except Exception as e:
                log_config.error(f"检查数据库连接异常: {db_name} - {str(e)}")
        
        # 运行智能连接池管理（添加超时控制）
        await asyncio.wait_for(smart_pool_manager.monitor_and_adjust(), timeout=30)
        
        log_config.debug("数据库连接检查完成")
    except asyncio.TimeoutError:
        log_config.warning("数据库连接检查超时")
    except Exception as e:
        log_config.error(f"数据库连接检查异常: {e}")


async def start_pool_monitoring():
    """启动连接池监控任务"""
    while True:
        try:
            # 添加超时控制，避免任务阻塞
            await asyncio.wait_for(smart_pool_manager.monitor_and_adjust(), timeout=60)
        except asyncio.TimeoutError:
            log_config.warning("连接池监控任务执行超时")
        except Exception as e:
            log_config.error(f"连接池监控任务异常: {e}")
        # 每5分钟执行一次
        await asyncio.sleep(300)

