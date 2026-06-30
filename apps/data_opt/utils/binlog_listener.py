"""
MySQL Binlog 实时监控模块

功能特性：
1. 实时监听 MySQL Binlog，捕获 INSERT/UPDATE/DELETE 事件
2. 无限重试机制 - 连接断开后自动重连，永不放弃
3. 位置持久化 - 自动保存 Binlog 位置，重启后从断点续传
4. 健康检查 - 定期检查 MySQL 连接状态
5. 告警通知 - 支持自定义告警回调（企业微信、钉钉、邮件等）

需要的 MySQL 权限：
-- 创建监控用户并授权
CREATE USER 'monitor_user'@'%' IDENTIFIED BY 'strong_password';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'monitor_user'@'%';
GRANT SELECT ON your_database.* TO 'monitor_user'@'%';
FLUSH PRIVILEGES;

-- 检查MySQL配置
SHOW VARIABLES LIKE 'log_bin';  -- 必须为ON
SHOW VARIABLES LIKE 'binlog_format';  -- 推荐ROW模式

验证方法：
1. 登录 MySQL 执行：SHOW VARIABLES LIKE 'log_bin'; 结果需为 ON
2. 执行：SHOW VARIABLES LIKE 'binlog_format'; 结果需为 ROW
3. 若未开启，需在 my.cnf 中设置：
   [mysqld]
   log_bin=mysql-bin
   binlog_format=ROW
   server_id=1
4. 重启 MySQL 使配置生效

使用示例：
    from apps.data_opt.utils.binlog_listener import binlog_listener
    
    # 注册告警处理器（可选）
    def alert_handler(message, level):
        # 发送到企业微信/钉钉/邮件等
        print(f"[{level}] {message}")
    
    binlog_listener.register_alert_handler(alert_handler)
    
    # 启动监控
    binlog_listener.start_monitoring()
    
    # 查看状态
    status = binlog_listener.get_status()
    print(status)
    
    # 停止监控
    binlog_listener.stop_monitoring()
"""


import os, asyncio, time, logging, threading, concurrent.futures, json, pickle, pymysql, uuid, random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import (
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)

from core.settings import MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD, MYAPS_MAIN_DB, MYAPS_DBSET_LIST, TURNON_BINLOG_LISTENER, ENABLE_BINLOG_POSITION, BASE_DIR

from globalobjects import logger as log_config
from globalobjects.reminder import remind_manager, RemindType

from apps.common.utils.thread_pool_manager import global_pool_manager

# ========== Simplified HA Module Integration ==========
try:
    from apps.data_opt.utils.binlog_ha import (
        prometheus_metrics,
        backpressure_controller,
        event_deduplicator,
        retry_policy,
    )
    HA_MODULES_AVAILABLE = True
except ImportError as e:
    log_config.get_logger(__name__).warning(f"⚠️ 简化版HA模块导入失败: {e}，使用基础功能")
    HA_MODULES_AVAILABLE = False

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


def _get_binlog_db_credentials(action_name: str) -> Optional[Dict[str, Any]]:
    """获取用于 Binlog 高权限操作的数据库连接信息。"""
    db_user = MYAPS_DB_USER
    db_password = MYAPS_DB_PASSWORD
    if not db_user:
        logger.error(
            f"{action_name}失败: 未配置 MYAPS_DB_USER。"
            "请在 .env 或项目配置中显式提供该变量。"
        )
        return None

    if not db_password:
        logger.error(
            f"{action_name}失败: 未配置 MYAPS_DB_PASSWORD。"
            "请在 .env 或项目配置中显式提供该变量。"
        )
        return None

    return {
        "host": MYAPS_DB_HOST,
        "port": MYAPS_DB_PORT,
        "user": db_user,
        "password": db_password,
    }


