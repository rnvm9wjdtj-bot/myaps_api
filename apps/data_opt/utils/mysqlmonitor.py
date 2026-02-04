"""
bBinlog方案需要的权限
-- 创建监控用户并授权
CREATE USER 'monitor_user'@'%' IDENTIFIED BY 'strong_password';
GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'monitor_user'@'%';
GRANT SELECT ON your_database.* TO 'monitor_user'@'%';
FLUSH PRIVILEGES;

-- 检查MySQL配置
SHOW VARIABLES LIKE 'log_bin';  -- 必须为ON
SHOW VARIABLES LIKE 'binlog_format';  -- 推荐ROW模式

本模块用于实时监听 MySQL binlog，捕获指定表的 INSERT/UPDATE/DELETE 事件，
并将变更数据通过 webhook 推送给外部系统，实现第三方系统的增量同步。
依赖 python-mysql-replication 包，要求 MySQL 开启 binlog 且为 ROW 格式。
验证方法：
1. 登录 MySQL 执行：SHOW VARIABLES LIKE 'log_bin'; 结果需为 ON
2. 执行：SHOW VARIABLES LIKE 'binlog_format'; 结果需为 ROW
3. 若未开启，需在 my.cnf 中设置：
   [mysqld]
   log_bin=mysql-bin
   binlog_format=ROW
   server_id=1
4. 重启 MySQL 使配置生效
"""


import os, asyncio, time, logging, threading, concurrent.futures
# from functools import wraps
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import (
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)

from config.settings import MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD, MYAPS_MAIN_DB, MYAPS_DBSET_LIST


