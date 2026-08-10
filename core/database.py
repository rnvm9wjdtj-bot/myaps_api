"""
数据库配置和初始化管理
包含 Tortoise ORM 配置、连接池管理、初始化状态管理器
"""
import time
import asyncio
from collections import defaultdict
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from tortoise.contrib.fastapi import register_tortoise
from tortoise import Tortoise
from core.settings import (
    BASE_DIR, SQLITE_FILE, SQLITE_DB_PATH,
    MYAPS_MAIN_DB, MYAPS_DBSET_LIST, MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD,
    THIS_DB_NAME, THIS_DB_HOST, THIS_DB_PORT, THIS_DB_USER, THIS_DB_PASSWORD,
    TIMEZONE_NAME
)
from globalobjects import logger as log_config


# ============================================================================
# 数据库初始化状态管理器
# ============================================================================

class DatabaseInitManager:
    """
    数据库初始化状态管理器
    
    解决 Tortoise ORM 异步初始化的竞态条件
    
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


# ============================================================================
# 数据库连接配置
# ============================================================================

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
        "file_path": SQLITE_DB_PATH,  # 使用公共变量
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
            "models": ["apps.common.monitor.models"],
            "default_connection": SQLITE_FILE  # 使用SQLite数据库
        },
    },
}

if THIS_DB_NAME:
    model_path = "apps.data_opt.mds.staging_models"
    try:
        __import__(model_path)
        log_config.info(f"✅ 模型模块导入成功: {model_path}")
    except ImportError as e:
        log_config.error(f"❌ 模型模块导入失败: {model_path} - {e}")
        raise
    
    connections[THIS_DB_NAME] = {
        "engine": "tortoise.backends.asyncpg",
        "credentials": {
            "host": THIS_DB_HOST,
            "port": THIS_DB_PORT,
            "user": THIS_DB_USER,
            "password": THIS_DB_PASSWORD,
            "database": THIS_DB_NAME,
            "server_settings": {
                "TimeZone": TIMEZONE_NAME,
                "application_name": "myaps_api",
            },
            "command_timeout": 60,
            "timeout": 30,
        },
        "min_size": 3,
        "max_size": 10,
        "use_tz": True,
        "pool_recycle": 1800,
    }
    
    log_config.info(f"✅ PostgreSQL连接配置完成: {THIS_DB_NAME}@{THIS_DB_HOST}:{THIS_DB_PORT}")
    
    TORTOISE_ORM_CONFIG["apps"]["data_opt_models"] = {
        "models": [model_path],
        "default_connection": THIS_DB_NAME,
    }
    
    log_config.info(f"✅ 模型注册完成: data_opt_models -> {THIS_DB_NAME}")


def validate_database_config() -> Dict[str, Any]:
    """
    验证数据库配置完整性和一致性
    
    多租户场景说明：
    - THIS_DB_* 为空是正常情况，表示该租户不使用自有数据库
    - 仅当 THIS_DB_NAME 有值时，才验证配套参数的完整性
    
    Returns:
        配置摘要字典
    
    Raises:
        ValueError: 配置验证失败时抛出（仅在 THIS_DB_NAME 有值时）
    """
    import json
    import traceback
    
    try:
        issues = []
        warnings = []
        
        if not THIS_DB_NAME:
            log_config.info("ℹ️ 该租户未配置自有数据库(THIS_DB_NAME为空)，跳过 PostgreSQL 配置验证")
            config_summary = {
                "has_own_database": False,
                "timezone": TIMEZONE_NAME,
                "connections": list(connections.keys()),
                "apps": list(TORTOISE_ORM_CONFIG["apps"].keys()),
            }
            log_config.info(f"配置摘要: {json.dumps(config_summary, indent=2, ensure_ascii=False)}")
            return config_summary
        
        log_config.info(f"✓ 检测到自有数据库配置: THIS_DB_NAME={THIS_DB_NAME}")
        
        required_vars = {
            "THIS_DB_HOST": THIS_DB_HOST,
            "THIS_DB_PORT": THIS_DB_PORT,
            "THIS_DB_USER": THIS_DB_USER,
            "THIS_DB_PASSWORD": THIS_DB_PASSWORD,
        }
        
        for var_name, var_value in required_vars.items():
            if not var_value:
                issues.append(f"{var_name} 环境变量未设置")
        
        if THIS_DB_PORT and not (1 <= THIS_DB_PORT <= 65535):
            issues.append(f"THIS_DB_PORT={THIS_DB_PORT} 超出有效范围(1-65535)")
        
        if THIS_DB_NAME not in connections:
            issues.append(f"THIS_DB_NAME='{THIS_DB_NAME}' 未在connections配置中找到")
        
        try:
            __import__("apps.data_opt.mds.staging_models")
        except ImportError as e:
            warnings.append(f"模型路径导入警告: apps.data_opt.mds.staging_models - {e}")
        
        if issues:
            error_msg = "自有数据库配置验证失败:\n" + "\n".join(f"  ❌ {issue}" for issue in issues)
            log_config.error(error_msg)
            raise ValueError(error_msg)
        
        if warnings:
            for warning in warnings:
                log_config.warning(warning)
        
        config_summary = {
            "has_own_database": True,
            "db_name": THIS_DB_NAME,
            "db_host": THIS_DB_HOST,
            "db_port": THIS_DB_PORT,
            "timezone": TIMEZONE_NAME,
            "connections": list(connections.keys()),
            "apps": list(TORTOISE_ORM_CONFIG["apps"].keys()),
        }
        
        log_config.info("✅ 数据库配置验证通过")
        log_config.info(f"配置摘要: {json.dumps(config_summary, indent=2, ensure_ascii=False)}")
        
        return config_summary
        
    except ValueError:
        raise
    except Exception as e:
        log_config.error(f"❌ 数据库配置验证异常: {type(e).__name__}: {e}")
        log_config.error(f"堆栈追踪:\n{traceback.format_exc()}")
        raise


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
    """
    注册Tortoise ORM到FastAPI应用（兼容接口）
    
    注意：此函数作为兼容接口保留，实际初始化已移到 lifespan 中
    """
    
    log_config.info("🔹 开始注册数据库...")
    validate_database_config()
    
    # 标记初始化开始
    connection_names = list(TORTOISE_ORM_CONFIG['connections'].keys())
    db_init_manager.start_init(connection_names)
    
    register_tortoise(
        app=app,
        config=TORTOISE_ORM_CONFIG,
        generate_schemas=False,
        add_exception_handlers=True,
    )
    
    log_config.info("✅ Tortoise ORM 已注册到FastAPI应用")
    log_config.info(f"连接配置: {connection_names}")
    log_config.info(f"应用配置: {list(TORTOISE_ORM_CONFIG['apps'].keys())}")
    
    from apps.common.monitor.service import monitor_service
    log_config.info("✅ 系统监控服务已集成")


REQUIRED_SQLITE_TABLES = [
    "api_requests",
    "outbound_api_requests",
    "system_logs",
    "binlog_positions",
    "processed_events",
    "failed_operations",
    "schema_version",
]


async def ensure_sqlite_monitor_tables() -> bool:
    """
    确保 SQLite 监控模块表存在

    在启动时检查必需的表是否存在于 SQLite 数据库中，
    如果不存在则执行迁移脚本创建表。

    Returns:
        bool: 所有表都存在或创建成功返回 True
    """
    import sqlite3

    db_path = SQLITE_DB_PATH

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing_tables = [table for table in REQUIRED_SQLITE_TABLES if table not in existing_tables]

        if not missing_tables:
            log_config.debug("✅ SQLite 监控表检查通过，所有表已存在")
            conn.close()
            return True

        log_config.warning(f"⚠️ SQLite 监控表缺失: {missing_tables}")

        migration_script = BASE_DIR / "scripts" / "migrate" / "monitor" / "monitor_tables.sql"
        if migration_script.exists():
            log_config.info(f"📦 正在执行数据库迁移脚本: {migration_script}")

            with open(migration_script, 'r', encoding='utf-8') as f:
                sql_content = f.read()

            cursor.executescript(sql_content)
            conn.commit()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            created_tables = {row[0] for row in cursor.fetchall()}

            still_missing = [table for table in REQUIRED_SQLITE_TABLES if table not in created_tables]
            if still_missing:
                log_config.error(f"❌ 迁移后仍有表缺失: {still_missing}")
                conn.close()
                return False

            log_config.info("✅ SQLite 监控表迁移完成")
            conn.close()
            return True
        else:
            log_config.error(f"❌ 迁移脚本不存在: {migration_script}")
            conn.close()
            return False

    except Exception as e:
        log_config.error(f"❌ SQLite 监控表初始化失败: {e}")
        try:
            if 'conn' in locals():
                conn.close()
        except Exception:
            pass
        return False


async def warmup_connections():
    """
    预热数据库连接，增强容错处理
    MySQL 连接失败不阻止应用启动
    """
    if not MYAPS_MAIN_DB:
        return
    try:
        from globalobjects.db_manager import get_db_managers
        db_managers = get_db_managers()
        for db_name, manager in db_managers.items():
            conn_config = TORTOISE_ORM_CONFIG["connections"].get(db_name, {})
            engine = conn_config.get("engine", "")
            is_mysql = "mysql" in engine
            
            try:
                start_time = time.time()
                # 注意：首次连接的 MySQL 握手可能耗时 5 秒以上（服务端未开 skip-name-resolve 时），
                # 此处的 timeout 必须大于握手耗时，否则预热会一直超时退化为 fallback 路径。
                # fast_mode 下最坏耗时链为 健康检查(10s) + 刷新(0.5s + 内部健康检查10s) + 复查(10s) ≈ 30.5s，
                # 故外层超时需覆盖完整链路，否则"刷新后复查"回退分支会被截断。
                is_healthy = await asyncio.wait_for(
                    manager.check_connection_health(timeout=10, fast_mode=True),
                    timeout=35
                )
                response_time = time.time() - start_time
                if is_healthy:
                    log_config.info(f"连接预热成功: {db_name} - 响应时间: {response_time:.3f}秒")
                else:
                    if is_mysql:
                        log_config.warning(f"⚠️ MySQL连接预热失败: {db_name}（不影响启动）")
                    else:
                        log_config.warning(f"连接预热失败: {db_name}")
                        await asyncio.wait_for(
                            manager.refresh_connection(fast_mode=True),
                            timeout=15
                        )
            except asyncio.TimeoutError:
                if is_mysql:
                    log_config.warning(f"⚠️ MySQL连接预热超时: {db_name}，跳过（不影响启动）")
                else:
                    log_config.warning(f"连接预热超时: {db_name}，跳过预热")
            except Exception as e:
                if is_mysql:
                    log_config.warning(f"⚠️ MySQL连接预热异常: {db_name} - {str(e)}（不影响启动）")
                else:
                    log_config.error(f"❌ 连接预热异常: {db_name} - {str(e)}")
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
    """启动连接池监控任务（使用增强的连接池管理）"""
    import os
    from core.settings import MYAPS_DBSET_LIST
    
    # 检查是否启用增强连接池管理
    use_enhanced_pool = os.getenv("USE_ENHANCED_POOL", "true").lower() == "true"
    
    if use_enhanced_pool:
        try:
            from globalobjects.db_pool import start_pool_monitoring as start_enhanced_monitoring
            
            # 获取要监控的连接名称列表
            connection_names = MYAPS_DBSET_LIST if MYAPS_DBSET_LIST else []
            
            log_config.info(f"启动增强连接池监控，监控连接: {connection_names}")
            
            # 启动增强监控
            await start_enhanced_monitoring(connection_names)
            
        except Exception as e:
            log_config.error(f"增强连接池监控启动失败: {e}，使用原有监控")
            # 回退到原有监控
            while True:
                try:
                    await asyncio.wait_for(smart_pool_manager.monitor_and_adjust(), timeout=60)
                except asyncio.TimeoutError:
                    log_config.warning("连接池监控任务执行超时")
                except Exception as e:
                    log_config.error(f"连接池监控任务异常: {e}")
                await asyncio.sleep(300)
    else:
        # 使用原有监控
        log_config.info("使用原有连接池监控")
        while True:
            try:
                await asyncio.wait_for(smart_pool_manager.monitor_and_adjust(), timeout=60)
            except asyncio.TimeoutError:
                log_config.warning("连接池监控任务执行超时")
            except Exception as e:
                log_config.error(f"连接池监控任务异常: {e}")
            await asyncio.sleep(300)


async def get_db_connection_safely(db_name: Optional[str] = None, max_wait: float = 15.0):
    """
    安全获取数据库连接，包含异常处理和友好提示
    
    Args:
        db_name: 数据库连接名称，默认使用THIS_DB_NAME
        max_wait: 最大等待时间（秒），用于等待ORM初始化
    
    Returns:
        数据库连接对象
    
    Raises:
        HTTPException: 数据库连接失败时返回500错误
    """
    from fastapi import HTTPException
    from core.settings import THIS_DB_NAME
    
    if db_name is None:
        db_name = THIS_DB_NAME
    
    try:
        if not Tortoise._inited:
            log_config.info(f"⏳ 等待数据库初始化完成: {db_name}")
            result = await db_init_manager.wait_for_init(max_wait=max_wait)
            
            if not result["success"]:
                error_msg = f"数据库初始化失败({result['elapsed']:.1f}秒)"
                log_config.error(f"❌ {error_msg}: {result.get('error')}")
                raise HTTPException(
                    status_code=500,
                    detail=f"数据库服务初始化失败，请稍后重试"
                )
            
            log_config.info(f"✅ 数据库就绪，获取连接: {db_name}")
        
        conn = Tortoise.get_connection(db_name)
        return conn
        
    except KeyError:
        log_config.error(f"❌ 数据库连接不存在: {db_name}")
        raise HTTPException(
            status_code=500,
            detail="数据库连接配置错误，请联系管理员"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        log_config.error(f"❌ 获取数据库连接异常: {db_name} - {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail="数据库连接失败，请检查服务配置或稍后重试"
        )

