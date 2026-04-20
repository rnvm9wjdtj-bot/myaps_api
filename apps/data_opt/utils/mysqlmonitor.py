"""
MySQL Binlog 实时监控模块

功能特性：
1. 实时监听 MySQL binlog，捕获 INSERT/UPDATE/DELETE 事件
2. 无限重试机制 - 连接断开后自动重连，永不放弃
3. 位置持久化 - 自动保存 binlog 位置，重启后从断点续传
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
    from apps.data_opt.utils.mysqlmonitor import mysql_monitor
    
    # 注册告警处理器（可选）
    def alert_handler(message, level):
        # 发送到企业微信/钉钉/邮件等
        print(f"[{level}] {message}")
    
    mysql_monitor.register_alert_handler(alert_handler)
    
    # 启动监控
    mysql_monitor.start_monitoring()
    
    # 查看状态
    status = mysql_monitor.get_status()
    print(status)
    
    # 停止监控
    mysql_monitor.stop_monitoring()
"""


import os, asyncio, time, logging, threading, concurrent.futures, json, pickle, pymysql
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
# from functools import wraps
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import (
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)

from core.settings import MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD, MYAPS_MAIN_DB, MYAPS_DBSET_LIST, TURNON_DBMONITOR, TURNON_BINLOG_POSITION_MANAGER, MYAPS_ROOT_PASSWORD
from globalobjects import logger as log_config
from apps.common.utils.thread_pool_manager import global_pool_manager
import os

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
logger = log_config.get_logger(__name__, level=LOG_LEVEL)



BINLOG_POSITION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "storage",
    ".binlog_position.json"
)



class BinlogPositionManager:
    """Binlog 位置管理器 - 负责持久化和恢复 binlog 位置"""
    
    def __init__(self):
        self.position_file = BINLOG_POSITION_FILE
        
        self._lock = threading.RLock()
        self._last_save_time = 0
        self._save_interval = 5  # 最少5秒保存一次，避免频繁写入
    
    def load_position(self) -> Optional[Dict[str, Any]]:
        """加载保存的 binlog 位置"""
        try:
            if os.path.exists(self.position_file):
                with self._lock:
                    with open(self.position_file, 'r', encoding='utf-8') as f:
                        position = json.load(f)
                        logger.info(f"📂 已加载 binlog 位置: {position.get('log_file')}:{position.get('log_pos')}")
                        return position
        except Exception as e:
            logger.warning(f"⚠️ 加载 binlog 位置失败: {e}")
        return None
    
    def save_position(self, log_file: str, log_pos: int, timestamp: Optional[float] = None):
        """保存 binlog 位置到文件"""
        current_time = time.time()
        
        # 限制保存频率
        if current_time - self._last_save_time < self._save_interval:
            return
        
        try:
            with self._lock:
                position = {
                    'log_file': log_file,
                    'log_pos': log_pos,
                    'timestamp': timestamp or current_time,
                    'datetime': datetime.fromtimestamp(timestamp or current_time).strftime('%Y-%m-%d %H:%M:%S')
                }
                
                # 先写入临时文件，再重命名，保证原子性
                temp_file = self.position_file + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(position, f, indent=2)
                
                if os.path.exists(self.position_file):
                    os.replace(temp_file, self.position_file)
                else:
                    os.rename(temp_file, self.position_file)
                
                self._last_save_time = current_time
                logger.debug(f"💾 Binlog 位置已保存: {log_file}:{log_pos}")
        except Exception as e:
            logger.error(f"❌ 保存 binlog 位置失败: {e}")
    
    def clear_position(self):
        """清除保存的位置（通常在手动重置时使用）"""
        try:
            if os.path.exists(self.position_file):
                os.remove(self.position_file)
                logger.info("🗑️ Binlog 位置已清除")
        except Exception as e:
            logger.warning(f"⚠️ 清除 binlog 位置失败: {e}")


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
        if not TURNON_DBMONITOR:
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
                    self._send_alert("MySQL 配置检查失败，请检查 binlog 配置", "warning")
            
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