logger = logging.getLogger(__name__)

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
        
        # 创建持久的事件循环
        self._event_loop = None
        
        # 验证配置
        self._validate_config()

    def _validate_config(self):
        """验证MySQL配置"""
        required_fields = ["host", "port", "user", "password"]
        missing_fields = []
        
        for field in required_fields:
            if field not in self.mysql_settings or not self.mysql_settings[field]:
                missing_fields.append(field)
        
        if missing_fields:
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
            import pymysql
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
                                logger.debug(f"预加载表结构: {database}.{table} -> {len(columns)}列")
                            except Exception as e:
                                logger.warning(f"🚫 无法获取表 {database}.{table} 结构: {e}")
                                
                except Exception as e:
                    logger.warning(f"🚫 预加载数据库 {database} 表结构失败: {e}")
            
            total_tables = sum(len(tables) for tables in self._table_schemas.values())
            logger.info(f"✅ 成功预加载 {len(self._table_schemas)} 个数据库，共 {total_tables} 个表的结构")
                    
        except Exception as e:
            logger.warning(f"❌ 预加载表结构失败: {e}")

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
        try:
            import pymysql
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
                    
                    logger.info(f"✅ 实时获取表结构成功: {database}.{correct_table_name} -> {len(columns)}列")
                    return columns
                except Exception as e:
                    logger.warning(f"🚫 获取表 {database}.{correct_table_name} 结构失败: {e}")
            
            conn.close()
                
        except Exception as e:
            logger.warning(f"🚫 连接数据库 {database} 失败: {e}")
        
        logger.warning(f"🚫 无法获取表 {database}.{correct_table_name} 的列结构")
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

    def start_monitoring(self):
        """开始监控Binlog"""
        self.running = True
        monitoring_thread = threading.Thread(target=self._monitor_binlog_with_retry, daemon=True)
        monitoring_thread.start()
        logger.info("✅ Binlog监控线程已启动")

    def _monitor_binlog_with_retry(self):
        """带重试机制的Binlog监控"""
        retry_count = 0
        max_retries = 5
        
        while self.running and retry_count < max_retries:
            try:
                self._start_binlog_stream()
                retry_count = 0
                
            except Exception as e:
                retry_count += 1
                if not self.running:
                    break
                    
                wait_time = min(2 ** retry_count, 60)
                logger.error(f"🚫 Binlog连接失败，{wait_time}秒后重试 ({retry_count}/{max_retries}): {e}")
                
                for _ in range(wait_time * 10):
                    if not self.running:
                        break
                    time.sleep(0.1)
        
        if retry_count >= max_retries:
            logger.error("🚫 达到最大重试次数，停止监控")

    def _start_binlog_stream(self):
        """启动Binlog流 - 支持多数据库"""
        settings = {
            "host": self.mysql_settings["host"],
            "port": int(self.mysql_settings["port"]),
            "user": self.mysql_settings["user"],
            "passwd": self.mysql_settings["password"],
        }
        
        server_id = 100 + os.getpid() % 1000
        
        # 基础配置
        stream_config = {
            "connection_settings": settings,
            "server_id": server_id,
            "blocking": True,
            "resume_stream": True,
            "only_events": [WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        }
        
        # 如果指定了数据库，只监控这些数据库
        if self.mysql_settings.get("databases"):
            stream_config["only_schemas"] = self.mysql_settings["databases"]
            logger.info(f"🔭 监控数据库: {', '.join(self.mysql_settings['databases'])}")
        else:
            logger.info("✅ 监控所有数据库")
        
        try:
            stream = BinLogStreamReader(**stream_config)
            logger.info("✅ 开始监控MySQL Binlog...")
            
            for binlogevent in stream:
                if not self.running:
                    break
                
                # 直接在当前线程中执行，避免创建新线程导致的事件循环冲突
                self._run_async_event(binlogevent)

        except Exception as e:
            logger.error(f"🚫 Binlog流处理错误: {e}")
            raise
        finally:
            if 'stream' in locals():
                stream.close()
                logger.info("✅ Binlog流已关闭")

    def _run_async_event(self, event):
        """在新线程中运行事件"""
        try:
            # 直接调用同步方法处理事件
            self.process_binlog_event(event)
        except Exception as e:
            logger.error(f"🚫 处理事件时出错: {e}")
    
    def _run_handler(self, handler, *args, **kwargs):
        """运行处理器函数，支持同步和异步函数"""
        try:
            result = handler(*args, **kwargs)
            # 检查是否是协程对象
            if hasattr(result, '__await__'):
                # 使用现有的事件循环或获取当前线程的事件循环
                try:
                    loop = asyncio.get_event_loop()
                    loop.run_until_complete(result)
                except RuntimeError:  # 如果没有事件循环，才创建新的
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(result)
                    finally:
                        loop.close()
        except Exception as e:
            logger.error(f"❌ 执行处理器失败: {e}")
        

    def process_binlog_event(self, event):
        """处理Binlog事件并调用被装饰的函数"""
        try:
            table = getattr(event, 'table', 'unknown_table')
            schema = getattr(event, 'schema', 'unknown_database')  # 数据库名称
            
            logger.debug(f"✅ 处理事件: 数据库={schema}, 表={table}, 类型={type(event).__name__}")
            
            if isinstance(event, WriteRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.info(f"📥 InsertTo {schema}.{table}: 批量插入 {batch_count} 条记录")
                for row in event.rows:
                    if hasattr(row, 'values'):
                        data = row.values
                    elif isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    else:
                        data = row
                    
                    mapped_data = self._map_data_with_column_names(schema, table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(schema, table, mapped_data, "INSERT")
                    
                    if batch_count == 1:
                        logger.info(f"📥 InsertTo {schema}.{table}: {self._format_dict_for_log(mapped_data)}")
                    
                    # 调用全局处理器
                    for handler in self._insert_handlers:
                        self._run_handler(handler, schema, table, mapped_data)
                    
                    # 调用特定表处理器
                    full_table_name = self._get_full_table_name(schema, table)
                    if full_table_name in self._table_filters:
                        for handler in self._table_filters[full_table_name]["insert"]:
                            self._run_handler(handler, schema, table, mapped_data)
                    
                    # 调用无数据库前缀的处理器（向后兼容）
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["insert"]:
                            self._run_handler(handler, schema, table, mapped_data)
                            
            elif isinstance(event, UpdateRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.info(f"🔄 Update {schema}.{table}: 批量更新 {batch_count} 条记录")
                for row in event.rows:
                    if hasattr(row, 'before_values') and hasattr(row, 'after_values'):
                        old_data = row.before_values
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
                        logger.info(f"🔄 Update {schema}.{table}:")
                        if data_diff:
                            for field, (old_val, new_val) in data_diff.items():
                                logger.info(f"   {field}: {old_val} -> {new_val}")
                        else:
                            logger.info("   无字段变更")
                    
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
                            logger.error(f"❌ 访问特定表处理器列表失败: {e}")
                    
                    # 调用无数据库前缀的处理器
                    if table in self._table_filters:
                        try:
                            update_handlers = self._table_filters[table].get("update", [])
                            for handler in update_handlers:
                                self._run_handler(handler, schema, table, change_data, data_diff)
                        except Exception as e:
                            logger.error(f"❌ 访问无数据库前缀处理器列表失败: {e}")
                            
            elif isinstance(event, DeleteRowsEvent):
                batch_count = len(event.rows)
                if batch_count > 1:
                    logger.info(f"🗑️ DeleteFrom {schema}.{table}: 批量删除 {batch_count} 条记录")
                for row in event.rows:
                    if hasattr(row, 'values'):
                        data = row.values
                    elif isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    else:
                        data = row
                    
                    mapped_data = self._map_data_with_column_names(schema, table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(schema, table, mapped_data, "DELETE")
                    
                    if batch_count == 1:
                        logger.info(f"🗑️ DeleteFrom {schema}.{table}: {self._format_dict_for_log(mapped_data)}")
                    
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
            logger.error(f"🚫 处理Binlog事件错误: {e}")

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
        self.running = False
        logger.info("✅ Binlog监控已停止")

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
