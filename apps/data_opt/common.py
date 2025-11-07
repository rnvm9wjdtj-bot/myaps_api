# bBinlog方案需要的权限
# -- 创建监控用户并授权
# CREATE USER 'monitor_user'@'%' IDENTIFIED BY 'strong_password';
# GRANT REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'monitor_user'@'%';
# GRANT SELECT ON your_database.* TO 'monitor_user'@'%';
# FLUSH PRIVILEGES;

# -- 检查MySQL配置
# SHOW VARIABLES LIKE 'log_bin';  -- 必须为ON
# SHOW VARIABLES LIKE 'binlog_format';  -- 推荐ROW模式

# 本模块用于实时监听 MySQL binlog，捕获指定表的 INSERT/UPDATE/DELETE 事件，
# 并将变更数据通过 webhook 推送给外部系统，实现第三方系统的增量同步。
# 依赖 python-mysql-replication 包，要求 MySQL 开启 binlog 且为 ROW 格式。
# 验证方法：
# 1. 登录 MySQL 执行：SHOW VARIABLES LIKE 'log_bin'; 结果需为 ON
# 2. 执行：SHOW VARIABLES LIKE 'binlog_format'; 结果需为 ROW
# 3. 若未开启，需在 my.cnf 中设置：
#    [mysqld]
#    log_bin=mysql-bin
#    binlog_format=ROW
#    server_id=1
# 4. 重启 MySQL 使配置生效

from config.settings import MYAPS_DB_HOST, MYAPS_DB_PORT, MYAPS_DB_USER, MYAPS_DB_PASSWORD, MYAPS_DEFAULT_DB

import os
import asyncio
import time
import logging
import threading
import concurrent.futures
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import (
    WriteRowsEvent,
    UpdateRowsEvent,
    DeleteRowsEvent,
)

logger = logging.getLogger(__name__)