class MySQLBinlogMonitor:
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
        
        # 初始化 binlog 位置管理器
        if TURNON_BINLOG_POSITION_MANAGER:
            self._position_manager = BinlogPositionManager()
            logger.info("✅ Binlog 位置管理器已启用")
        else:
            self._position_manager = None
            logger.info("⚠️ Binlog 位置管理器已禁用")
            if os.path.exists(BINLOG_POSITION_FILE):
                try:
                    os.remove(BINLOG_POSITION_FILE)
                    logger.info("🗑️ 已删除旧的 binlog 标记点文件")
                except Exception as e:
                    logger.warning(f"⚠️ 删除 binlog 标记点文件失败: {e}")
        self._current_position = None  # 当前 binlog 位置
        
        # 初始化健康检查器
        self._health_checker = ConnectionHealthChecker(
            self.mysql_settings if mysql_settings else self.get_mysql_config(),
            check_interval=30  # 每30秒检查一次
        )
        
        # 重试配置
        self._max_retry_wait = 300  # 最大重试等待时间（5分钟）
        self._consecutive_errors = 0  # 连续错误计数
        self._last_error_time = 0  # 上次错误时间
        
        if MYAPS_DBSET_LIST and TURNON_DBMONITOR:
            # 使用全局线程池管理器
            self._min_workers = 5
            self._max_workers = 5
            self._thread_pool = global_pool_manager.get_pool(
                'mysql_monitor', 
                max_workers=self._max_workers,
                thread_name_prefix='mysql-monitor-'
            )
            # 验证配置
            self._validate_config()
        else:
            self._thread_pool = global_pool_manager.get_pool(
                'mysql_monitor', 
                max_workers=1,
                thread_name_prefix='mysql-monitor-'
            )
        

    def _validate_config(self):
        """验证MySQL配置"""
        required_fields = ["host", "port", "user", "password"]
        missing_fields = []
        
        for field in required_fields:
            if field not in self.mysql_settings or not self.mysql_settings[field]:
                missing_fields.append(field)
        
        if missing_fields and TURNON_DBMONITOR:
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
                                logger.debug(f"预加载表结构: {table}@{database} -> {len(columns)}列")
                            except Exception as e:
                                logger.warning_msg("表结构获取", f"{table}@{database}", str(e))
                                
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

    def _send_alert(self, message: str, level: str = "warning"):
        """发送告警通知
        
        可通过注册回调函数来自定义告警方式（企业微信、钉钉、邮件等）
        """
        # 记录到日志
        if level == "error":
            logger.error(f"🚨 告警: {message}")
        elif level == "warning":
            logger.warning(f"⚠️ 告警: {message}")
        else:
            logger.info(f"ℹ️ 通知: {message}")
        
        # 这里可以扩展为调用外部告警接口
        # 例如：企业微信、钉钉、邮件等

    def register_alert_handler(self, handler: Callable[[str, str], None]):
        """注册告警处理器
        
        Args:
            handler: 回调函数，接收 (message, level) 两个参数
        """
        self._health_checker.register_alert_callback(handler)
        logger.info("✅ 告警处理器已注册")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态信息"""
        return {
            "running": self.running,
            "healthy": self._health_checker.is_healthy() if hasattr(self, '_health_checker') else None,
            "current_position": self._current_position,
            "consecutive_errors": getattr(self, '_consecutive_errors', 0),
            "thread_pool_size": getattr(self._thread_pool, '_max_workers', 'unknown'),
        }

    def reset_position(self):
        """重置 binlog 位置（下次启动时从头开始）"""
        if TURNON_BINLOG_POSITION_MANAGER and self._position_manager:
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
                logger.debug(f"线程池状态: 当前线程数={current_workers}, 最大线程数={self._max_workers}")
                
                # 这里可以添加更复杂的监控逻辑，例如基于系统负载、任务执行时间等
                
            except Exception as e:
                logger.fail("线程池监控", "", str(e))
            
            # 每10秒检查一次
            for _ in range(10):
                if not self.running:
                    break
                time.sleep(1)

    def start_monitoring(self):
        """开始监控Binlog"""
        if not self.running:
            self.running = True
            # 重新创建线程池
            try:
                import concurrent.futures
                if hasattr(self, '_thread_pool') and getattr(self._thread_pool, '_shutdown', False):
                    self._thread_pool = concurrent.futures.ThreadPoolExecutor(
                        max_workers=self._min_workers, 
                        thread_name_prefix='mysql-monitor-'
                    )
                    logger.success("线程池", "", "已重新创建")
            except Exception as e:
                logger.fail("线程池创建", "", str(e))
            
            # 启动Binlog监控线程
            monitoring_thread = threading.Thread(target=self._monitor_binlog_with_retry, daemon=True, name='mysql-monitor-binlog')
            monitoring_thread.start()
            
            # 启动线程池监控线程
            pool_monitor_thread = threading.Thread(target=self._monitor_thread_pool, daemon=True, name='mysql-monitor-pool')
            pool_monitor_thread.start()
            
            logger.info("✅ Binlog监控线程已启动")
            logger.info("✅ 线程池监控线程已启动")
        else:
            logger.info("⚠️ Binlog监控已经在运行")

    def _monitor_binlog_with_retry(self):
        """增强版重试机制 - 无限重试 + 持久化位置 + 健康检查"""
        retry_count = 0
        last_alert_time = 0
        alert_interval = 300  # 告警间隔（5分钟）
        
        # 启动健康检查器
        self._health_checker.start()
        
        while self.running:
            try:
                # 检查 MySQL 健康状态
                if not self._health_checker.is_healthy():
                    wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                    logger.warning(f"⏳ MySQL 连接不健康，{wait_time}秒后重试...")
                    
                    # 发送告警（限制频率）
                    current_time = time.time()
                    if current_time - last_alert_time > alert_interval:
                        self._send_alert(f"Binlog 监控等待 MySQL 连接恢复，已重试 {retry_count} 次", "warning")
                        last_alert_time = current_time
                    
                    time.sleep(wait_time)
                    retry_count += 1
                    continue
                
                # 尝试启动 binlog 流
                self._start_binlog_stream()
                
                # 成功连接后重置计数
                if retry_count > 0:
                    logger.success("Binlog监控", "", f"连接已恢复，共重试 {retry_count} 次")
                    self._send_alert(f"Binlog 监控已恢复，共重试 {retry_count} 次", "info")
                retry_count = 0
                self._consecutive_errors = 0
                
            except Exception as e:
                self._consecutive_errors += 1
                retry_count += 1
                
                if not self.running:
                    break
                
                # 计算等待时间（指数退避，但不超过最大值）
                wait_time = min(2 ** min(retry_count, 8), self._max_retry_wait)
                
                # 记录错误（但避免日志过多）
                if retry_count <= 5 or retry_count % 10 == 0:
                    logger.error(f"❌ Binlog 连接失败 ({retry_count}次): {e}")
                    logger.info(f"⏳ {wait_time}秒后重试...")
                
                # 发送告警（限制频率）
                current_time = time.time()
                if current_time - last_alert_time > alert_interval:
                    self._send_alert(f"Binlog 监控连接失败: {e}，已重试 {retry_count} 次", "error")
                    last_alert_time = current_time
                
                # 等待后重试
                time.sleep(wait_time)
        
        # 停止健康检查
        self._health_checker.stop()
        logger.info("🛑 Binlog 监控重试循环已退出")

    def _start_binlog_stream(self):
        """启动Binlog流 - 支持多数据库 + 位置持久化"""
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
        if TURNON_BINLOG_POSITION_MANAGER and self._position_manager:
            saved_position = self._position_manager.load_position()
            if saved_position:
                stream_config["log_file"] = saved_position.get("log_file")
                stream_config["log_pos"] = saved_position.get("log_pos")
                logger.info(f"📍 从上次位置恢复: {stream_config['log_file']}:{stream_config['log_pos']}")
        
        # 如果指定了数据库，只监控这些数据库
        if self.mysql_settings.get("databases"):
            stream_config["only_schemas"] = self.mysql_settings["databases"]
            logger.info(f"监控数据库：{', '.join(self.mysql_settings['databases'])}")
        else:
            logger.info("监控所有数据库")
        
        stream = None
        try:
            stream = BinLogStreamReader(**stream_config)
            logger.success("Binlog监控", f"@{MYAPS_MAIN_DB}", "开始监控")
            
            event_count = 0
            last_position_save = time.time()
            
            for binlogevent in stream:
                if not self.running:
                    break
                
                # 提交事件处理
                self._run_async_event(binlogevent)
                
                # 定期保存 binlog 位置
                event_count += 1
                current_time = time.time()
                if TURNON_BINLOG_POSITION_MANAGER and self._position_manager and current_time - last_position_save >= 5:  # 每5秒保存一次位置
                    try:
                        # 获取当前位置
                        log_file = stream.log_file
                        log_pos = stream.log_pos
                        if log_file and log_pos:
                            self._position_manager.save_position(log_file, log_pos)
                            self._current_position = {"log_file": log_file, "log_pos": log_pos}
                            last_position_save = current_time
                    except Exception as e:
                        logger.debug(f"保存 binlog 位置失败: {e}")
                
                # 每处理1000个事件输出一次进度
                if event_count % 1000 == 0:
                    logger.debug(f"📊 已处理 {event_count} 个 binlog 事件")

        except Exception as e:
            # 异常前尝试保存当前位置
            if stream and TURNON_BINLOG_POSITION_MANAGER and self._position_manager:
                try:
                    self._position_manager.save_position(stream.log_file, stream.log_pos)
                    logger.info(f"💾 异常前保存位置: {stream.log_file}:{stream.log_pos}")
                except:
                    pass
            logger.fail("Binlog流处理", "", str(e))
            raise
        finally:
            if stream:
                # 关闭前保存最终位置
                if TURNON_BINLOG_POSITION_MANAGER and self._position_manager:
                    try:
                        self._position_manager.save_position(stream.log_file, stream.log_pos)
                        logger.info(f"💾 最终位置已保存: {stream.log_file}:{stream.log_pos}")
                    except:
                        pass
                stream.close()
                logger.success("Binlog流", "", "已关闭")

    def _run_async_event(self, event):
        try:
            self._thread_pool.submit(self.process_binlog_event, event)
        except Exception as e:
            logger.fail("事件处理", "", str(e))
    
    def _run_handler(self, handler, *args, **kwargs):
        """运行处理器函数，支持同步和异步函数"""
        handler_name = getattr(handler, '__name__', str(handler))
        start_time = time.time()
        
        try:
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
                        logger.warning("事件循环启动超时，使用同步执行")
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
                                logger.warning(f"异步处理器 {handler_name} 执行时间过长: {exec_time:.2f}秒")
                            elif exec_time > 1.0:
                                logger.debug(f"异步处理器 {handler_name} 执行时间: {exec_time:.2f}秒")
                        except Exception as e:
                            logger.fail(f"异步处理器 {handler_name} 执行", "", str(e))
                    future.add_done_callback(callback)
                except Exception as e:
                    logger.fail(f"异步处理器 {handler_name} 提交", "", str(e))
            else:
                # 同步函数执行完成
                exec_time = time.time() - start_time
                if exec_time > 5.0:
                    logger.warning(f"同步处理器 {handler_name} 执行时间过长: {exec_time:.2f}秒")
                elif exec_time > 1.0:
                    logger.debug(f"同步处理器 {handler_name} 执行时间: {exec_time:.2f}秒")
        except Exception as e:
            logger.fail(f"处理器 {handler_name} 执行", "", str(e))
        finally:
            # 确保即使出错也能继续处理其他事件
            pass
        

    def process_binlog_event(self, event):
        """处理Binlog事件并调用被装饰的函数"""
        try:
            table = getattr(event, 'table', 'unknown_table')
            schema = getattr(event, 'schema', 'unknown_database')  # 数据库名称
            
            logger.debug(f"✅ 处理事件: 数据库={schema}, 表={table}, 类型={type(event).__name__}")
            
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

    def stop_monitoring(self):
        """停止监控"""
        if self.running:
            self.running = False
            # 关闭事件循环
            if self._event_loop:
                try:
                    self._event_loop.call_soon_threadsafe(self._event_loop.stop())
                    if self._loop_thread:
                        self._loop_thread.join(timeout=5)
                    logger.success("事件循环", "", "已关闭")
                except Exception as e:
                    logger.fail("事件循环关闭", "", str(e))
            
            # 关闭线程池
            try:
                self._thread_pool.shutdown(wait=True, cancel_futures=True)
                logger.success("线程池", f"{self._thread_pool}", "已关闭")
            except Exception as e:
                logger.fail("线程池关闭", f"{self._thread_pool}", str(e))
            
            # 重置状态
            self._event_loop = None
            self._loop_thread = None
            
            logger.success("Binlog监控", f"@{MYAPS_MAIN_DB}", "已停止")
        else:
            logger.info("⚠️ Binlog监控已经停止")

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
            logger.info(f"🔭 监控数据库: {', '.join(databases)}")
        else:
            logger.warning("⚠️ 未设置数据库，将监控所有数据库")
        return config



# 定义全局的MySQLBinlogMonitor单例实例
# 用户可以直接导入并使用这个实例

mysql_monitor = MySQLBinlogMonitor()


# 使用说明：
# 直接导入全局实例（推荐）
#    from apps.data_opt.utils.mysqlmonitor import mysql_monitor
#    # 直接使用mysql_monitor对象
#    await mysql_monitor.start_monitoring()
#  
#  
# 注册事件处理器示例：
#    @mysql_monitor.on_insert_for_table("your_table", "your_database")
#    async def handle_insert(database, table, data):
#        # 处理插入事件
#        pass
#  
# 停止监控：
#    mysql_monitor.stop_monitoring()


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

    # 数据库连接信息
    db_host = MYAPS_DB_HOST
    db_port = MYAPS_DB_PORT
    db_user = "root"
    db_password = MYAPS_ROOT_PASSWORD

    logger.info("🚀 开始验证MySQL配置...")
    logger.info(f"🔗 连接到数据库: {db_host}:{db_port}")

    var_result = {
        "log_bin": "ON",
        "binlog_format": "ROW",
        "binlog_row_metadata": "FULL",
        "binlog_row_image": "FULL",
    }

    try:
        # 连接数据库
        conn = pymysql.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
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

    # 数据库连接信息
    db_host = MYAPS_DB_HOST
    db_port = MYAPS_DB_PORT
    db_user = "root"
    db_password = MYAPS_ROOT_PASSWORD

    logger.info("🚀 开始设置binlog参数...")
    logger.info(f"🔗 连接到数据库: {db_host}:{db_port}")

    try:
        # 连接数据库
        conn = pymysql.connect(
            host=db_host,
            port=int(db_port),
            user=db_user,
            password=db_password,
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