class BinlogPositionManager:
    """Binlog 位置管理器 - 负责持久化和恢复 Binlog 位置（基于文件存储）"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._last_save_time = 0
        self._save_interval = 5  # 最少5秒保存一次，避免频繁写入
        self._server_id = "default"  # 默认服务器标识
        self._position_file = os.path.join(str(BASE_DIR), "storage", "binlog_position.json")
        self._processed_events_file = os.path.join(str(BASE_DIR), "storage", "processed_events.json")
        self._dir_checked = False  # 仅首次写入时检查目录存在性
    
    def _read_json_file(self, file_path):
        """读取 JSON 文件"""
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ 读取文件 {file_path} 失败: {e}")
            return {}
    
    def _write_json_file(self, file_path, data):
        """写入 JSON 文件（原子操作）
        
        使用临时文件 + os.replace() 确保写入原子性：
        1. 先写入临时文件
        2. 原子替换目标文件
        3. 失败时清理临时文件
        
        这样可以防止写入过程中断导致文件损坏
        """
        temp_path = f"{file_path}.tmp"
        try:
            # 首次写入时确保目标目录存在（Docker overlay2 下 rename 可能对挂载点敏感）
            if not self._dir_checked:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                self._dir_checked = True
            
            # 先写入临时文件
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 原子替换（os.replace 在 POSIX 系统上是原子操作）
            os.replace(temp_path, file_path)
            return True
        except Exception as e:
            logger.error(f"❌ 写入文件 {file_path} 失败: {e}")
            # 清理临时文件
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except:
                pass
            return False
    
    def load_position(self) -> Optional[Dict[str, Any]]:
        """加载保存的 Binlog 位置"""
        try:
            data = self._read_json_file(self._position_file)
            position = data.get(self._server_id)
            if position and position.get('log_file'):
                logger.info(f"📂 已加载 Binlog 位置: {position['log_file']}:{position['log_pos']}")
                return position
        except Exception as e:
            logger.warning(f"⚠️ 加载 Binlog 位置失败: {e}")
        return None
    
    def save_position(self, log_file: str, log_pos: int, timestamp: Optional[float] = None):
        """保存 Binlog 位置到文件"""
        current_time = time.time()
        
        # 限制保存频率
        if current_time - self._last_save_time < self._save_interval:
            return
        
        try:
            data = self._read_json_file(self._position_file)
            data[self._server_id] = {
                'log_file': log_file,
                'log_pos': log_pos,
                'timestamp': timestamp or current_time
            }
            if self._write_json_file(self._position_file, data):
                self._last_save_time = current_time
                logger.debug(f"💾 Binlog 位置已保存: {log_file}:{log_pos}")
        except Exception as e:
            logger.error(f"❌ 保存 Binlog 位置失败: {e}")
    
    def clear_position(self):
        """清除保存的位置（通常在手动重置时使用）"""
        try:
            data = self._read_json_file(self._position_file)
            if self._server_id in data:
                del data[self._server_id]
                self._write_json_file(self._position_file, data)
                logger.info("🗑️ Binlog 位置已清除")
        except Exception as e:
            logger.warning(f"⚠️ 清除 Binlog 位置失败: {e}")
    
    def is_event_processed(self, event_id: str) -> bool:
        """检查事件是否已处理"""
        try:
            data = self._read_json_file(self._processed_events_file)
            return event_id in data
        except Exception as e:
            logger.warning(f"⚠️ 检查 binlog监听 事件是否已处理失败: {e}")
            return False
    
    def mark_event_processed(self, event_id: str, log_file: str, log_pos: int, event_type: str, table_name: str, database_name: str):
        """标记事件为已处理"""
        try:
            data = self._read_json_file(self._processed_events_file)
            data[event_id] = {
                "log_file": log_file,
                "log_pos": log_pos,
                "event_type": event_type,
                "table_name": table_name,
                "database_name": database_name,
                "processed_at": datetime.now().isoformat()
            }
            self._write_json_file(self._processed_events_file, data)
        except Exception as e:
            logger.warning(f"⚠️ 标记 binlog监听 事件为已处理失败: {e}")
    
    def cleanup_old_events(self, days: int = 7):
        """清理旧的已处理事件记录"""
        try:
            data = self._read_json_file(self._processed_events_file)
            cutoff = datetime.now() - timedelta(days=days)
            to_delete = []
            
            for event_id, event_data in data.items():
                processed_at = event_data.get('processed_at')
                if processed_at:
                    try:
                        processed_time = datetime.fromisoformat(processed_at)
                        if processed_time < cutoff:
                            to_delete.append(event_id)
                    except:
                        pass
            
            for event_id in to_delete:
                del data[event_id]
            
            if to_delete:
                self._write_json_file(self._processed_events_file, data)
                logger.info(f"🗑️ 已清理 {len(to_delete)} 条旧的已处理事件记录")
        except Exception as e:
            logger.warning(f"⚠️ 清理旧的已处理 binlog监听 事件记录失败: {e}")


class ConnectionHealthChecker:
    """连接健康检查器 - 定期检查 MySQL 连接状态"""
    
    def __init__(self, mysql_settings: Dict[str, Any], check_interval: int = 30):
        self.mysql_settings = mysql_settings
        self.check_interval = check_interval  # 检查间隔（秒）
        self._is_healthy = True
        self._is_config_valid = True
        self._last_check_time = 0
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._check_thread: Optional[threading.Thread] = None
        self._alert_callbacks: list = []
    
    def register_alert_callback(self, callback: Callable):
        """注册告警回调函数"""
        self._alert_callbacks.append(callback)
    
    def _send_alert(self, message: str, level: str = "warning"):
        """发送告警通知"""
        for callback in self._alert_callbacks:
            try:
                callback(message, level)
            except Exception as e:
                logger.error(f"告警发送失败: {e}")
    
    def is_healthy(self) -> bool:
        """获取当前健康状态"""
        with self._lock:
            return self._is_healthy and self._is_config_valid
    
    def check_connection(self) -> bool:
        """执行一次连接检查"""
        try:
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "connect_timeout": 5
            }
            
            conn = pymysql.connect(**conn_params)
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            conn.close()
            
            with self._lock:
                if not self._is_healthy:
                    self._is_healthy = True
                    logger.success("健康检查", "MySQL", "连接已恢复")
                    self._send_alert("MySQL 连接已恢复", "info")
            
            return True
            
        except Exception as e:
            with self._lock:
                if self._is_healthy:
                    self._is_healthy = False
                    logger.warning(f"⚠️ 健康检查失败: {e}")
                    self._send_alert(f"MySQL 连接健康检查失败: {e}", "warning")
            return False
    
    def check_config(self) -> bool:
        """执行一次配置检查"""
        # 如果未启用数据库监控，跳过配置检查
        if not TURNON_BINLOG_LISTENER:
            with self._lock:
                # 未启用监控时，将配置状态设置为有效
                self._is_config_valid = True
            return True
        
        try:
            # 调用配置验证函数
            is_valid = is_mysql_config_valid()
            
            # 如果配置无效，尝试自动修正
            if not is_valid:
                logger.info("🔧 配置无效，尝试自动修正...")
                try:
                    set_binlog_params()
                    logger.success("配置修正", "MySQL", "已尝试自动修正配置")
                    # 修正后再次检查
                    is_valid = is_mysql_config_valid()
                except Exception as fix_error:
                    logger.error("配置修正", f"自动修正失败: {fix_error}")
            
            with self._lock:
                if not self._is_config_valid and is_valid:
                    self._is_config_valid = True
                    logger.success("健康检查", "MySQL", "配置已恢复")
                    self._send_alert("MySQL 配置已恢复", "info")
                elif self._is_config_valid and not is_valid:
                    self._is_config_valid = False
                    logger.warning("⚠️ 配置检查失败: MySQL 配置不符合要求")
                    self._send_alert("MySQL 配置检查失败，请检查 Binlog 配置", "warning")
            
            return is_valid
            
        except Exception as e:
            with self._lock:
                if self._is_config_valid:
                    self._is_config_valid = False
                    logger.warning(f"⚠️ 配置检查失败: {e}")
                    self._send_alert(f"MySQL 配置检查失败: {e}", "warning")
            return False
    
    def start(self):
        """启动健康检查线程"""
        if self._check_thread is None or not self._check_thread.is_alive():
            self._stop_event.clear()
            self._check_thread = threading.Thread(
                target=self._check_loop,
                daemon=True,
                name='mysql-health-checker'
            )
            self._check_thread.start()
            logger.info("✅ MySQL 健康检查线程已启动")
    
    def stop(self):
        """停止健康检查线程"""
        self._stop_event.set()
        if self._check_thread and self._check_thread.is_alive():
            self._check_thread.join(timeout=5)
            logger.info("🛑 MySQL 健康检查线程已停止")
    
    def _check_loop(self):
        """健康检查循环"""
        while not self._stop_event.is_set():
            self.check_connection()
            # self.check_config()
            # 使用事件等待，支持快速退出
            self._stop_event.wait(self.check_interval)


class _EventLoopHealthChecker:
    """事件循环健康检查器 - 定期检查事件循环状态"""
    
    def __init__(self, listener, check_interval: int = 30):
        self._listener = listener
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._check_thread = None
        self._last_loop_check_time = 0
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3
        self._is_healthy = True
    
    def start(self):
        """启动事件循环健康检查器"""
        if self._check_thread is not None and self._check_thread.is_alive():
            return
        self._stop_event.clear()
        self._check_thread = threading.Thread(
            target=self._check_loop,
            daemon=True,
            name='event-loop-health-checker'
        )
        self._check_thread.start()
        logger.info("✅ 事件循环健康检查器已启动")
    
    def stop(self):
        """停止事件循环健康检查器"""
        self._stop_event.set()
        if self._check_thread:
            self._check_thread.join(timeout=5)
        logger.info("🛑 事件循环健康检查器已停止")
    
    def is_healthy(self) -> bool:
        """获取事件循环健康状态"""
        return self._is_healthy
    
    def _check_loop(self):
        """健康检查主循环"""
        while not self._stop_event.is_set():
            self._do_check()
            self._stop_event.wait(self._check_interval)
    
    def _do_check(self):
        """执行健康检查"""
        try:
            event_loop = getattr(self._listener, '_event_loop', None)
            if event_loop is None:
                logger.debug("⚠️ 事件循环未初始化")
                self._consecutive_failures += 1
                return
            
            # 检查事件循环是否还在运行
            if not event_loop.is_running():
                logger.error("❌ 事件循环已停止运行")
                self._is_healthy = False
                self._consecutive_failures += 1
                if self._consecutive_failures >= self._max_consecutive_failures:
                    # 通过健康检查器发送告警
                    if hasattr(self._listener, '_health_checker'):
                        self._listener._health_checker._send_alert(
                            f"binlog监听事件循环已停止运行，已连续失败 {self._consecutive_failures} 次",
                            "error"
                        )
                return
            
            # 检查pending任务数（Python 3.7+）
            try:
                pending_count = len(asyncio.all_tasks(event_loop))
                logger.debug(f"事件循环当前pending任务数: {pending_count}")
                
                # 如果pending任务过多，发出警告
                if pending_count > 1000:
                    logger.warning(f"⚠️ 事件循环pending任务过多: {pending_count}")
                    self._is_healthy = False
                    if hasattr(self._listener, '_health_checker'):
                        self._listener._health_checker._send_alert(
                            f"binlog监听事件循环pending任务过多: {pending_count}",
                            "warning"
                        )
                else:
                    self._is_healthy = True
                
                self._consecutive_failures = 0  # 成功后重置
                self._last_loop_check_time = time.time()
            except Exception as e:
                logger.warning(f"⚠️ 事件循环状态检查失败: {e}")
                self._consecutive_failures += 1
                
        except Exception as e:
            logger.error(f"❌ 事件循环健康检查异常: {e}")
            self._is_healthy = False
            self._consecutive_failures += 1


class MySQLBinlogListener:
    # 单例模式实现
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls, mysql_settings=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, mysql_settings=None):
        # 确保初始化只执行一次
        with self.__class__._lock:
            if hasattr(self, '_initialized') and self._initialized:
                return
                
            # 支持延迟初始化，首次调用时如果未设置mysql_settings则使用默认配置
            if mysql_settings is None:
                mysql_settings = self.get_mysql_config()
                
            self.mysql_settings = mysql_settings
            self.running = False
        
        # 存储表结构信息（按数据库分组）
        self._table_schemas = {}  # 格式: {database: {table: [columns]}}
        self._table_name_mapping = {}  # 格式: {database: {lower_table: table}}
        
        # 注册表：事件类型 -> 装饰器函数列表
        self._insert_handlers = []
        self._update_handlers = []
        self._delete_handlers = []
        
        # 表过滤功能（支持多数据库）
        self._table_filters = {}  # 格式: {database.table: handlers}
        
        # 创建持久的事件循环和线程
        self._event_loop = None
        self._loop_thread = None
        
        # 初始化 Binlog 位置管理器
        if ENABLE_BINLOG_POSITION:
            self._position_manager = BinlogPositionManager()
            logger.info("✅ Binlog 位置管理器已启用")
        else:
            # 禁用时清除现有的位置记录
            try:
                position_manager = BinlogPositionManager()
                position_manager.clear_position()
                logger.info("🗑️ 已清除现有的 Binlog 位置记录")
            except Exception as e:
                logger.warning(f"⚠️ 清除 Binlog 位置记录失败: {e}")
            self._position_manager = None
            logger.info("⚠️ Binlog 位置管理器已禁用")
        self._current_position = None  # 当前 Binlog 位置
        
        # 初始化健康检查器
        self._health_checker = ConnectionHealthChecker(
            self.mysql_settings if mysql_settings else self.get_mysql_config(),
            check_interval=30  # 每30秒检查一次
        )
        
        # 初始化事件循环健康检查器
        self._event_loop_health_checker = _EventLoopHealthChecker(
            self,
            check_interval=30  # 每30秒检查一次
        )
        
        # 重试配置
        self._max_retry_wait = 300  # 最大重试等待时间（5分钟）
        self._consecutive_errors = 0  # 连续错误计数
        self._last_error_time = 0  # 上次错误时间
        
        # 背压监控配置
        self._pending_events = 0  # 当前待处理事件数
        self._pending_lock = threading.Lock()  # 计数器锁
        self._backpressure_threshold = 10000  # 背压告警阈值
        self._backpressure_warning_threshold = int(self._backpressure_threshold * 0.75)  # 警告阈值（75%）
        self._last_backpressure_warning = 0  # 上次背压告警时间
        self._backpressure_warning_interval = 60  # 告警间隔（秒）
        
        # 初始化线程池
        if MYAPS_DBSET_LIST and TURNON_BINLOG_LISTENER:
            # 使用全局线程池管理器
            self._min_workers = 5
            self._max_workers = 5
            self._thread_pool = global_pool_manager.get_pool(
                'binlog_listener', 
                max_workers=self._max_workers,
                thread_name_prefix='mysql-monitor-'
            )
            # 验证配置
            self._validate_config()
        else:
            self._thread_pool = global_pool_manager.get_pool(
                'binlog_listener', 
                max_workers=1,
                thread_name_prefix='mysql-monitor-'
            )
        
        # 标记初始化完成
        with self.__class__._lock:
            self._initialized = True
        
        # 启动互斥锁，防止并发启动
        self._startup_lock = threading.Lock()
        
        # ========== Simplified HA Module Initialization ==========
        self._event_count_since_check = 0  # 事件计数器（用于背压控制检测）
        if HA_MODULES_AVAILABLE:
            logger.info("✅ 简化版HA模块已集成：背压控制、事件去重、重试策略")

    def _validate_config(self):
        """验证MySQL配置"""
        required_fields = ["host", "port", "user", "password"]
        missing_fields = []
        
        for field in required_fields:
            if field not in self.mysql_settings or not self.mysql_settings[field]:
                missing_fields.append(field)
        
        if missing_fields and TURNON_BINLOG_LISTENER:
            raise ValueError(f"❌ 缺少必要的MySQL配置: {', '.join(missing_fields)}")
        
        # 检查数据库配置
        if not self.mysql_settings.get("databases") and not self.mysql_settings.get("database"):
            logger.warning("🔭 未指定数据库名称，将监控所有数据库")
        else:
            # 处理数据库列表
            databases = self.mysql_settings.get("databases", [])
            if self.mysql_settings.get("database"):
                databases.append(self.mysql_settings["database"])
            
            # 去重
            databases = list(set(databases))
            self.mysql_settings["databases"] = databases
            logger.info(f"🔭 配置监控的数据库: {', '.join(databases)}")
        
        # 测试连接
        try:
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "connect_timeout": 5
            }
            
            # 如果指定了数据库，使用第一个数据库测试连接
            if self.mysql_settings.get("databases"):
                conn_params["database"] = self.mysql_settings["databases"][0]
            
            conn = pymysql.connect(**conn_params)
            
            # 预加载表结构信息
            if self.mysql_settings.get("databases"):
                self._preload_table_schemas(conn)
            conn.close()
            logger.info("✅ MySQL连接测试成功")
            self._initialized = True  # 标记初始化完成
            
            # 验证 Binlog 位置（如果位置管理器已启用）
            self._validate_binlog_position()
                    
        except Exception as e:
            logger.warning(f"⚠️ MySQL连接测试警告: {e}")

    def _preload_table_schemas(self, conn):
        """预加载表结构信息"""
        try:
            databases = self.mysql_settings.get("databases", [])
            
            for database in databases:
                try:
                    with conn.cursor() as cursor:
                        # 切换到目标数据库
                        cursor.execute(f"USE `{database}`")
                        
                        # 获取所有表
                        cursor.execute("SHOW TABLES")
                        tables = [row[0] for row in cursor.fetchall()]
                        
                        # 初始化数据库结构
                        if database not in self._table_schemas:
                            self._table_schemas[database] = {}
                        if database not in self._table_name_mapping:
                            self._table_name_mapping[database] = {}
                        
                        # 创建表名映射
                        for table in tables:
                            self._table_name_mapping[database][table.lower()] = table
                        
                        logger.info(f"🐬 数据库 {database} 发现 {len(tables)} 个表")
                        
                        # 预加载表结构
                        for table in tables:
                            try:
                                cursor.execute(f"DESCRIBE `{table}`")
                                columns = [row[0] for row in cursor.fetchall()]
                                self._table_schemas[database][table] = columns
                                logger.debug(f"预加载表结构: @{database} - {table} -> {len(columns)}列")
                            except Exception as e:
                                logger.warning_msg("表结构获取", f"@{database} - {table}", str(e))
                                
                except Exception as e:
                    logger.warning_msg("数据库预加载", f"@{database}",  str(e))
            
            total_tables = sum(len(tables) for tables in self._table_schemas.values())
            logger.success("表结构预加载", f"@{database}", f"{len(self._table_schemas)}个数据库，共{total_tables}个表")
                    
        except Exception as e:
            logger.fail("表结构预加载", f"@{database}", str(e))

    def _get_correct_table_name(self, database, table_name):
        """获取正确的表名（解决大小写问题）"""
        if database in self._table_schemas and table_name in self._table_schemas[database]:
            return table_name
        
        # 尝试小写匹配
        if database in self._table_name_mapping:
            lower_table_name = table_name.lower()
            if lower_table_name in self._table_name_mapping[database]:
                return self._table_name_mapping[database][lower_table_name]
        
        return table_name
    
    def _validate_binlog_position(self):
        """验证 Binlog 位置是否有效
        
        检查两个维度：
        1. 文件名是否存在于当前的 Binlog 列表中
        2. 位置是否在文件大小范围内（防止 'position > file size' 错误）
        """
        if not ENABLE_BINLOG_POSITION or not self._position_manager:
            return
        
        saved_position = self._position_manager.load_position()
        if not saved_position:
            return
        
        log_file = saved_position.get('log_file')
        log_pos = saved_position.get('log_pos')
        
        try:
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "connect_timeout": 5
            }
            conn = pymysql.connect(**conn_params)
            
            with conn.cursor() as cursor:
                cursor.execute("SHOW BINARY LOGS")
                binary_logs = cursor.fetchall()
                logs = {row[0]: row[1] for row in binary_logs}
                
                if log_file not in logs:
                    logger.warning(f"⚠️ 保存的 Binlog 文件不存在: {log_file}，将重置位置")
                    self._reset_to_current_file_start(cursor, binary_logs)
                else:
                    file_size = logs[log_file]
                    if log_pos > file_size:
                        logger.warning(f"⚠️ 保存的位置 {log_pos} 超出文件大小 {file_size}，将重置位置")
                        self._reset_to_current_file_start(cursor, binary_logs)
            
            conn.close()
        except Exception as e:
            logger.warning(f"⚠️ 验证 Binlog 位置失败: {e}")
            self._position_manager.clear_position()
    
    def _reset_to_current_file_start(self, cursor, binary_logs):
        """重置位置到当前 Binlog 文件的起始位置
        
        当位置无效时，重置到当前文件的开头而非 SHOW MASTER STATUS 的当前位置，
        这样可以确保不会丢失断连期间的事件（可能重复，但去重器会处理）。
        
        Args:
            cursor: 数据库游标
            binary_logs: SHOW BINARY LOGS 的结果列表
        """
        try:
            cursor.execute("SHOW MASTER STATUS")
            master_status = cursor.fetchone()
            if master_status:
                current_log_file = master_status[0]
                reset_pos = 4
                
                logs_dict = {row[0]: row[1] for row in binary_logs}
                if current_log_file in logs_dict:
                    file_size = logs_dict[current_log_file]
                    if file_size > 0:
                        logger.warning(f"📍 重置到当前 Binlog 文件开头: {current_log_file}:{reset_pos}")
                        self._position_manager.save_position(current_log_file, reset_pos)
                    else:
                        logger.warning(f"📍 当前 Binlog 文件为空，使用 MASTER STATUS 位置")
                        current_log_pos = master_status[1]
                        self._position_manager.save_position(current_log_file, current_log_pos)
                else:
                    logger.warning(f"📍 当前 Binlog 文件不在列表中，使用 MASTER STATUS 位置")
                    current_log_pos = master_status[1]
                    self._position_manager.save_position(current_log_file, current_log_pos)
        except Exception as e:
            logger.error(f"❌ 重置 Binlog 位置失败: {e}")
            self._position_manager.clear_position()
    
    def _get_column_names(self, database, table_name):
        """获取表的列名"""
        # 先尝试获取正确的表名
        correct_table_name = self._get_correct_table_name(database, table_name)
        
        # 如果已经加载过，直接返回
        if (database in self._table_schemas and 
            correct_table_name in self._table_schemas[database]):
            return self._table_schemas[database][correct_table_name]
        
        # 尝试实时查询表结构
        conn = None
        try:
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "database": database,
                "connect_timeout": 5
            }
            
            conn = pymysql.connect(**conn_params)
            
            with conn.cursor() as cursor:
                # 确保使用正确的数据库
                cursor.execute(f"USE `{database}`")
                
                # 尝试DESCRIBE
                try:
                    cursor.execute(f"DESCRIBE `{correct_table_name}`")
                    columns = [row[0] for row in cursor.fetchall()]
                    
                    # 保存到缓存
                    if database not in self._table_schemas:
                        self._table_schemas[database] = {}
                    self._table_schemas[database][correct_table_name] = columns
                    
                    logger.success("表结构获取", f"{database}.{correct_table_name}", f"{len(columns)}列")
                    return columns
                except Exception as e:
                    logger.warning_msg("表结构获取", f"{database}.{correct_table_name}", str(e))
            
            if conn:
                try:
                    conn.close()
                except Exception as close_error:
                    logger.debug(f"关闭数据库连接时出错: {close_error}")
                
        except Exception as e:
            logger.warning_msg("数据库连接", database, str(e))
            # 确保连接被关闭
            if conn:
                try:
                    conn.close()
                except:
                    pass
        
        logger.warning_msg("表结构获取", f"{database}.{correct_table_name}", "无法获取列结构")
        return None

    def _map_data_with_column_names(self, database, table_name, data):
        """将数据映射到正确的列名"""
        if not data:
            return data
            
        # 尝试获取列名
        column_names = self._get_column_names(database, table_name)
        
        # 如果无法获取列名，尝试使用通用列名
        if not column_names:
            if isinstance(data, (list, tuple)):
                mapped_data = {}
                for i, value in enumerate(data):
                    mapped_data[f"col_{i}"] = value
                return mapped_data
            elif isinstance(data, dict):
                mapped_data = {}
                for key, value in data.items():
                    if key.startswith('UNKNOWN_COL'):
                        try:
                            col_num = int(key.replace('UNKNOWN_COL', ''))
                            mapped_data[f"col_{col_num}"] = value
                        except:
                            mapped_data[key] = value
                    else:
                        mapped_data[key] = value
                return mapped_data
            else:
                return {"raw_data": data}
        
        # 有列名的情况
        if isinstance(data, (list, tuple)):
            mapped_data = {}
            for i, value in enumerate(data):
                if i < len(column_names):
                    mapped_data[column_names[i]] = value
                else:
                    mapped_data[f"extra_col_{i}"] = value
            return mapped_data
        elif isinstance(data, dict):
            mapped_data = {}
            for i, (key, value) in enumerate(data.items()):
                if i < len(column_names):
                    mapped_data[column_names[i]] = value
                else:
                    mapped_data[key] = value
            return mapped_data
        
        return data

    # 装饰器方法（支持多数据库）
    def on_insert(self, func):
        """注册全局INSERT事件处理器"""
        self._insert_handlers.append(func)
        return func

    def on_update(self, func):
        """注册全局UPDATE事件处理器"""
        self._update_handlers.append(func)
        return func

    def on_delete(self, func):
        """注册全局DELETE事件处理器"""
        self._delete_handlers.append(func)
        return func

    def on_insert_for_table(self, table_name, database=None):
        """注册特定表的INSERT事件处理器"""
        def decorator(func):
            full_table_name = self._get_full_table_name(database, table_name)
            if full_table_name not in self._table_filters:
                self._table_filters[full_table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[full_table_name]["insert"].append(func)
            return func
        return decorator

    def on_update_for_table(self, table_name, database=None):
        """注册特定表的UPDATE事件处理器"""
        def decorator(func):
            full_table_name = self._get_full_table_name(database, table_name)
            if full_table_name not in self._table_filters:
                self._table_filters[full_table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[full_table_name]["update"].append(func)
            return func
        return decorator

    def on_delete_for_table(self, table_name, database=None):
        """注册特定表的DELETE事件处理器"""
        def decorator(func):
            full_table_name = self._get_full_table_name(database, table_name)
            if full_table_name not in self._table_filters:
                self._table_filters[full_table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[full_table_name]["delete"].append(func)
            return func
        return decorator

    def _get_full_table_name(self, database, table_name):
        """获取完整的表名（database.table）"""
        if database:
            return f"{database}.{table_name}"
        return table_name

    def _parse_full_table_name(self, full_table_name):
        """解析完整的表名为数据库和表名"""
        if '.' in full_table_name:
            parts = full_table_name.split('.')
            if len(parts) == 2:
                return parts[0], parts[1]  # database, table
        return None, full_table_name  # 无数据库信息，只有表名

    def _send_remind(self, message: str, level: str = "warning"):
        """发送提示通知
        
        使用全局 RemindManager 发送提示，支持去重和频率限制
        """
        # 记录到日志
        remind_type = RemindType.BINLOG_LISTENER_BREAK
        if level == "error":
            logger.error(f"🚨 告警: {message}")
        elif level == "warning":
            logger.warning(f"⚠️ 告警: {message}")
        else:
            logger.info(f"ℹ️ 通知: {message}")
        
        # 通过全局 RemindManager 发送提示（带去重和频率限制）
        remind_content = {
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "source": "binlog_listener"
        }
        
        # 在事件循环中异步发送提示
        if self._event_loop and self._event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                remind_manager.trigger_remind(remind_type, remind_content),
                self._event_loop
            )
        else:
            # 如果事件循环未运行，同步执行
            asyncio.create_task(remind_manager.trigger_remind(remind_type, remind_content))

    def regist_reminder(self, reminder):
        """注册提示提醒器到全局 RemindManager
        
        Args:
            reminder: Reminder 实例，需实现 async remind 方法
        """
        # 注册到全局 RemindManager，支持所有提示类型
        remind_manager.register(reminder, [
            RemindType.BINLOG_LISTENER_RESUME,
            RemindType.BINLOG_LISTENER_BREAK,
        ])
        logger.info("✅ 提示提醒器已注册到全局 RemindManager")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态信息（简化版）"""
        base_status = {
            "running": self.running,
            "healthy": self._health_checker.is_healthy() if hasattr(self, '_health_checker') else None,
            "event_loop_healthy": self._event_loop_health_checker.is_healthy() if hasattr(self, '_event_loop_health_checker') else None,
            "current_position": self._current_position,
            "consecutive_errors": getattr(self, '_consecutive_errors', 0),
            "thread_pool_size": getattr(self._thread_pool, '_max_workers', 'unknown'),
            "pending_events": self.get_pending_events_count(),
            "backpressure_threshold": self._backpressure_threshold,
            "backpressure_percent": round(self.get_pending_events_count() / self._backpressure_threshold * 100, 2),
        }
        
        # ========== Simplified HA: 增强返回值 ==========
        if HA_MODULES_AVAILABLE:
            bp_metrics = backpressure_controller.get_queue_metrics()
            base_status["backpressure"] = {
                "state": backpressure_controller.get_state().value,
                "queue_size": bp_metrics.current_size,
                "throttle_count": bp_metrics.throttle_count,
            }
            
            dedup_stats = event_deduplicator.get_stats()
            base_status["dedup_stats"] = {
                "total_checked": dedup_stats["total_checked"],
                "total_duplicates": dedup_stats["total_duplicates"],
                "duplicate_rate": dedup_stats["duplicate_rate"],
            }
        
        return base_status

    def _increment_pending(self):
        """增加待处理事件计数"""
        with self._pending_lock:
            self._pending_events += 1
            return self._pending_events

    def _decrement_pending(self):
        """减少待处理事件计数"""
        with self._pending_lock:
            if self._pending_events > 0:
                self._pending_events -= 1
            return self._pending_events

    def get_pending_events_count(self):
        """获取当前待处理事件数"""
        with self._pending_lock:
            return self._pending_events

    def _check_backpressure(self):
        """检查背压状态并发送告警"""
        pending_count = self.get_pending_events_count()
        
        # 检查是否超过警告阈值
        if pending_count > self._backpressure_warning_threshold:
            current_time = time.time()
            # 检查是否需要发送告警（避免频繁告警）
            if current_time - self._last_backpressure_warning > self._backpressure_warning_interval:
                warning_msg = f"⚠️ binlog监听背压告警: 待处理事件 {pending_count} 超过阈值 {self._backpressure_warning_threshold}"
                logger.warning(warning_msg)
                # 通过健康检查器发送告警
                if hasattr(self, '_health_checker'):
                    self._health_checker._send_alert(warning_msg, "warning")
                self._last_backpressure_warning = current_time
        
        # 检查是否超过严重阈值
        if pending_count > self._backpressure_threshold:
            current_time = time.time()
            if current_time - self._last_backpressure_warning > self._backpressure_warning_interval:
                error_msg = f"❌ binlog监听背压严重: 待处理事件 {pending_count} 超过上限 {self._backpressure_threshold}"
                logger.error(error_msg)
                if hasattr(self, '_health_checker'):
                    self._health_checker._send_alert(error_msg, "error")
                self._last_backpressure_warning = current_time
        
        return pending_count

    def reset_position(self):
        """重置 Binlog 位置（下次启动时从头开始）"""
        if ENABLE_BINLOG_POSITION and self._position_manager:
            self._position_manager.clear_position()
            logger.info("🔄 Binlog 位置已重置，下次启动将从最新位置开始")
        else:
            logger.warning("⚠️ Binlog 位置管理器已禁用，无法重置位置")

    def _start_event_loop(self):
        """启动事件循环线程"""
        self._event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._event_loop)
        try:
            self._event_loop.run_forever()
        except Exception as e:
            logger.fail("事件循环", "", str(e))
        finally:
            if self._event_loop:
                self._event_loop.close()

    def _monitor_thread_pool(self):
        """监控线程池并动态调整大小"""
        while self.running:
            try:
                # 检查线程池状态
                current_workers = getattr(self._thread_pool, '_max_workers', self._min_workers)
                
                # 由于线程池工作队列可能无法直接访问，这里简化监控逻辑
                # 基于时间间隔进行简单的线程池调整
                # 实际生产环境中可以根据实际负载情况调整
                logger.debug(f"binlog监听线程池状态: 当前线程数={current_workers}, 最大线程数={self._max_workers}")
                
                # 这里可以添加更复杂的监控逻辑，例如基于系统负载、任务执行时间等
                
            except Exception as e:
                logger.fail("binlog监听线程池监控", "", str(e))
            
            # 每10秒检查一次
            for _ in range(10):
                if not self.running:
                    break
                time.sleep(1)

    def start_monitoring(self):
        """开始监控Binlog（简化版）"""
        with self._startup_lock:
            if self.running:
                logger.info("⚠️ Binlog监听已经在运行")
                return
            
            logger.info("🚀 启动Binlog监听器（单进程模式）")
            self._start_listening()
    
    def _start_listening(self):
        """启动 Binlog 监听"""
        self.running = True
        # 验证线程池是否可用
        pool = global_pool_manager.get_pool(
            'binlog_listener', 
            max_workers=self._max_workers,
            thread_name_prefix='mysql-monitor-'
        )
        try:
            future = pool.submit(lambda: None)
            future.result(timeout=5)
            logger.info("Binlog监听线程池", "", "线程池可用，复用现有实例")
        except Exception:
            # 池已关闭/不可用，通过全局管理器销毁重建
            global_pool_manager.shutdown_pool('binlog_listener', wait=False)
            pool = global_pool_manager.get_pool(
                'binlog_listener', 
                max_workers=self._max_workers,
                thread_name_prefix='mysql-monitor-'
            )
            logger.success("Binlog监听线程池", "", "已重建（原池不可用）")
        self._thread_pool = pool
        
        # 启动健康检查器
        self._health_checker.start()
        
        # 启动事件循环健康检查器
        self._event_loop_health_checker.start()
        
        # ========== Simplified HA: Prometheus指标注册 ==========
        if HA_MODULES_AVAILABLE:
            prometheus_metrics.set_listener_status(True)
            logger.info("✅ Prometheus指标已注册")
        
        # 启动Binlog监控线程
        monitoring_thread = threading.Thread(target=self._monitor_binlog_with_retry, daemon=True, name='mysql-monitor-binlog')
        monitoring_thread.start()
        
        # 启动线程池监控线程
        pool_monitor_thread = threading.Thread(target=self._monitor_thread_pool, daemon=True, name='mysql-monitor-pool')
        pool_monitor_thread.start()
        
        logger.info("✅ Binlog监听线程已启动")
        logger.info("✅ Binlog监听线程池监控线程已启动")

    def _monitor_binlog_with_retry(self):
        """增强版重试机制 - 无限重试 + 持久化位置 + 健康检查"""
        retry_count = 0
        last_alert_time = 0
        alert_interval = 300  # 告警间隔（5分钟）
        
        while self.running:
            try:

                # 检查 MySQL 健康状态
                if not self._health_checker.is_healthy():
                    wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                    logger.warning(f"⏳ MySQL 连接不健康，{wait_time}秒后重试...")
                    
                    # 发送告警（限制频率）
                    current_time = time.time()
                    if current_time - last_alert_time > alert_interval:
                        self._health_checker._send_alert(f"binlog监听等待 MySQL 连接恢复，已重试 {retry_count} 次", "warning")
                        last_alert_time = current_time
                    
                    time.sleep(wait_time)
                    retry_count += 1
                    continue
                
                # 验证 Binlog 位置（MySQL重启后可能轮转）
                if ENABLE_BINLOG_POSITION and self._position_manager:
                    self._validate_binlog_position()
                
                # 尝试启动 Binlog 流
                if self.running:
                    self._start_binlog_stream()
                
                # 成功连接后重置计数
                if retry_count > 0:
                    logger.success("Binlog监听", "", f"连接已恢复，共重试 {retry_count} 次")
                    self._health_checker._send_alert(f"Binlog监听已恢复，共重试 {retry_count} 次", "info")
                retry_count = 0
                self._consecutive_errors = 0
                
            except pymysql.Error as e:
                # MySQL连接/协议错误 → 重试
                self._consecutive_errors += 1
                retry_count += 1
                
                if not self.running:
                    break
                
                wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                
                if retry_count <= 5 or retry_count % 10 == 0:
                    logger.error(f"❌ MySQL连接错误 ({retry_count}次): {type(e).__name__}: {e}")
                    logger.info(f"⏳ {wait_time}秒后重试...")
                
                current_time = time.time()
                if current_time - last_alert_time > alert_interval:
                    self._health_checker._send_alert(f"MySQL连接错误: {e}，已重试 {retry_count} 次", "error")
                    last_alert_time = current_time
                
                time.sleep(wait_time)
                
            except (ConnectionError, ConnectionResetError, BrokenPipeError, OSError) as e:
                # 网络连接错误 → 重试
                self._consecutive_errors += 1
                retry_count += 1
                
                if not self.running:
                    break
                
                wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                
                if retry_count <= 5 or retry_count % 10 == 0:
                    logger.warning(f"⚠️ 网络连接中断 ({retry_count}次): {type(e).__name__}")
                    logger.info(f"⏳ {wait_time}秒后重试...")
                
                current_time = time.time()
                if current_time - last_alert_time > alert_interval:
                    self._health_checker._send_alert(f"网络连接中断，已重试 {retry_count} 次", "warning")
                    last_alert_time = current_time
                
                time.sleep(wait_time)
                
            except Exception as e:
                # 其他未知错误 → 记录详细堆栈
                self._consecutive_errors += 1
                retry_count += 1
                
                if not self.running:
                    break
                
                wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                
                if retry_count <= 5 or retry_count % 10 == 0:
                    logger.error(f"❌ Binlog监听未知错误 ({retry_count}次): {type(e).__name__}: {e}")
                    logger.info(f"⏳ {wait_time}秒后重试...")
                
                current_time = time.time()
                if current_time - last_alert_time > alert_interval:
                    self._health_checker._send_alert(f"Binlog监听未知错误: {type(e).__name__}: {e}，已重试 {retry_count} 次", "error")
                    last_alert_time = current_time
                
                # 等待后重试
                time.sleep(wait_time)
        
        # 停止健康检查
        self._health_checker.stop()
        logger.info("🛑 binlog监听重试循环已退出")

    def _start_binlog_stream(self):
        """启动binlog流   支持多数据库 + 位置持久化"""
        settings = {
            "host": self.mysql_settings["host"],
            "port": int(self.mysql_settings["port"]),
            "user": self.mysql_settings["user"],
            "passwd": self.mysql_settings["password"],
        }
        
        # 生成更可靠的server_id，避免冲突
        # 结合进程ID、时间戳和随机数
        import random
        timestamp = int(time.time() * 1000)  # 毫秒时间戳
        random_num = random.randint(1000, 9999)
        # 使用更大的范围，确保唯一性
        server_id = 1000000000 + (os.getpid() % 10000) * 10000 + (timestamp % 10000) * 100 + random_num % 100
        
        # 基础配置
        stream_config = {
            "connection_settings": settings,
            "server_id": server_id,
            "blocking": True,
            "resume_stream": True,
            "only_events": [WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        }
        
        # 尝试恢复上次的位置
        if ENABLE_BINLOG_POSITION and self._position_manager:
            saved_position = self._position_manager.load_position()
            if saved_position:
                stream_config["log_file"] = saved_position.get("log_file")
                stream_config["log_pos"] = saved_position.get("log_pos")
                logger.info(f"📍 从上次位置恢复: {stream_config['log_file']}:{stream_config['log_pos']}")
        
        # 如果指定了数据库，只监控这些数据库
        if self.mysql_settings.get("databases"):
            stream_config["only_schemas"] = self.mysql_settings["databases"]
            logger.info(f"binlog监听指定数据库：{', '.join(self.mysql_settings['databases'])}")
        else:
            logger.info("binlog监听监控所有数据库")
        
        stream = None
        try:
            stream = BinLogStreamReader(**stream_config)
            logger.success("binlog监听", f"@{MYAPS_MAIN_DB}", "开始运行")
            
            event_count = 0
            last_position_save = time.time()
            
            for binlogevent in stream:
                if not self.running:
                    break
                
                # ========== Simplified HA: 背压控制检测 ==========
                self._event_count_since_check += 1
                if HA_MODULES_AVAILABLE and self._event_count_since_check >= 10:
                    self._event_count_since_check = 0
                    bp_state = backpressure_controller.check_pressure(
                        queue_size=self.get_pending_events_count()
                    )
                    if backpressure_controller.apply_throttling(bp_state):
                        # 触发限流，暂停拉取
                        pause_duration = backpressure_controller.pause_duration
                        logger.warning(f"⏸️ 背压限流中，暂停 {pause_duration}秒...")
                        time.sleep(pause_duration)
                
                # ========== Simplified HA: 事件去重检查 ==========
                if HA_MODULES_AVAILABLE:
                    event_id = event_deduplicator.generate_event_id_from_event(binlogevent)
                    if event_deduplicator.is_duplicate(event_id):
                        logger.debug(f"🔄 跳过重复事件: {event_id[:16]}...")
                        prometheus_metrics.inc_events_dropped("duplicate")
                        continue
                
                # 提交事件处理
                self._run_async_event(binlogevent)
                
                # ========== HA: 标记事件已处理 ==========
                if HA_MODULES_AVAILABLE:
                    event_type = type(binlogevent).__name__.replace("RowsEvent", "").upper()
                    event_deduplicator.mark_processed(
                        event_id=event_id,
                        event_type=event_type,
                        table_name=getattr(binlogevent, 'table', 'unknown'),
                        database_name=getattr(binlogevent, 'schema', 'unknown'),
                        log_file=getattr(stream, 'log_file', ''),
                        log_pos=getattr(stream, 'log_pos', 0)
                    )
                    prometheus_metrics.inc_events_processed(event_type)
                
                # 定期保存 Binlog 位置
                event_count += 1
                current_time = time.time()
                if ENABLE_BINLOG_POSITION and self._position_manager and current_time - last_position_save >= 5:  # 每5秒保存一次位置
                    try:
                        # 获取当前位置
                        log_file = stream.log_file
                        log_pos = stream.log_pos
                        if log_file and log_pos:
                            self._position_manager.save_position(log_file, log_pos)
                            self._current_position = {"log_file": log_file, "log_pos": log_pos}
                            last_position_save = current_time
                    except Exception as e:
                        logger.debug(f"保存 Binlog 位置失败: {e}")
                
                # 每处理1000个事件输出一次进度
                if event_count % 1000 == 0:
                    logger.debug(f"📊 已处理 {event_count} 个 Binlog 事件")

        except Exception as e:
            # 异常前尝试保存当前位置
            if stream and ENABLE_BINLOG_POSITION and self._position_manager:
                try:
                    self._position_manager.save_position(stream.log_file, stream.log_pos)
                    logger.info(f"💾 异常前保存位置: {stream.log_file}:{stream.log_pos}")
                except:
                    pass
            logger.fail("Binlog监听处理", "", str(e))
            raise
        finally:
            if stream:
                # 关闭前保存最终位置
                if ENABLE_BINLOG_POSITION and self._position_manager:
                    try:
                        self._position_manager.save_position(stream.log_file, stream.log_pos)
                        logger.info(f"💾 最终位置已保存: {stream.log_file}:{stream.log_pos}")
                    except:
                        pass
                stream.close()
                logger.success("Binlog监听", "", "已关闭")

    def _add_to_dead_letter_queue(self, event, error_message):
        """将失败的事件添加到DeadLetter队列（异步写入）"""
        try:
            from apps.common.utils.event_helpers import get_dead_letter_queue

            dead_letter_message = {
                'id': str(uuid.uuid4()),
                'event_type': type(event).__name__,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error_message': error_message,
                'event_data': {
                    'database': getattr(event, 'schema', 'unknown'),
                    'table': getattr(event, 'table', 'unknown'),
                    'log_file': getattr(event, 'log_file', 'unknown'),
                    'log_pos': getattr(event, 'log_pos', 0)
                }
            }

            dlq = get_dead_letter_queue()
            dlq.add_failed_event(dead_letter_message, error_message, type(event).__name__)
            logger.info(f"📥 binlog监听事件已添加到DeadLetter队列: {dead_letter_message['id']}")
        except Exception as e:
            logger.error(f"❌ binlog监听添加到DeadLetter队列失败: {e}")
    
    def _get_retry_delay(self, retry: int, base_delay: float = 0.5) -> float:
        """计算带抖动的指数退避延迟，防止重试风暴"""
        # 指数退避：0.5s, 1s, 2s, 4s...
        delay = base_delay * (2 ** retry)
        # 添加 ±20% 的抖动，错开重试时间
        jitter = random.uniform(0.8, 1.2)
        return delay * jitter
    
    def _run_async_event(self, event):
        """异步运行事件处理，支持重试机制和背压检测"""
        # 增加待处理事件计数
        self._increment_pending()
        
        # 定期检查背压状态（每100个事件检查一次）
        if self.get_pending_events_count() % 100 == 0:
            self._check_backpressure()
        
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                self._thread_pool.submit(self._process_with_counter, event)
                return
            except RuntimeError as e:
                msg = str(e).lower()
                if "shutdown" in msg:
                    # 线程池已关闭 → 正常退出，不重试
                    logger.debug(f"binlog监听线程池已关闭，跳过事件处理")
                    self._decrement_pending()
                    return
                elif "queue" in msg or "full" in msg:
                    # 队列满 → 触发背压告警
                    if retry < max_retries - 1:
                        delay = self._get_retry_delay(retry) * 2  # 倍增等待
                        logger.warning(f"⚠️ 线程池队列满，{retry+1}/{max_retries} 重试 ({delay:.2f}s后)")
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ 线程池队列持续满载，事件转入DLQ")
                        self._decrement_pending()
                        self._add_to_dead_letter_queue(event, f"ThreadPool queue full: {e}")
                else:
                    # 其他运行时错误
                    if retry < max_retries - 1:
                        delay = self._get_retry_delay(retry)
                        logger.warning(f"⚠️ 线程池运行时错误，{retry+1}/{max_retries} 重试: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ 线程池运行时错误，已达最大重试: {e}")
                        self._decrement_pending()
                        self._add_to_dead_letter_queue(event, str(e))
            except Exception as e:
                # 其他未知错误
                if retry < max_retries - 1:
                    delay = self._get_retry_delay(retry)
                    logger.warning(f"⚠️ 线程池任务提交失败，{retry+1}/{max_retries} 重试 ({delay:.2f}s后): {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ 事件处理失败，已达最大重试次数: {e}")
                    self._decrement_pending()
                    self._add_to_dead_letter_queue(event, str(e))

    def _process_with_counter(self, event):
        """处理事件并维护待处理计数（简化版）"""
        start_time = time.time()
        try:
            self.process_binlog_event(event)
            
            # ========== Simplified HA: 更新处理延迟指标 ==========
            if HA_MODULES_AVAILABLE:
                processing_delay = time.time() - start_time
                prometheus_metrics.observe_processing_delay(processing_delay)
                    
        finally:
            # 无论成功或失败，都减少待处理计数
            self._decrement_pending()
            
            # ========== Simplified HA: 更新队列大小指标 ==========
            if HA_MODULES_AVAILABLE:
                prometheus_metrics.set_queue_size(self.get_pending_events_count())
    
    def _run_handler(self, handler, *args, **kwargs):
        """运行处理器函数，支持同步和异步函数，带重试机制"""
        handler_name = getattr(handler, '__name__', str(handler))
        start_time = time.time()
        max_retries = 3
        
        for retry in range(max_retries):
            try:
                # 检查监控是否仍在运行
                if not self.running:
                    logger.debug(f"binlog监听已停止，跳过事件处理: {handler_name}")
                    return
                
                result = handler(*args, **kwargs)
                # 检查是否是协程对象
                if hasattr(result, '__await__'):
                    # 启动事件循环线程（如果尚未启动）
                    if self._event_loop is None:
                        self._loop_thread = threading.Thread(
                            target=self._start_event_loop, 
                            daemon=True,
                            name='mysql-monitor-event-loop'
                        )
                        self._loop_thread.start()
                        # 等待事件循环就绪
                        for _ in range(10):
                            if self._event_loop is not None:
                                break
                            time.sleep(0.1)
                        else:
                            logger.warning("binlog监听事件循环启动超时，使用同步执行")
                            # 回退到同步执行
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                loop.run_until_complete(result)
                            finally:
                                loop.close()
                        return
                    
                    # 使用事件循环线程非阻塞执行
                    try:
                        future = asyncio.run_coroutine_threadsafe(result, self._event_loop)
                        # 不使用result()避免阻塞
                        # 可以添加回调处理结果
                        def callback(fut):
                            try:
                                fut.result()
                                exec_time = time.time() - start_time
                                if exec_time > 5.0:
                                    logger.warning(f"binlog监听异步处理器 {handler_name} 执行时间过长: {exec_time:.2f}秒")
                                elif exec_time > 1.0:
                                    logger.debug(f"binlog监听异步处理器 {handler_name} 执行时间: {exec_time:.2f}秒")
                            except Exception as e:
                                # 细化异常类型
                                error_str = str(e).lower()
                                if "pool" in error_str and "close" in error_str:
                                    logger.warning(f"binlog监听连接池已关闭，跳过事件处理: {handler_name}")
                                elif isinstance(e, asyncio.CancelledError):
                                    logger.debug(f"binlog监听异步任务被取消: {handler_name}")
                                elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                                    logger.warning(f"⚠️ 异步处理器 {handler_name} 执行超时")
                                elif isinstance(e, (ConnectionError, ConnectionResetError, BrokenPipeError)):
                                    logger.warning(f"⚠️ 异步处理器 {handler_name} 网络错误: {type(e).__name__}")
                                else:
                                    logger.fail(f"binlog监听异步处理器 {handler_name} 执行", "", f"{type(e).__name__}: {e}")
                        future.add_done_callback(callback)
                    except Exception as e:
                        # 检查是否是连接池关闭错误
                        if "pool" in str(e).lower() and "close" in str(e).lower():
                            logger.warning(f"binlog监听连接池已关闭，跳过事件处理: {handler_name}")
                            return
                        elif retry < max_retries - 1:
                            delay = self._get_retry_delay(retry)
                            logger.warning(f"⚠️ binlog监听异步处理器提交失败，{retry+1}/{max_retries} 重试 ({delay:.2f}s后): {e}")
                            time.sleep(delay)
                            continue
                        else:
                            logger.fail(f"binlog监听异步处理器 {handler_name} 提交", "", str(e))
                else:
                    # 同步函数执行完成
                    exec_time = time.time() - start_time
                    if exec_time > 5.0:
                        logger.warning(f"binlog监听同步处理器 {handler_name} 执行时间过长: {exec_time:.2f}秒")
                    elif exec_time > 1.0:
                        logger.debug(f"binlog监听同步处理器 {handler_name} 执行时间: {exec_time:.2f}秒")
                return
            except (ConnectionError, ConnectionResetError, BrokenPipeError) as e:
                # 网络连接错误 → 重试
                if retry < max_retries - 1:
                    delay = self._get_retry_delay(retry)
                    logger.warning(f"⚠️ 处理器网络错误，{retry+1}/{max_retries} 重试: {type(e).__name__}")
                    time.sleep(delay)
                else:
                    logger.error(f"❌ 处理器 {handler_name} 网络错误，已达最大重试: {type(e).__name__}")
                    
            except (TimeoutError, asyncio.TimeoutError) as e:
                # 超时错误 → 不重试（可能是业务逻辑慢）
                logger.warning(f"⚠️ 处理器 {handler_name} 执行超时，跳过重试")
                return
                
            except asyncio.CancelledError as e:
                # 任务被取消 → 正常退出
                logger.debug(f"binlog监听任务被取消: {handler_name}")
                return
                
            except Exception as e:
                # 其他错误 → 按错误类型处理
                error_str = str(e).lower()
                if "pool" in error_str and "close" in error_str:
                    logger.warning(f"binlog监听连接池已关闭，跳过事件处理: {handler_name}")
                    return
                elif retry < max_retries - 1:
                    delay = self._get_retry_delay(retry)
                    logger.warning(f"⚠️ 处理器执行失败，{retry+1}/{max_retries} 重试 ({delay:.2f}s后): {type(e).__name__}: {e}")
                    time.sleep(delay)
                else:
                    logger.fail(f"binlog监听处理器 {handler_name} 执行", "", f"{type(e).__name__}: {e}")
        

    def process_binlog_event(self, event):
        """处理Binlog事件并调用被装饰的函数"""
        try:
            table = getattr(event, 'table', 'unknown_table')
            schema = getattr(event, 'schema', 'unknown_database')  # 数据库名称
            
            logger.debug(f"✅ binlog监听处理事件: 数据库={schema}, 表={table}, 类型={type(event).__name__}")
            
            if isinstance(event, WriteRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.debug(f"📥 InsertTo {schema}.{table}: 批量插入 {batch_count} 条记录")
                for row in event.rows:
                    if isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    elif hasattr(row, 'values'):
                        # 检查values是否是方法
                        if callable(row.values):
                            data = dict(row.values())
                        else:
                            data = row.values
                    else:
                        data = row
                    
                    mapped_data = self._map_data_with_column_names(schema, table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(schema, table, mapped_data, "INSERT")
                    
                    if batch_count == 1:
                        logger.debug(f"📥 InsertTo {schema}.{table}: {self._format_dict_for_log(mapped_data)}")
                    
                    # 将数据包装成字典格式，与UPDATE事件保持一致
                    insert_data = {"new": mapped_data}
                    
                    # 调用全局处理器
                    for handler in self._insert_handlers:
                        self._run_handler(handler, schema, table, insert_data)
                    
                    # 调用特定表处理器
                    full_table_name = self._get_full_table_name(schema, table)
                    if full_table_name in self._table_filters:
                        for handler in self._table_filters[full_table_name]["insert"]:
                            self._run_handler(handler, schema, table, insert_data)
                    
                    # 调用无数据库前缀的处理器（向后兼容）
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["insert"]:
                            self._run_handler(handler, schema, table, insert_data)
                            
            elif isinstance(event, UpdateRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.debug(f"🔄 Update {schema}.{table}: 批量更新 {batch_count} 条记录")
                for row in event.rows:
                    if hasattr(row, 'before_values') and hasattr(row, 'after_values'):
                        # 检查before_values和after_values是否是方法
                        if callable(row.before_values):
                            old_data = dict(row.before_values())
                        else:
                            old_data = row.before_values
                        if callable(row.after_values):
                            new_data = dict(row.after_values())
                        else:
                            new_data = row.after_values
                    elif isinstance(row, dict) and 'before_values' in row and 'after_values' in row:
                        old_data = row['before_values']
                        new_data = row['after_values']
                    else:
                        old_data = getattr(row, 'before_values', {})
                        new_data = getattr(row, 'after_values', {})
                    
                    mapped_old_data = self._map_data_with_column_names(schema, table, old_data)
                    mapped_new_data = self._map_data_with_column_names(schema, table, new_data)
                    change_data = {"old": mapped_old_data, "new": mapped_new_data}
                    
                    # 计算变更的字段
                    data_diff = {}
                    for key in mapped_new_data:
                        old_val = mapped_old_data.get(key)
                        new_val = mapped_new_data.get(key)
                        if old_val != new_val:
                            data_diff[key] = (old_val, new_val)
                    
                    # 检查数据质量
                    self._check_data_quality(schema, table, mapped_old_data, "UPDATE_OLD")
                    self._check_data_quality(schema, table, mapped_new_data, "UPDATE_NEW")
                    
                    if batch_count == 1:
                        logger.debug(f"🔄 Update {schema}.{table}:")
                        if data_diff:
                            for field, (old_val, new_val) in data_diff.items():
                                logger.debug(f"   {field}: {old_val} -> {new_val}")
                        else:
                            logger.debug("   无字段变更")
                    
                    # 调用全局处理器
                    for handler in self._update_handlers:
                        self._run_handler(handler, schema, table, change_data, data_diff)
                    
                    # 调用特定表处理器
                    full_table_name = self._get_full_table_name(schema, table)
                    if full_table_name in self._table_filters:
                        try:
                            update_handlers = self._table_filters[full_table_name].get("update", [])
                            for handler in update_handlers:
                                self._run_handler(handler, schema, table, change_data, data_diff)
                        except Exception as e:
                            logger.fail("表处理器访问", "", str(e))
                    
                    if table in self._table_filters:
                        try:
                            update_handlers = self._table_filters[table].get("update", [])
                            for handler in update_handlers:
                                self._run_handler(handler, schema, table, change_data, data_diff)
                        except Exception as e:
                            logger.fail("表处理器访问", "", str(e))
                            
            elif isinstance(event, DeleteRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.debug(f"🗑️ DeleteFrom {schema}.{table}: 批量删除 {batch_count} 条记录")
                for row in event.rows:
                    if isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    elif hasattr(row, 'values'):
                        # 检查values是否是方法
                        if callable(row.values):
                            data = dict(row.values())
                        else:
                            data = row.values
                    else:
                        data = row
                        
                    mapped_data = self._map_data_with_column_names(schema, table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(schema, table, mapped_data, "DELETE")
                    
                    if batch_count == 1:
                        logger.debug(f"🗑️ DeleteFrom {schema}.{table}: {self._format_dict_for_log(mapped_data)}")
                    
                    # 调用全局处理器
                    for handler in self._delete_handlers:
                        self._run_handler(handler, schema, table, mapped_data)
                    
                    # 调用特定表处理器
                    full_table_name = self._get_full_table_name(schema, table)
                    if full_table_name in self._table_filters:
                        for handler in self._table_filters[full_table_name]["delete"]:
                            self._run_handler(handler, schema, table, mapped_data)
                    
                    # 调用无数据库前缀的处理器
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["delete"]:
                            self._run_handler(handler, schema, table, mapped_data)
                            
        except Exception as e:
            logger.fail("Binlog事件处理", "", str(e))

    def _check_data_quality(self, database, table, data, event_type):
        """检查数据质量，检测是否有UNKNOWN_COL"""
        if not data:
            return
            
        # 检查是否有UNKNOWN_COL
        if isinstance(data, dict):
            unknown_cols = [key for key in data.keys() if key.startswith('UNKNOWN_COL')]
            if unknown_cols:
                logger.warning(f"⚠️ 表 {database}.{table} 的 {event_type} 事件包含 {len(unknown_cols)} 个未知列")
                logger.warning("   建议设置MySQL变量:")
                logger.warning("   SET GLOBAL binlog_row_metadata = 'FULL';")
                logger.warning("   SET GLOBAL binlog_row_image = 'FULL';")

    def _format_dict_for_log(self, data, max_length=500):
        """格式化字典数据用于日志输出，避免显示过长的内容"""
        if not data:
            return "{}"
        
        if isinstance(data, dict):
            data_str = str(data)
            if len(data_str) > max_length:
                truncated = data_str[:max_length]
                return f"{truncated}... (truncated)"
            return data_str
        return str(data)

    def stop_monitoring(self, graceful_timeout=30):
        """
        停止监控（优雅停止，HA增强版）
        
        Args:
            graceful_timeout: 优雅停止最大等待时间（秒）
        """
        if not self.running:
            logger.info("⚠️ binlog监听已经停止")
            return
        
        logger.info("🛑 开始停止binlog监听...")
        self.running = False
        

        # 1. 停止健康检查器
        if hasattr(self, '_health_checker'):
            try:
                self._health_checker.stop()
                logger.info("✅ 健康检查器已停止")
            except Exception as e:
                logger.warning(f"⚠️ 健康检查器停止失败: {e}")
        
        # 1.5 停止事件循环健康检查器
        if hasattr(self, '_event_loop_health_checker'):
            try:
                self._event_loop_health_checker.stop()
                logger.info("✅ 事件循环健康检查器已停止")
            except Exception as e:
                logger.warning(f"⚠️ 事件循环健康检查器停止失败: {e}")
        
        # ========== Simplified HA: 更新Prometheus指标 ==========
        if HA_MODULES_AVAILABLE:
            prometheus_metrics.set_listener_status(False)
        
        # 2. 等待待处理事件完成（优雅停止）
        pending = self.get_pending_events_count()
        if pending > 0:
            logger.info(f"⏳ 等待 {pending} 个待处理事件完成...")
            start_time = time.time()
            while self.get_pending_events_count() > 0:
                elapsed = time.time() - start_time
                if elapsed > graceful_timeout:
                    remaining = self.get_pending_events_count()
                    logger.warning(
                        f"⚠️ 优雅停止超时 ({graceful_timeout}秒)，"
                        f"仍有 {remaining} 个事件处理中"
                    )
                    break
                # 短暂等待后再次检查
                time.sleep(0.1)
            elapsed = time.time() - start_time
            logger.info(f"✅ 事件处理等待完成，耗时 {elapsed:.2f} 秒")
        
        # 3. 关闭事件循环
        if self._event_loop:
            try:
                self._event_loop.call_soon_threadsafe(self._event_loop.stop)
                if self._loop_thread and self._loop_thread.is_alive():
                    self._loop_thread.join(timeout=5)
                    if self._loop_thread.is_alive():
                        logger.warning("⚠️ 事件循环线程未能正常结束")
                logger.info("✅ 事件循环已关闭")
            except Exception as e:
                logger.warning(f"⚠️ 事件循环关闭失败: {e}")
        
        # 4. 关闭线程池（等待所有任务完成，不取消）
        try:
            self._thread_pool.shutdown(wait=True, cancel_futures=False)
            logger.info("✅ 线程池已关闭")
        except Exception as e:
            logger.warning(f"⚠️ 线程池关闭失败: {e}")
        
        # 5. 清理状态
        self._event_loop = None
        self._loop_thread = None
        
        logger.success("binlog监听", f"@{MYAPS_MAIN_DB}", "已完全停止")

    @staticmethod
    def get_mysql_config(is_single_db=True):
        """获取MySQL配置 - 支持多数据库"""
        config = {
            "host": MYAPS_DB_HOST,
            "port": MYAPS_DB_PORT,
            "user": MYAPS_DB_USER,
            "password": MYAPS_DB_PASSWORD,
        }
        if is_single_db:
            databases = [MYAPS_MAIN_DB]
        else:
            databases = MYAPS_DBSET_LIST
        
        if databases:
            config["databases"] = databases
            logger.info(f"🔭 binlog监听数据库: {', '.join(databases)}")
        else:
            logger.warning("⚠️ 未设置binlog监听数据库，将监控所有数据库")
        return config



# 定义全局的MySQLBinlogMonitor单例实例
# 用户可以直接导入并使用这个实例

binlog_listener = MySQLBinlogListener()


# 使用说明：
# 直接导入全局实例（推荐）
#    from apps.data_opt.utils.binlog_listener import binlog_listener
#    # 直接使用mysql_monitor对象
#    await binlog_listener.start_monitoring()
#  
#  
# 注册事件处理器示例：
#    @binlog_listener.on_insert_for_table("your_table", "your_database")
#    async def handle_insert(database, table, data):
#        # 处理插入事件
#        pass
#  
# 停止监控：
#    binlog_listener.stop_monitoring()


def is_mysql_config_valid() -> bool:
    """
    验证MySQL数据库配置是否符合监控要求

    功能：
    1. 连接到MySQL数据库
    2. 检查所有必需的binlog配置项
    3. 返回验证结果
    
    Returns:
        bool: 当所有配置项都符合要求时返回True，其他情况返回False
    """

    credentials = _get_binlog_db_credentials("验证MySQL配置")
    if not credentials:
        return False

    logger.debug("🚀 开始验证MySQL配置...")
    logger.debug(f"🔗 连接到数据库: {credentials['host']}:{credentials['port']}")

    var_result = {
        "log_bin": "ON",
        "binlog_format": "ROW",
        "binlog_row_metadata": "FULL",
        "binlog_row_image": "FULL",
    }

    try:
        # 连接数据库
        conn = pymysql.connect(
            host=credentials["host"],
            port=int(credentials["port"]),
            user=credentials["user"],
            password=credentials["password"],
            connect_timeout=5
        )
        
        logger.success("数据库连接成功")
        
        with conn.cursor() as cursor:
            # 检查所有必需的配置项
            for config_name, expected_value in var_result.items():
                cursor.execute(f"SHOW VARIABLES LIKE '{config_name}';")
                result = cursor.fetchone()
                if not result or result[1] != expected_value:
                    logger.fail("验证配置", f"{config_name} 设置错误: {result[1] if result else '无法获取'}")
                    conn.close()
                    return False
                logger.success("验证配置", f"{config_name}: {result[1]}")
        
        conn.close()
        logger.success("MySQL 配置验证通过")
        return True
        
    except Exception as e:
        error_msg = f"连接数据库失败: {str(e)}"
        logger.error("验证MySQL配置", error_msg)
        return False


def set_binlog_params():
    """
    设置MySQL binlog参数脚本（简化版）

    功能：
    1. 直接连接到MySQL数据库
    2. 设置binlog_row_metadata和binlog_row_image参数为FULL
    3. 验证设置是否成功
    """

    credentials = _get_binlog_db_credentials("设置binlog参数")
    if not credentials:
        exit(1)

    logger.info("🚀 开始设置binlog参数...")
    logger.info(f"🔗 连接到数据库: {credentials['host']}:{credentials['port']}")

    try:
        # 连接数据库
        conn = pymysql.connect(
            host=credentials["host"],
            port=int(credentials["port"]),
            user=credentials["user"],
            password=credentials["password"],
            connect_timeout=5
        )
        
        logger.success("数据库连接成功")
        
        with conn.cursor() as cursor:
            # 执行设置命令
            sql_commands = [
                "SET GLOBAL binlog_row_metadata = 'FULL';",
                "SET GLOBAL binlog_row_image = 'FULL';"
            ]
            
            for sql in sql_commands:
                logger.info(f"执行SQL: {sql}")
                cursor.execute(sql)
                logger.success("执行SQL", sql)
            
            # 验证设置
            verify_commands = [
                "SHOW VARIABLES LIKE 'binlog_row_metadata';",
                "SHOW VARIABLES LIKE 'binlog_row_image';"
            ]
            
            for sql in verify_commands:
                logger.info(f"验证设置: {sql}")
                cursor.execute(sql)
                result = cursor.fetchone()
                if result:
                    variable_name, value = result
                    logger.info(f"📊 {variable_name}: {value}")
                    if value == 'FULL':
                        logger.success("设置binlog参数", variable_name)
                    else:
                        logger.fail("设置binlog参数", variable_name, f"{value}")
        
        conn.close()
        logger.success("设置binlog参数")
        
    except Exception as e:
        logger.error("设置binlog参数", str(e))
        exit(1)