class MySQLBinlogMonitor:
    def __init__(self, mysql_settings):
        self.mysql_settings = mysql_settings
        self.running = False
        
        # 存储表结构信息
        self._table_schemas = {}
        # 存储表名映射（解决大小写问题）
        self._table_name_mapping = {}
        
        # 注册表：事件类型 -> 装饰器函数列表
        self._insert_handlers = []
        self._update_handlers = []
        self._delete_handlers = []
        
        # 表过滤功能
        self._table_filters = {}
        
        # 验证配置并检查MySQL设置
        self._validate_config()
        self._check_mysql_settings()

    def _check_mysql_settings(self):
        """检查并建议MySQL设置"""
        try:
            import pymysql
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "connect_timeout": 5
            }
            
            if self.mysql_settings.get("database"):
                conn_params["database"] = self.mysql_settings["database"]
            
            conn = pymysql.connect(**conn_params)
            
            with conn.cursor() as cursor:
                # 检查当前设置
                cursor.execute("SHOW VARIABLES LIKE 'binlog_row_metadata'")
                row_metadata = cursor.fetchone()
                
                cursor.execute("SHOW VARIABLES LIKE 'binlog_row_image'")
                row_image = cursor.fetchone()
                
                logger.info(f"当前MySQL设置: binlog_row_metadata={row_metadata[1]}, binlog_row_image={row_image[1]}")
                
                # 检查是否需要建议设置
                if row_metadata[1] != 'FULL' or row_image[1] != 'FULL':
                    logger.warning("⚠️ 建议设置MySQL变量以获得完整的列信息:")
                    logger.warning("   在MySQL中执行以下命令:")
                    logger.warning("   SET GLOBAL binlog_row_metadata = 'FULL';")
                    logger.warning("   SET GLOBAL binlog_row_image = 'FULL';")
                    logger.warning("   或者在my.cnf中添加:")
                    logger.warning("   binlog_row_metadata = FULL")
                    logger.warning("   binlog_row_image = FULL")
                    logger.warning("   重启MySQL后生效")
            
            conn.close()
            
        except Exception as e:
            logger.warning(f"检查MySQL设置失败: {e}")

    def _validate_config(self):
        """验证MySQL配置"""
        required_fields = ["host", "port", "user", "password"]
        missing_fields = []
        
        for field in required_fields:
            if field not in self.mysql_settings or not self.mysql_settings[field]:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"缺少必要的MySQL配置: {', '.join(missing_fields)}")
        
        # 检查数据库配置
        if not self.mysql_settings.get("database"):
            logger.warning("未指定数据库名称，列名映射功能将受限")
        else:
            logger.info(f"配置的数据库: {self.mysql_settings['database']}")
        
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
            
            if self.mysql_settings.get("database"):
                conn_params["database"] = self.mysql_settings["database"]
            
            conn = pymysql.connect(**conn_params)
            
            # 预加载表结构信息（如果有数据库）
            if self.mysql_settings.get("database"):
                self._preload_table_schemas(conn)
            conn.close()
            logger.info("MySQL连接测试成功")
            
        except Exception as e:
            logger.warning(f"MySQL连接测试警告: {e}")

    def _preload_table_schemas(self, conn):
        """预加载表结构信息"""
        try:
            with conn.cursor() as cursor:
                # 确保使用正确的数据库
                cursor.execute(f"USE `{self.mysql_settings['database']}`")
                
                # 方法1: 使用SHOW TABLES
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                
                # 创建表名映射（解决大小写敏感问题）
                for table in tables:
                    self._table_name_mapping[table.lower()] = table
                
                logger.info(f"发现 {len(tables)} 个表，开始预加载表结构...")
                
                for table in tables:
                    try:
                        # 方法1: 使用DESCRIBE
                        cursor.execute(f"DESCRIBE `{table}`")
                        columns = [row[0] for row in cursor.fetchall()]
                        self._table_schemas[table] = columns
                        logger.debug(f"预加载表结构: {table} -> {len(columns)}列")
                    except Exception as e:
                        logger.warning(f"无法使用DESCRIBE获取表 {table} 结构: {e}")
                            
            logger.info(f"成功预加载 {len(self._table_schemas)} 个表的结构")
                    
        except Exception as e:
            logger.warning(f"预加载表结构失败: {e}")

    def _get_correct_table_name(self, table_name):
        """获取正确的表名（解决大小写问题）"""
        if table_name in self._table_schemas:
            return table_name
        
        # 尝试小写匹配
        lower_table_name = table_name.lower()
        if lower_table_name in self._table_name_mapping:
            return self._table_name_mapping[lower_table_name]
        
        return table_name

    def _get_column_names(self, table_name):
        """获取表的列名"""
        # 先尝试获取正确的表名
        correct_table_name = self._get_correct_table_name(table_name)
        
        # 如果已经加载过，直接返回
        if correct_table_name in self._table_schemas:
            return self._table_schemas[correct_table_name]
        
        # 如果没有数据库信息，无法获取列结构
        if not self.mysql_settings.get("database"):
            logger.warning(f"未指定数据库，无法获取表 {correct_table_name} 的结构")
            return None
        
        # 尝试实时查询表结构
        try:
            import pymysql
            conn_params = {
                "host": self.mysql_settings["host"],
                "port": int(self.mysql_settings["port"]),
                "user": self.mysql_settings["user"],
                "password": self.mysql_settings["password"],
                "database": self.mysql_settings["database"],
                "connect_timeout": 5
            }
            
            conn = pymysql.connect(**conn_params)
            
            with conn.cursor() as cursor:
                # 确保使用正确的数据库
                cursor.execute(f"USE `{self.mysql_settings['database']}`")
                
                # 方法1: 尝试DESCRIBE
                try:
                    cursor.execute(f"DESCRIBE `{correct_table_name}`")
                    columns = [row[0] for row in cursor.fetchall()]
                    self._table_schemas[correct_table_name] = columns
                    logger.info(f"实时获取表结构成功: {correct_table_name} -> {len(columns)}列")
                    return columns
                except Exception as e:
                    logger.warning(f"DESCRIBE表 {correct_table_name} 失败: {e}")
            
            conn.close()
                
        except Exception as e:
            logger.warning(f"获取表 {correct_table_name} 结构失败: {e}")
        
        logger.warning(f"无法获取表 {correct_table_name} 的列结构")
        return None

    def _map_data_with_column_names(self, table_name, data):
        """将数据映射到正确的列名"""
        if not data:
            return data
            
        # 尝试获取列名
        column_names = self._get_column_names(table_name)
        
        # 如果无法获取列名，尝试使用通用列名
        if not column_names:
            if isinstance(data, (list, tuple)):
                # 如果是列表，创建通用列名
                mapped_data = {}
                for i, value in enumerate(data):
                    mapped_data[f"col_{i}"] = value
                return mapped_data
            elif isinstance(data, dict):
                # 如果是字典，检查是否是FULL模式的数据
                if all(key.startswith(('UNKNOWN_COL', 'col_')) for key in data.keys()):
                    # 尝试使用数字索引映射
                    mapped_data = {}
                    for key, value in data.items():
                        if key.startswith('UNKNOWN_COL'):
                            col_num = int(key.replace('UNKNOWN_COL', ''))
                            mapped_data[f"col_{col_num}"] = value
                        else:
                            mapped_data[key] = value
                    return mapped_data
                else:
                    # 可能是FULL模式，已经有正确的列名
                    return data
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
            # 检查是否已经是正确的列名
            if set(data.keys()).intersection(set(column_names)):
                # 已经有正确的列名，直接返回
                return data
            else:
                # 需要映射
                mapped_data = {}
                for i, (key, value) in enumerate(data.items()):
                    if i < len(column_names):
                        mapped_data[column_names[i]] = value
                    else:
                        mapped_data[key] = value
                return mapped_data
        
        return data

    # 装饰器方法
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

    def on_insert_for_table(self, table_name):
        """注册特定表的INSERT事件处理器"""
        def decorator(func):
            if table_name not in self._table_filters:
                self._table_filters[table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[table_name]["insert"].append(func)
            return func
        return decorator

    def on_update_for_table(self, table_name):
        """注册特定表的UPDATE事件处理器"""
        def decorator(func):
            if table_name not in self._table_filters:
                self._table_filters[table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[table_name]["update"].append(func)
            return func
        return decorator

    def on_delete_for_table(self, table_name):
        """注册特定表的DELETE事件处理器"""
        def decorator(func):
            if table_name not in self._table_filters:
                self._table_filters[table_name] = {"insert": [], "update": [], "delete": []}
            self._table_filters[table_name]["delete"].append(func)
            return func
        return decorator

    async def start_monitoring(self):
        """开始监控Binlog"""
        self.running = True
        monitoring_thread = threading.Thread(target=self._monitor_binlog_with_retry, daemon=True)
        monitoring_thread.start()
        logger.info("Binlog监控线程已启动")

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
                logger.error(f"Binlog连接失败，{wait_time}秒后重试 ({retry_count}/{max_retries}): {e}")
                
                for _ in range(wait_time * 10):
                    if not self.running:
                        break
                    time.sleep(0.1)
        
        if retry_count >= max_retries:
            logger.error("达到最大重试次数，停止监控")

    def _start_binlog_stream(self):
        """启动Binlog流"""
        settings = {
            "host": self.mysql_settings["host"],
            "port": int(self.mysql_settings["port"]),
            "user": self.mysql_settings["user"],
            "passwd": self.mysql_settings["password"],
        }
        
        if self.mysql_settings.get("database"):
            settings["db"] = self.mysql_settings["database"]
            logger.info(f"Binlog监控数据库: {self.mysql_settings['database']}")
        else:
            logger.warning("未指定数据库名称，将监控所有数据库")
        
        server_id = 100 + os.getpid() % 1000
        
        # 基础配置
        stream_config = {
            "connection_settings": settings,
            "server_id": server_id,
            "blocking": True,
            "resume_stream": True,
            "only_events": [WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        }
        
        if self.mysql_settings.get("database"):
            stream_config["only_schemas"] = [self.mysql_settings["database"]]
        
        try:
            stream = BinLogStreamReader(**stream_config)
            logger.info("开始监控MySQL Binlog...")
            logger.info(
                """
                如果看到UNKNOWN_COL警告，请设置MySQL的binlog_row_metadata和binlog_row_image为FULL：
                -- 临时设置（重启后失效）
                SET GLOBAL binlog_row_metadata = 'FULL';
                SET GLOBAL binlog_row_image = 'FULL';

                -- 永久设置（修改my.cnf）
                -- 在[mysqld]部分添加：
                -- binlog_row_metadata = FULL
                -- binlog_row_image = FULL
                -- 然后重启MySQL
                """
                )
            
            for binlogevent in stream:
                if not self.running:
                    break
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self._run_async_event, binlogevent)
                    future.result()

        except Exception as e:
            logger.error(f"Binlog流处理错误: {e}")
            raise
        finally:
            if 'stream' in locals():
                stream.close()
                logger.info("Binlog流已关闭")

    def _run_async_event(self, event):
        """在新线程中运行异步事件"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.process_binlog_event(event))
        except Exception as e:
            logger.error(f"处理异步事件时出错: {e}")
        finally:
            loop.close()

    async def process_binlog_event(self, event):
        """处理Binlog事件并调用被装饰的函数"""
        try:
            table = getattr(event, 'table', 'unknown_table')
            event_type = type(event).__name__
            
            logger.debug(f"处理事件: 表={table}, 类型={event_type}")
            
            if isinstance(event, WriteRowsEvent):
                for row in event.rows:
                    # 处理不同的数据格式
                    if hasattr(row, 'values'):
                        data = row.values
                    elif isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    else:
                        data = row
                    
                    mapped_data = self._map_data_with_column_names(table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(table, mapped_data, "INSERT")
                    
                    logger.info(f"📥 INSERT到表 {table}: {mapped_data}")
                    
                    for handler in self._insert_handlers:
                        await handler(table, mapped_data)
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["insert"]:
                            await handler(table, mapped_data)
                            
            elif isinstance(event, UpdateRowsEvent):
                for row in event.rows:
                    # 处理不同的数据格式
                    if hasattr(row, 'before_values') and hasattr(row, 'after_values'):
                        old_data = row.before_values
                        new_data = row.after_values
                    elif isinstance(row, dict) and 'before_values' in row and 'after_values' in row:
                        old_data = row['before_values']
                        new_data = row['after_values']
                    else:
                        old_data = getattr(row, 'before_values', {})
                        new_data = getattr(row, 'after_values', {})
                    
                    mapped_old_data = self._map_data_with_column_names(table, old_data)
                    mapped_new_data = self._map_data_with_column_names(table, new_data)
                    change_data = {"old": mapped_old_data, "new": mapped_new_data}
                    
                    # 检查数据质量
                    self._check_data_quality(table, mapped_old_data, "UPDATE_OLD")
                    self._check_data_quality(table, mapped_new_data, "UPDATE_NEW")
                    
                    logger.info(f"🔄 UPDATE表 {table}:")
                    # 显示变更的字段
                    changed_fields = []
                    for key in mapped_new_data:
                        old_val = mapped_old_data.get(key)
                        new_val = mapped_new_data.get(key)
                        if old_val != new_val:
                            changed_fields.append(f"{key}: {old_val} -> {new_val}")
                    
                    if changed_fields:
                        for field in changed_fields:
                            logger.info(f"   {field}")
                    else:
                        logger.info("   无字段变更")
                    
                    for handler in self._update_handlers:
                        await handler(table, change_data)
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["update"]:
                            await handler(table, change_data)
                            
            elif isinstance(event, DeleteRowsEvent):
                for row in event.rows:
                    if hasattr(row, 'values'):
                        data = row.values
                    elif isinstance(row, dict) and 'values' in row:
                        data = row['values']
                    else:
                        data = row
                    
                    mapped_data = self._map_data_with_column_names(table, data)
                    
                    # 检查数据质量
                    self._check_data_quality(table, mapped_data, "DELETE")
                    
                    logger.info(f"🗑️ DELETE从表 {table}: {mapped_data}")
                    
                    for handler in self._delete_handlers:
                        await handler(table, mapped_data)
                    if table in self._table_filters:
                        for handler in self._table_filters[table]["delete"]:
                            await handler(table, mapped_data)
                            
        except Exception as e:
            logger.error(f"处理Binlog事件错误: {e}")

    def _check_data_quality(self, table, data, event_type):
        """检查数据质量，检测是否有UNKNOWN_COL"""
        if not data:
            return
            
        # 检查是否有UNKNOWN_COL
        unknown_cols = [key for key in data.keys() if key.startswith('UNKNOWN_COL')]
        if unknown_cols:
            logger.warning(f"⚠️ 表 {table} 的 {event_type} 事件包含 {len(unknown_cols)} 个未知列")
            logger.warning("   建议设置MySQL变量:")
            logger.warning("   SET GLOBAL binlog_row_metadata = 'FULL';")
            logger.warning("   SET GLOBAL binlog_row_image = 'FULL';")

    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        logger.info("Binlog监控已停止")


# 配置和使用示例
def get_mysql_config():
    """获取MySQL配置"""
    config = {
        "host": MYAPS_DB_HOST,
        "port": MYAPS_DB_PORT,
        "user": MYAPS_DB_USER,
        "password": MYAPS_DB_PASSWORD,
        "database": MYAPS_DEFAULT_DB  # 数据库名称，若不传则监控所有数据库（但代价是无法准确获取数据的column name）
    }
    
    # 检查数据库配置
    if not config["database"]:
        logger.warning("⚠️ 未设置MYAPS_DEFAULT_DB环境变量，列名映射功能将受限")
        logger.warning("请设置环境变量: export MYAPS_DEFAULT_DB=your_database_name")
    else:
        logger.info(f"✅ 数据库配置: {config['database']}")
    
    return config

monitor = MySQLBinlogMonitor(get_mysql_config())
monitor.start_monitoring()