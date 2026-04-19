from typing import List, Dict, Any, Tuple, Optional, Union, Literal
from contextlib import asynccontextmanager
from datetime import datetime
import time
import asyncio

from tortoise import Tortoise
from tortoise.connection import connections
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError

from core.settings import MYAPS_DBSET_LIST
from apps.io_api.utils.common import dict_to_lower_keys
from globalobjects import logger as log_config
import os

LOG_LEVEL = os.getenv("LOG_LEVEL") or "INFO"
# 获取统一日志器
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


def with_transaction(func):
    """
    事务装饰器，根据实例配置或方法参数决定是否使用事务
    
    Args:
        func: 要装饰的异步方法
        
    Returns:
        装饰后的方法
    """
    async def wrapper(self, *args, **kwargs):
        # 检查是否有use_transaction参数，如果有则使用，否则使用实例默认值
        transaction_mode = kwargs.pop('use_transaction', self.use_transaction)
        
        if transaction_mode:
            # 使用事务
            async with in_transaction(self.connection_name):
                return await func(self, *args, **kwargs)
        else:
            # 不使用事务
            return await func(self, *args, **kwargs)
    
    return wrapper


class DbManager:
    """数据库操作管理器"""
    
    def __init__(self, connection_name: str, batch_size: int = 1000, use_transaction: bool = True):
        """
        初始化管理器
        
        Args:
            connection_name: 数据库连接名称
            batch_size: 批量大小，超过此数量会分批处理
            use_transaction: 是否使用事务
        """
        self.connection_name = connection_name
        self.batch_size = batch_size
        self.use_transaction = use_transaction
        self.stats = {
            'total_processed': 0,
            'batches_executed': 0,
            'last_execution_time': None
        }


    @asynccontextmanager
    async def get_connection(self):
        """
        异步上下文管理器，用于安全地获取Tortoise ORM的数据库连接
        注意：Tortoise会自动管理连接的获取和释放，不需要手动关闭连接
        
        Yields:
            Tortoise数据库连接对象
        """
        connection = Tortoise.get_connection(self.connection_name)
        yield connection


    @classmethod
    def _get_conflict_fields(cls, model_class, conflict_fields: Optional[Tuple[str, ...]]=None) -> Tuple[str, ...]:
        """
        获取冲突字段，如果未提供则自动确定
        
        Args:
            model_class: Tortoise 模型类
            conflict_fields: 冲突检测字段（可选）
            
        Returns:
            冲突检测字段元组
            
        Raises:
            ValueError: 如果模型没有定义主键或唯一约束
        """
        if conflict_fields is None:
            unique_together = getattr(model_class._meta, 'unique_together', [])
            if unique_together:
                conflict_fields = unique_together[0]
            else:
                pk_attr = getattr(model_class._meta, 'pk_attr', None)
                if pk_attr:
                    conflict_fields = (pk_attr,)
                else:
                    raise ValueError(f"模型 {model_class.__name__} 没有定义主键或唯一约束")
        return conflict_fields
    

    @with_transaction
    async def call_stored_procedure(
        self, 
        procedure_name: str, 
        params_list: List[List[Any]] = None, 
        use_transaction: Optional[bool] = None,
        max_retries: int = 5, 
        retry_delay: float = 2.0 
    ) -> Dict[str, Any]:
        """
        调用数据库存储过程（支持死锁自动重试）
        
        Args:
            procedure_name: 存储过程名称
            params_list: 存储过程参数列表，每个元素是一个参数列表（可选，默认[[]]）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            max_retries: 最大重试次数，默认5次
            retry_delay: 基础重试延迟时间（秒），默认2秒
            
        Returns:
            包含执行结果的字典，包括成功状态、执行时间、影响记录数等
            
        Raises:
            Exception: 如果存储过程执行失败且重试耗尽
        """
        if params_list is None:
            params_list = [[]]
            
        start_time = datetime.now()
        retry_count = 0
        last_exception = None
        
        while retry_count <= max_retries:
            try:
                # 优化：在获取连接前先检查连接池状态
                if retry_count > 0:
                    # 等待并确保连接刷新完成
                    await asyncio.sleep(0.5)
                
                conn = Tortoise.get_connection(self.connection_name)
                affect_count = 0
                results = []
                
                for params in params_list:
                    result = await conn.execute_query(
                        f'CALL `{procedure_name}`({", ".join(["%s"] * len(params))})', 
                        params
                    )
                    count = result[0] if result else 0
                    affect_count += count
                    results.append(result)
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                self.stats['total_processed'] += len(params_list)
                self.stats['batches_executed'] += len(params_list)
                self.stats['last_execution_time'] = execution_time
                
                response = {
                    "success": True,
                    "procedure_name": procedure_name,
                    "execution_time": execution_time,
                    "total_calls": len(params_list),
                    "affected_rows": affect_count,
                    "results": results,
                    "retry_count": retry_count
                }
                
                if retry_count > 0:
                    logger.success("存储过程调用", f"{procedure_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒（第{retry_count}次重试成功），影响记录数{affect_count}条")
                else:
                    logger.success("存储过程调用", f"{procedure_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒，影响记录数{affect_count}条")
                return response
                
            except Exception as e:
                last_exception = e
                
                error_str = str(e).upper()
                is_deadlock = 'DEADLOCK' in error_str or '1213' in str(e) or '死锁' in str(e)
                is_operational_error = "OperationalError" in str(type(e))
                is_connection_closed = "Cannot acquire connection after closing pool" in str(e)
                is_none_type_error = "NoneType" in str(e)
                is_connection_error = "Connection" in str(type(e))
                is_timeout_error = "Timeout" in str(type(e))
                is_network_error = "Network" in str(type(e)) or "网络" in str(e)
                is_pool_error = "Pool" in str(type(e))
                
                if (is_deadlock or is_operational_error or is_connection_closed or is_none_type_error or 
                    is_connection_error or is_timeout_error or is_network_error or is_pool_error) and retry_count < max_retries:
                    retry_count += 1
                    # 使用指数退避策略，增加重试延迟时间
                    # 对于连接池关闭的错误，使用更长的延迟确保完全恢复
                    if is_connection_closed:
                        base_delay = 3.0  # 连接池关闭需要更长的恢复时间
                    elif is_deadlock:
                        base_delay = retry_delay * 2
                    else:
                        base_delay = retry_delay
                    
                    current_delay = base_delay * (2 ** (retry_count - 1))
                    # 限制最大延迟时间为20秒
                    current_delay = min(current_delay, 20.0)
                    
                    error_type = "连接错误"
                    if is_connection_closed:
                        error_type = "连接池关闭"
                    elif is_deadlock:
                        error_type = "死锁"
                    elif is_timeout_error:
                        error_type = "超时错误"
                    elif is_network_error:
                        error_type = "网络错误"
                    
                    logger.warning_msg(
                        "存储过程调用", 
                        f"{procedure_name}@{self.connection_name} 检测到{error_type}，第{retry_count}次重试中...", 
                        f"等待{current_delay:.1f}秒后重试"
                    )
                    
                    # 尝试刷新连接
                    if not is_deadlock:
                        # 对于连接池关闭的错误，使用快速模式刷新
                        await self.refresh_connection(fast_mode=is_connection_closed)
                    
                    await asyncio.sleep(current_delay)
                    continue
                
                logger.fail("存储过程调用", f"{procedure_name}@{self.connection_name}", str(e))
                raise last_exception
    

    async def query_data(self, table_name: str, filter_string: str = '', order_string: str = '', page_size: int = 1000, page_index: int = 0, max_retries: int = 3) -> Dict[str, Any]:
        """
        查询数据库表数据，获取符合筛选条件的数据，支持重试机制
        
        Args:
            table_name: 表名
            filter_string: WHERE条件字符串（可选）
            order_string: ORDER BY排序字符串（可选）
            page_size: 分页查询的页大小（最大/默认1000）
            page_index: 分页查询的页码（默认0，获取全部数据；若大于0则取对应页数据）
            max_retries: 最大重试次数（默认3次）
            
        Returns:
            包含查询结果的字典，包括成功状态、数据列表、总数、执行时间等
            
        Raises:
            Exception: 如果查询失败
        """
        retry_count = 0
        last_exception = None
        page_size = min(page_size, 1000)  # 限制最大页大小为1000
        
        while retry_count <= max_retries:
            start_time = datetime.now()
            
            try:
                # 使用Tortoise的连接池机制，不需要手动关闭连接
                # Tortoise会自动管理连接的获取和释放
                conn = Tortoise.get_connection(self.connection_name)
                
                # 构建WHERE和ORDER子句
                where = f" WHERE {filter_string}" if filter_string else ''
                order = f" ORDER BY {order_string}" if order_string else ''
                
                # 先获取数据总条数
                count_sql = f'SELECT COUNT(*) as total FROM `{table_name}` {where}'
                count_result = await conn.execute_query(count_sql)
                total = count_result[1][0].get('total', 0)
                
                # 查询数据
                all_data = []
                
                offset = max((page_index - 1) * page_size, 0)
                while offset < total:
                    # 构建带LIMIT和OFFSET的分页查询SQL
                    sql = f'SELECT * FROM `{table_name}` {where} {order} LIMIT {page_size} OFFSET {offset}'
                    _, batch_data = await conn.execute_query(sql)
                    all_data.extend(batch_data)
                    if page_index > 0:  # 若page_index大于0，说明需要查询指定页数据，查询当前页后直接退出
                        break
                    offset += page_size
                    # 如果当前批次数据不足page_size，说明已经获取完所有数据
                    if len(batch_data) < page_size:
                        break
            
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 更新统计信息
                self.stats['total_processed'] += total
                self.stats['batches_executed'] += (total + page_size - 1) // page_size
                self.stats['last_execution_time'] = execution_time
                
                response = {
                    "success": True,
                    "table_name": table_name,
                    "filter": filter_string,
                    "order": order_string,
                    "execution_time": execution_time,
                    "total": total,
                    "page_size": page_size,
                    "page_index": page_index,
                    "data": [dict_to_lower_keys(item) for item in all_data]
                }
                
                if retry_count > 0:
                    logger.success(f"数据查询成功（第{retry_count + 1}次重试）", f"{table_name}@{self.connection_name}", f"执行时间{execution_time:.3f}秒")
                
                logger.debug(f"数据查询完成：{response}")
                return response
                
            except Exception as e:
                last_exception = e
                retry_count += 1
                
                # 特殊处理连接相关错误
                error_msg = str(e)
                if "OperationalError" in str(type(e)) or "Cannot acquire connection after closing pool" in error_msg or "NoneType" in error_msg:
                    logger.warning(f"数据库连接错误，将进行第{retry_count}次重试", f"{table_name}@{self.connection_name}", str(e))
                    # 尝试刷新连接
                    await self.refresh_connection()
                elif retry_count <= max_retries:
                    logger.warning(f"数据查询失败，将进行第{retry_count}次重试", f"{table_name}@{self.connection_name}", str(e))
                
                if retry_count <= max_retries:
                    import asyncio
                    await asyncio.sleep(1)  # 等待1秒后重试
                else:
                    logger.fail("数据查询", f"{table_name}@{self.connection_name}", str(e))
                    raise
        
        # 理论上不会走到这里，但为了代码完整性
        if last_exception:
            raise last_exception
    

    @with_transaction
    async def delete_data(self, table_name: str, filter_string: str = '', use_transaction: Optional[bool] = None) -> Dict[str, Any]:
        """
        删除数据库表数据
        
        Args:
            table_name: 表名
            filter_string: WHERE条件字符串（可选）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            包含删除结果的字典，包括成功状态、删除记录数、执行时间等
            
        Raises:
            Exception: 如果删除失败
        """
        start_time = datetime.now()
        retry_count = 0
        max_retries = 3
        
        while retry_count <= max_retries:
            try:
                # 使用Tortoise的连接池机制，不需要手动关闭连接
                # Tortoise会自动管理连接的获取和释放
                conn = Tortoise.get_connection(self.connection_name)
                
                # 构建WHERE子句
                where = f" WHERE {filter_string}" if filter_string else ''
                
                # 构建DELETE SQL语句
                delete_sql = f'DELETE FROM `{table_name}` {where}'
                
                # 移除事务分支，统一执行核心逻辑
                affected_rows, data = await conn.execute_query(delete_sql)
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 更新统计信息
                self.stats['total_processed'] += affected_rows
                self.stats['batches_executed'] += 1
                self.stats['last_execution_time'] = execution_time
                
                response = {
                    "success": True,
                    "table_name": table_name,
                    "filter": filter_string,
                    "execution_time": execution_time,
                    "affected_rows": affected_rows,
                    "connection_name": self.connection_name
                }
                
                if retry_count > 0:
                    logger.success(f"数据删除成功（第{retry_count + 1}次重试）", f"{table_name}@{self.connection_name}", f"影响{affected_rows}行")
                else:
                    logger.success("数据删除", f"{table_name}@{self.connection_name}", f"影响{affected_rows}行")
                return response
                
            except Exception as e:
                # 特殊处理连接相关错误
                error_msg = str(e)
                if ("OperationalError" in str(type(e)) or "Cannot acquire connection after closing pool" in error_msg or "NoneType" in error_msg) and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"数据库连接错误，将进行第{retry_count}次重试", f"{table_name}@{self.connection_name}", str(e))
                    # 尝试刷新连接
                    await self.refresh_connection()
                    import asyncio
                    await asyncio.sleep(1)  # 等待1秒后重试
                else:
                    logger.fail("数据删除", f"{table_name}@{self.connection_name}", str(e))
                    raise
    

    async def _execute_native_sql(self, sql: str, params: List[Any], description: str = "") -> int:
        """
        执行原生 SQL 查询
        """
        retry_count = 0
        max_retries = 3
        
        while retry_count <= max_retries:
            try:
                start_time = datetime.now()
                # 使用Tortoise的连接池机制，不需要手动关闭连接
                # Tortoise会自动管理连接的获取和释放
                conn = Tortoise.get_connection(self.connection_name)
                
                # 检查连接是否有效
                if conn is None:
                    raise Exception("获取数据库连接失败：连接对象为None")
                
                # 检查连接是否已关闭
                if hasattr(conn, 'closed') and conn.closed:
                    raise Exception("获取数据库连接失败：连接已关闭")
                
                # 检查连接是否有execute_query方法
                if not hasattr(conn, 'execute_query'):
                    raise Exception("获取数据库连接失败：连接对象不支持execute_query方法")
                
                count, data_list = await conn.execute_query(sql, params)
                if data_list:
                    data_list = [dict_to_lower_keys(row) for row in data_list]
                execution_time = (datetime.now() - start_time).total_seconds()
                
                if description:
                    if retry_count > 0:
                        logger.info(f"{description}（第{retry_count + 1}次重试） - 执行时间：{execution_time:.3f}秒")
                    else:
                        logger.info(f"{description} - 执行时间：{execution_time:.3f}秒")
                
                return (count if count else 0, data_list)
            except Exception as e:
                # 特殊处理连接相关错误
                error_msg = str(e)
                if ("OperationalError" in str(type(e)) or "NoneType" in error_msg or "execute_command" in error_msg or "closed" in error_msg or "Cannot acquire connection after closing pool" in error_msg) and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"数据库连接错误，将进行第{retry_count}次重试", f"{description}@{self.connection_name}", error_msg)
                    # 尝试刷新连接
                    await self.refresh_connection()
                    import asyncio
                    await asyncio.sleep(1)  # 等待1秒后重试
                else:
                    logger.fail("SQL执行", f"{description}@{self.connection_name}", error_msg)
                    logger.debug(f"SQL：{sql[:200]}...")
                    raise
    

    async def _bulk_upsert_native_sql(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None
    ) -> Dict[str, int]:
        """
        使用原生 SQL 执行批量 upsert
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据列表（不能为空）
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
        """
        
        # 获取冲突字段
        conflict_fields = self._get_conflict_fields(model_class, conflict_fields)

        # 如果未提供exclude_fields，则初始化为空列表
        # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
        if exclude_fields is None:
            exclude_fields = []

        # 获取表名
        table_name = model_class._meta.db_table
        
        # 获取所有字段，排除指定字段
        all_fields = [key for key in data_list[0].keys() 
                     if key not in exclude_fields]
        
        if not all_fields:
            raise ValueError("没有可插入的字段")
        
        # 验证字段
        # 只验证冲突字段，update_fields可能为空
        for field in conflict_fields:
            # 检查字段是否是自增主键
            is_auto_increment_pk = False
            if hasattr(model_class._meta, 'pk_attr') and field == model_class._meta.pk_attr:
                pk_field = model_class._meta.fields_map.get(field)
                if pk_field and pk_field.generated:
                    is_auto_increment_pk = True
            # 跳过自增主键的验证
            if not is_auto_increment_pk and field not in all_fields:
                raise ValueError(f"字段 {field} 不在数据字段中")
        
        # 如果有update_fields，验证其是否在数据字段中
        if update_fields:
            for field in update_fields:
                if field not in all_fields:
                    raise ValueError(f"字段 {field} 不在数据字段中")
        
        # 构建字段字符串，使用反引号包裹字段名
        fields_str = ', '.join([f"`{field}`" for field in all_fields])
        total_inserted = 0
        total_updated = 0
        
        # 分批处理
        for i in range(0, len(data_list), self.batch_size):
            batch = data_list[i:i + self.batch_size]
            
            # 构建 VALUES 占位符和参数
            placeholders = []
            values = []
            for data in batch:
                # 只包含需要的字段
                row_values = [data[field] for field in all_fields]
                placeholders.append('(' + ', '.join(['%s'] * len(all_fields)) + ')')
                values.extend(row_values)
            
            # 构建 SQL
            if update_fields:
                # 如果有update_fields，构建完整的UPSERT语句
                # 构建 ON DUPLICATE KEY UPDATE 部分
                update_parts = [f"`{field}` = VALUES(`{field}`)" for field in update_fields]
                conflict_fields_str = ', '.join([f"`{field}`" for field in conflict_fields])
                update_str = ', '.join(update_parts)
                
                sql = f"""
                INSERT INTO `{table_name}` ({fields_str}) 
                VALUES {', '.join(placeholders)}
                ON DUPLICATE KEY UPDATE
                {update_str}
                """
            else:
                # 如果没有update_fields，只执行INSERT IGNORE
                sql = f"INSERT IGNORE INTO `{table_name}` ({fields_str}) VALUES {', '.join(placeholders)}"
            
            # 执行 SQL
            affected, data_list = await self._execute_native_sql(
                sql, 
                values,
                description=f"批量 upsert 批次 {i//self.batch_size + 1}"
            )
            
            # 计算新增和更新数量
            if update_fields:
                # 对于 INSERT INTO ... ON DUPLICATE KEY UPDATE:
                # - 新增行：影响行数 = 1
                # - 更新行：影响行数 = 2
                # - 未改变：影响行数 = 0
                # 使用实际处理的数据行数（len(batch)）代替batch_size，因为可能有重复数据
                actual_size = len(batch)
                updated = max(0, affected - actual_size)
                inserted = affected - 2 * updated
                # 确保插入数量为非负数
                inserted = max(0, inserted)
            else:
                # 对于 INSERT IGNORE:
                # - 成功插入：影响行数 = 1
                # - 忽略冲突：影响行数 = 0
                inserted = affected
                updated = 0
            
            total_inserted += inserted
            total_updated += updated
            
            self.stats['batches_executed'] += 1
        
        return {
            'inserted': total_inserted,
            'updated': total_updated,
            'total': total_inserted + total_updated
        }
    
    
    async def _bulk_upsert_orm(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None
    ) -> Dict[str, int]:
        """
        使用 ORM 的 bulk_create 执行批量 upsert
        适合小批量数据
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据列表（不能为空）
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段
            exclude_fields: 排除的字段列表（必须显式提供）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
        """        
        # 获取冲突字段
        # 获取数据库连接对象
        db = Tortoise.get_connection(self.connection_name)
        conflict_fields = conflict_fields if conflict_fields is not None else self._get_conflict_fields(model_class)
        
        # 获取模型的主键字段
        pk_field = getattr(model_class._meta, 'pk_attr', None)

        # 如果未提供exclude_fields，则初始化为空列表
        # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
        if exclude_fields is None:
            exclude_fields = []
        
        # 注意：不要将冲突字段（包括主键）从数据中排除，它们是标识记录所必需的
        # 只需要在后续更新操作中确保不更新主键字段即可

        # 过滤排除字段
        filtered_data = []
        for data in data_list:
            filtered_data.append({k: v for k, v in data.items() 
                               if k not in exclude_fields})
        
        # 查询已存在的记录
        existing_records = []
        if conflict_fields:
            # 构建查询条件
            conditions = []
            for data in filtered_data:
                condition = {}  # 将条件改为字典类型
                for field in conflict_fields:
                    if field in data:
                        condition[field] = data[field]
                if condition:
                    conditions.append(condition)
            
            # 查询所有满足冲突条件的记录
            # 使用 Q 对象构建 OR 查询
            if conditions:
                # 第一个条件作为基础
                query = Q(**conditions[0])
                # 为每个条件创建 Q 对象并使用 OR 连接
                for condition in conditions[1:]:
                    query |= Q(**condition)
                
                existing_records = await model_class.filter(query).only(*conflict_fields).using_db(db).all()
            else:
                existing_records = []
        
        # 创建模型实例
        instances = [model_class(**data) for data in filtered_data]
        
        # 使用 bulk_create
        # 如果没有update_fields，不执行更新操作（仅插入）
        if existing_records:# update_fields:
            # 使用指定的数据库连接执行bulk_create
            if len(filtered_data) == 1:
                await existing_records[0].update_from_dict(filtered_data[0])
                # 获取需要更新的字段列表，确保不包含主键字段
                update_fields_list = [field for field in filtered_data[0].keys() if field != pk_field]
                await existing_records[0].save(update_fields=update_fields_list)
                # await model_class.filter(query).only(*conflict_fields).using_db(db).all().update_from_dict(filtered_data[0])
            else:
                # 确保update_fields不包含主键字段
                filtered_update_fields = None
                if update_fields:
                    filtered_update_fields = [field for field in update_fields if field != pk_field]
                await model_class.bulk_create(instances, on_conflict=conflict_fields, update_fields=filtered_update_fields, using_db=db)
            
        else:
            # 只执行插入操作，忽略冲突
            await model_class.bulk_create(instances, ignore_conflicts=True, using_db=db)
        
        # 计算新增和更新数量
        # 创建现有记录的冲突字段值的集合，用于快速查找
        existing_keys = set()
        for record in existing_records:
            key = tuple(getattr(record, field) for field in conflict_fields)
            existing_keys.add(key)
        
        # 计算新增和更新数量
        updated_count = 0
        inserted_count = 0
        
        for data in filtered_data:
            key = tuple(data.get(field) for field in conflict_fields)
            if key in existing_keys:
                updated_count += 1
            else:
                inserted_count += 1
        
        return {
            'inserted': inserted_count,
            'updated': updated_count,
            'total': inserted_count + updated_count
        }
    

    @with_transaction
    async def bulk_upsert(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_fields: Optional[List[str]] = None,
        exclude_fields: Optional[List[str]] = None,
        conflict_fields: Optional[Tuple[str, ...]] = None,
        use_orm_or_sql: Literal["orm", "sql", "auto"] = "sql",
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        批量 upsert 主方法
        
        Args:
            model_class: Tortoise 模型类
            data_list: 数据字典列表（不能为空）
            conflict_fields: 冲突检测字段（必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段列表（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 要排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            use_orm_or_sql: 显式指定使用 ORM 或 SQL 执行批量 upsert，默认使用 SQL 执行 （auto时根据数据量自动选择）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
        Returns:
            执行统计信息
        """
        
        start_time = datetime.now()
        db_table = model_class._meta.db_table
        try:
            # 获取冲突字段（需要在计算默认update_fields之前获取）
            if conflict_fields is None:
                conflict_fields = self._get_conflict_fields(model_class, conflict_fields)
            
            # 如果未提供exclude_fields，则初始化为空列表
            # 注意：不再默认排除冲突字段，因为它们可能是必需的主键字段
            if exclude_fields is None:
                exclude_fields = []
            
            # 如果未提供update_fields，则自动使用所有非冲突非排除字段作为默认更新字段
            if update_fields is None and data_list:
                # 获取所有字段
                all_fields = set(data_list[0].keys())
                # 获取冲突字段和排除字段的集合
                # 注意：即使exclude_fields为空，也需要排除冲突字段，因为它们不应该被更新
                excluded_set = set(conflict_fields) | set(exclude_fields)
                # 计算默认更新字段：所有非冲突非排除字段
                update_fields = list(all_fields - excluded_set)
            
            # 选择执行策略
            if use_orm_or_sql == "orm" or (use_orm_or_sql == "auto" and len(data_list) < 100):
                method = "orm"
                result = await self._bulk_upsert_orm(
                    model_class, data_list, update_fields,
                    exclude_fields, conflict_fields
                )
            else:
                method = "native_sql"
                result = await self._bulk_upsert_native_sql(
                    model_class, data_list, update_fields, 
                    exclude_fields, conflict_fields
                )

            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 更新统计
            self.stats['total_processed'] += len(data_list)
            self.stats['last_execution_time'] = execution_time
            
            response = {
                "success": True,
                "method": method,
                "total_records": len(data_list),
                "affected_rows": result['total'],
                "inserted": result['inserted'],
                "updated": result['updated'],
                "execution_time": execution_time,
                "batch_size": len(data_list),
                "conflict_fields": conflict_fields,
                "update_fields": update_fields
            }
            
            logger.success("批量upsert", f"{db_table}@{self.connection_name}", f"插入{result['inserted']}条，更新{result['updated']}条")
            return response
            
        except IntegrityError as e:
            logger.fail("数据完整性", f"{db_table}@{self.connection_name}", str(e))
            raise
        except Exception as e:
            logger.fail("批量upsert", f"{db_table}@{self.connection_name}", str(e))
            # 保留异常处理的特殊逻辑，因为它涉及到不同的异常处理策略
            transaction_mode = self.use_transaction if use_transaction is None else use_transaction
            if transaction_mode:
                # 事务会自动回滚
                raise
            else:
                return {
                    "success": False,
                    "error": str(e),
                    "total_records": len(data_list),
                    "inserted": 0,
                    "updated": 0
                }


    @with_transaction
    async def single_upsert(
        self,
        model_class,
        data: Dict[str, Any],
        conflict_fields: Optional[Tuple[str, ...]] = None,
        # update_fields: Optional[List[str]] = None,
        # exclude_fields: Optional[List[str]] = None,
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        单条记录 upsert 操作
        
        Args:
            model_class: Tortoise 模型类
            data: 单条数据字典
            conflict_fields: 冲突检测字段（必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_fields: 冲突时更新的字段列表（可选，默认使用所有非冲突非排除字段）
            exclude_fields: 要排除的字段列表（可选，默认使用conflict_fields作为排除字段）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            执行结果字典，包含操作类型、影响行数等信息
            
        Raises:
            ValueError: 如果存在多个与冲突字段匹配的记录
        """
        # 获取冲突字段
        if conflict_fields is None:
            conflict_fields = conflict_fields or self._get_conflict_fields(model_class)
            # 取字段交集：只保留既在 data 中也在 conflict_fields 里的键，为什么要这样做？
            conflict_fields = tuple(set(conflict_fields) & set(data.keys()))
            # 因为如果 data 中包含了不在 conflict_fields 里的字段，那么在 upsert 时就会报错
            # 具体应用场景：t_supply 联合主键（默认冲突字段）是 supplyno + materialno
            # 而 patch supply 时（单条），前端可能不传入 materialno
            # 此时若按联合主键索引，一则可能 raise materialno 不存在；其次，就算不报错，因为缺少 materialno，也无法索引出目标记录
        else:
            # 检查数据中是否包含所有冲突字段
            missing_fields = [field for field in conflict_fields if field not in data]
            if missing_fields:
                raise ValueError(f"数据中缺少必要的冲突字段: {', '.join(missing_fields)}")
        
        # 构建查询条件
        query_conditions = {field: data[field] for field in conflict_fields}
        
        # 查询是否存在记录
        conn = Tortoise.get_connection(self.connection_name)
        conflict_check_sql = f"""
        SELECT COUNT(*) as count FROM `{model_class._meta.db_table}`
        WHERE {' AND '.join([f'`{field}` = %s' for field in conflict_fields])}
        """
        
        # 执行查询
        result = await conn.execute_query(conflict_check_sql, list(query_conditions.values()))
        count = result[1][0]['count']
        
        # 如果存在多条冲突记录，抛出错误
        if count > 1:
            raise ValueError(f"检测到多个 {', '.join(conflict_fields)} 匹配的记录，无法执行单条 upsert 操作")
        
        # 计算更新字段
        update_fields = tuple(set(data.keys()) - set(conflict_fields))
        
        # 根据记录是否存在，决定执行INSERT还是UPDATE
        conn = Tortoise.get_connection(self.connection_name)
        
        if count == 0:
            # 执行INSERT操作
            fields = list(data.keys())
            placeholders = ['%s'] * len(fields)
            values = list(data.values())
            
            insert_sql = f"""
            INSERT INTO `{model_class._meta.db_table}` ({', '.join([f'`{k}`' for k in fields])})
            VALUES ({', '.join(placeholders)})
            """
            
            result = await conn.execute_query(insert_sql, values)
            affected_rows = result[0]
            operation_type = 'inserted'
        else:
            # 执行UPDATE操作
            if not update_fields:
                # 没有需要更新的字段
                affected_rows = 0
                operation_type = 'no_change'
            else:
                update_parts = [f'`{field}` = %s' for field in update_fields]
                where_parts = [f'`{field}` = %s' for field in conflict_fields]
                
                update_sql = f"""
                UPDATE `{model_class._meta.db_table}`
                SET {', '.join(update_parts)}
                WHERE {' AND '.join(where_parts)}
                """
                
                # 构建参数列表：先更新字段的值，再冲突字段的值
                update_values = [data[field] for field in update_fields]
                conflict_values = [data[field] for field in conflict_fields]
                all_values = update_values + conflict_values
                
                result = await conn.execute_query(update_sql, all_values)
                affected_rows = result[0]
                operation_type = 'updated'
        
        return {
            'success': True,
            'operation_type': operation_type,
            'affected_rows': affected_rows,
            'conflict_fields': conflict_fields,
            'update_fields': update_fields,
            'inserted': 1 if operation_type == 'inserted' else 0,
            'updated': 1 if operation_type == 'updated' else 0
        }


    @with_transaction
    async def conditional_bulk_upsert(
        self,
        model_class,
        data_list: List[Dict[str, Any]],
        update_rules: Dict[str, str],
        condition_field: str,
        condition_value: Any,
        conflict_fields: Optional[Tuple[str, ...]] = None,
        use_transaction: Optional[bool] = None
    ) -> Dict[str, int]:
        """
        条件批量 upsert
        支持更复杂的更新逻辑
        
        Args:
            conflict_fields: 冲突检测字段（联合主键，必须为元组形式，可省略，默认自动从model_class._meta.unique_together或model_class._meta.pk_attr获取）
            update_rules: 更新规则字典，key为字段名，value为SQL表达式
                注意：所有表达式必须包含VALUES
                例如: {'quantity': 'quantity + VALUES(quantity)', 'price': 'VALUES(price)'}
            condition_field: 条件字段（必需）
            condition_value: 条件值（必需）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            包含新增和更新数量的字典: {'inserted': int, 'updated': int, 'total': int}
        """
        # 获取冲突字段
        conflict_fields = self._get_conflict_fields(model_class, conflict_fields)

        table_name = model_class._meta.db_table
        all_fields = list(data_list[0].keys())
        fields_str = ', '.join([f"`{field}`" for field in all_fields])
        
        total_inserted = 0
        total_updated = 0
        
        async def execute_batch():
            nonlocal total_inserted, total_updated
            for i in range(0, len(data_list), self.batch_size):
                batch = data_list[i:i + self.batch_size]
                batch_size = len(batch)
                
                # 构建 VALUES
                placeholders = []
                values = []
                for data in batch:
                    row_values = [data[field] for field in all_fields]
                    placeholders.append('(' + ', '.join(['%s'] * len(all_fields)) + ')')
                    values.extend(row_values)
                
                # 构建条件更新
                update_parts = []
                for field, expression in update_rules.items():
                    if 'VALUES' not in expression:
                        raise ValueError(f"更新规则表达式必须包含VALUES: {field} = {expression}")
                    update_parts.append(f"`{field}` = {expression}")
                
                # 添加条件
                where_clause = f"WHERE `{condition_field}` = %s"
                values.append(condition_value)
                
                # 为冲突字段字符串添加反引号包裹
                conflict_fields_str = ', '.join([f"`{field}`" for field in conflict_fields])
                update_str = ', '.join(update_parts)
                
                # 构建 SQL 语句
                sql = f"""
                INSERT INTO `{table_name}` ({fields_str}) 
                VALUES {', '.join(placeholders)}
                ON DUPLICATE KEY UPDATE
                {update_str}
                {where_clause}
                """
                
                affected, data_list = await self._execute_native_sql(
                    sql, values, f"条件批量 upsert 批次 {i//self.batch_size + 1}"
                )
                
                # 计算新增和更新数量
                # 对于条件更新，我们需要预查询来获取更准确的计数
                # 先查询已存在的记录
                existing_records = []
                if conflict_fields:
                    # 构建查询条件
                    conditions = []
                    for data in batch:
                        condition = {}
                        for field in conflict_fields:
                            condition[field] = data[field]
                        conditions.append(condition)
                    
                    # 查询所有满足冲突条件的记录
                    # 使用 Q 对象构建 OR 查询
                    if conditions:
                        # 第一个条件作为基础
                        query = Q(**conditions[0])
                        # 为每个条件创建 Q 对象并使用 OR 连接
                        for condition in conditions[1:]:
                            query |= Q(**condition)
                        
                        existing_records = await model_class.filter(
                            query
                        ).using_db(self.connection_name).all()
                    else:
                        existing_records = []
                
                # 计算新增数量
                inserted = batch_size - len(existing_records)
                
                # 计算更新数量
                # 对于条件更新，影响行数可能不等于更新行数
                # 影响行数 = 新增行数 + 更新成功的行数
                updated = max(0, affected - inserted)
                
                total_inserted += inserted
                total_updated += updated
        
        # 移除事务分支，直接执行批次处理
        await execute_batch()
        
        return {
            'inserted': total_inserted,
            'updated': total_updated,
            'total': total_inserted + total_updated
        }
    

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()
    

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_processed': 0,
            'batches_executed': 0,
            'last_execution_time': None
        }
    

    def switch_connection(self, connection_name: str):
        """
        切换数据库连接
        
        Args:
            connection_name: 新的数据库连接名称
        """
        self.connection_name = connection_name
        logger.info(f"已切换数据库连接至：{connection_name}")
    
    async def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        获取连接池状态（增强版）
        
        Returns:
            连接池状态信息
        """
        try:
            conn = Tortoise.get_connection(self.connection_name)
            pool = conn._pool if hasattr(conn, '_pool') else None
            
            status = {
                'connection_name': self.connection_name,
                'pool_available': pool is not None,
                'timestamp': time.time(),
                'warnings': [],
                'alerts': []
            }
            
            if pool:
                # 不同数据库后端的连接池属性可能不同
                # 尝试多种可能的属性名称
                # 当前连接数
                if hasattr(pool, '_size'):
                    status['current_size'] = pool._size
                elif hasattr(pool, 'size'):
                    status['current_size'] = pool.size
                elif hasattr(pool, 'current_size'):
                    status['current_size'] = pool.current_size
                elif hasattr(pool, '_connections'):
                    status['current_size'] = len(pool._connections)
                elif hasattr(pool, 'connections'):
                    status['current_size'] = len(pool.connections)
                else:
                    status['current_size'] = 10  # 默认值
                
                # 最大连接数
                if hasattr(pool, '_maxsize'):
                    status['max_size'] = pool._maxsize
                elif hasattr(pool, 'maxsize'):
                    status['max_size'] = pool.maxsize
                elif hasattr(pool, 'max_size'):
                    status['max_size'] = pool.max_size
                elif hasattr(pool, 'maximum_size'):
                    status['max_size'] = pool.maximum_size
                else:
                    status['max_size'] = 30  # 默认值
                
                # 最小连接数
                if hasattr(pool, '_minsize'):
                    status['min_size'] = pool._minsize
                elif hasattr(pool, 'minsize'):
                    status['min_size'] = pool.minsize
                elif hasattr(pool, 'min_size'):
                    status['min_size'] = pool.min_size
                elif hasattr(pool, 'minimum_size'):
                    status['min_size'] = pool.minimum_size
                else:
                    status['min_size'] = 10  # 默认值
                
                # 空闲连接数
                if hasattr(pool, '_idle'):
                    status['idle_connections'] = len(pool._idle)
                elif hasattr(pool, 'idle'):
                    status['idle_connections'] = len(pool.idle)
                elif hasattr(pool, 'idle_connections'):
                    status['idle_connections'] = pool.idle_connections
                elif hasattr(pool, 'free'):
                    status['idle_connections'] = len(pool.free)
                elif hasattr(pool, 'free_connections'):
                    status['idle_connections'] = pool.free_connections
                elif hasattr(pool, '_free'):
                    status['idle_connections'] = len(pool._free)
                else:
                    status['idle_connections'] = status.get('current_size', 10)  # 默认值
                
                # 使用中连接数
                if hasattr(pool, '_used'):
                    status['used_connections'] = len(pool._used)
                elif hasattr(pool, 'used'):
                    status['used_connections'] = len(pool.used)
                elif hasattr(pool, 'used_connections'):
                    status['used_connections'] = pool.used_connections
                elif hasattr(pool, 'in_use'):
                    status['used_connections'] = len(pool.in_use)
                elif hasattr(pool, 'busy'):
                    status['used_connections'] = len(pool.busy)
                elif hasattr(pool, 'busy_connections'):
                    status['used_connections'] = pool.busy_connections
                elif hasattr(pool, '_busy'):
                    status['used_connections'] = len(pool._busy)
                # 如果无法直接获取使用中连接数，尝试计算
                elif 'current_size' in status and 'idle_connections' in status:
                    status['used_connections'] = status['current_size'] - status['idle_connections']
                # 直接设置默认值
                else:
                    status['used_connections'] = 0  # 默认值
                
                # 计算使用率和预警
                if status.get('max_size', 0) > 0:
                    status['usage_rate'] = status['used_connections'] / status['max_size'] * 100
                    
                    # 使用率预警
                    if status['usage_rate'] >= 90:
                        status['alerts'].append(f"连接池使用率过高: {status['usage_rate']:.1f}%")
                    elif status['usage_rate'] >= 80:
                        status['warnings'].append(f"连接池使用率较高: {status['usage_rate']:.1f}%")
                    
                    # 空闲连接预警
                    if status['idle_connections'] == 0:
                        status['warnings'].append("连接池没有空闲连接")
            
            return status
        except Exception as e:
            logger.error(f"获取连接池状态失败: {e}")
            return {
                'connection_name': self.connection_name,
                'pool_available': False,
                'error': str(e),
                'timestamp': time.time()
            }
    
    async def check_connection_health(self, timeout: int = 5, fast_mode: bool = False) -> bool:
        """
        检查数据库连接健康状态
        
        Args:
            timeout: 查询超时时间（秒）
            fast_mode: 是否使用快速模式，快速模式下刷新连接时使用较少的重试次数
            
        Returns:
            bool: 连接是否健康
        """
        try:
            import asyncio
            conn = Tortoise.get_connection(self.connection_name)
            # 执行一个简单的查询来检查连接是否有效，添加超时设置
            await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"数据库连接健康检查超时: {self.connection_name}")
            # 尝试刷新连接
            await self.refresh_connection(fast_mode=fast_mode)
            # 再次检查连接
            try:
                conn = Tortoise.get_connection(self.connection_name)
                await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
                return True
            except Exception as e:
                logger.warning(f"刷新连接后健康检查仍失败: {e}")
                return False
        except Exception as e:
            logger.warning(f"数据库连接健康检查失败: {e}")
            # 尝试刷新连接
            await self.refresh_connection(fast_mode=fast_mode)
            # 再次检查连接
            try:
                conn = Tortoise.get_connection(self.connection_name)
                await asyncio.wait_for(conn.execute_query("SELECT 1"), timeout=timeout)
                return True
            except Exception as e:
                logger.warning(f"刷新连接后健康检查仍失败: {e}")
                return False
    
    async def refresh_connection(self, fast_mode: bool = False):
        """
        刷新数据库连接，确保连接有效
        当出现数据包序列号错误等协议层问题时，会强制重新创建连接
        
        Args:
            fast_mode: 是否使用快速模式，快速模式下使用较少的重试次数和较短的等待时间
        """
        import asyncio
        import time
        # 根据模式设置不同的重试参数
        if fast_mode:
            retry_count = 3  # 快速模式下减少重试次数
            retry_delay = 1.0  # 快速模式下减少初始延迟
        else:
            retry_count = 5  # 正常模式下增加重试次数
            retry_delay = 2.0  # 正常模式下增加初始延迟
        
        for attempt in range(retry_count):
            try:
                start_time = time.time()
                logger.info(f"尝试刷新连接 {self.connection_name} (尝试 {attempt + 1}/{retry_count})")
                
                # 1. 尝试获取并关闭当前连接
                try:
                    conn = Tortoise.get_connection(self.connection_name)
                    
                    # 关闭当前连接（如果存在且可关闭）
                    if conn and hasattr(conn, 'close'):
                        try:
                            # 检查是否是TransactionWrapper（通过检查是否有_pool属性）
                            if hasattr(conn, '_pool'):
                                # 尝试关闭连接，但如果出现事件循环冲突，就跳过
                                try:
                                    await conn.close()
                                    logger.info(f"已关闭旧连接: {self.connection_name}")
                                except Exception as close_error:
                                    # 如果是事件循环冲突，就跳过关闭操作
                                    if "bound to a different event loop" in str(close_error):
                                        logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                                    else:
                                        logger.warning(f"关闭旧连接时出错: {close_error}")
                            else:
                                # 对于TransactionWrapper，尝试获取内部连接并关闭
                                if hasattr(conn, 'connection'):
                                    inner_conn = conn.connection
                                    if inner_conn and hasattr(inner_conn, 'close'):
                                        try:
                                            await inner_conn.close()
                                            logger.info(f"已关闭TransactionWrapper内部连接: {self.connection_name}")
                                        except Exception as inner_close_error:
                                            # 如果是事件循环冲突，就跳过关闭操作
                                            if "bound to a different event loop" in str(inner_close_error):
                                                logger.warning(f"关闭TransactionWrapper内部连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                                            else:
                                                logger.warning(f"关闭TransactionWrapper内部连接时出错: {inner_close_error}")
                                logger.info(f"处理TransactionWrapper连接: {self.connection_name}")
                        except Exception as close_error:
                            # 如果是事件循环冲突，就跳过关闭操作
                            if "bound to a different event loop" in str(close_error):
                                logger.warning(f"关闭旧连接时出现事件循环冲突，跳过关闭操作: {self.connection_name}")
                            else:
                                logger.warning(f"关闭旧连接时出错: {close_error}")
                except Exception as get_conn_error:
                    logger.warning(f"获取当前连接时出错: {get_conn_error}")
                
                # 2. 从 Tortoise ORM 的连接存储中移除损坏的连接
                # 这样下次调用 connections.get() 时会自动创建新的连接
                try:
                    connections.discard(self.connection_name)
                    logger.info(f"已从连接存储中移除: {self.connection_name}")
                except Exception as discard_error:
                    logger.warning(f"移除连接时出错: {discard_error}")
                
                # 3. 尝试重新初始化 Tortoise，解决连接池关闭的问题
                try:
                    from core.database import TORTOISE_ORM_CONFIG
                    if hasattr(Tortoise, '_inited') and Tortoise._inited:
                        # 尝试关闭所有连接
                        try:
                            from tortoise.connection import connections
                            for conn_name in connections._connections.keys():
                                try:
                                    conn = connections.get(conn_name)
                                    if conn and hasattr(conn, 'close'):
                                        try:
                                            await conn.close()
                                        except Exception as close_error:
                                            logger.warning(f"关闭连接 {conn_name} 时出错: {close_error}")
                                except Exception as get_conn_error:
                                    logger.warning(f"获取连接 {conn_name} 时出错: {get_conn_error}")
                        except Exception as close_all_error:
                            logger.warning(f"关闭所有连接时出错: {close_all_error}")
                        
                        # 尝试重新初始化 Tortoise
                        try:
                            logger.info(f"尝试重新初始化 Tortoise")
                            await Tortoise.init(config=TORTOISE_ORM_CONFIG)
                            logger.info(f"Tortoise 重新初始化成功")
                        except Exception as init_error:
                            logger.warning(f"重新初始化 Tortoise 时出错: {init_error}")
                except Exception as init_error:
                    logger.warning(f"重新初始化 Tortoise 时出错: {init_error}")
                
                # 3. 等待一段时间，确保连接完全关闭
                if fast_mode:
                    wait_time = 0.5 + attempt * 0.5  # 快速模式下使用较短的等待时间
                else:
                    wait_time = 1.0 + attempt * 1.0  # 正常模式下使用较长的等待时间
                logger.info(f"等待 {wait_time:.1f} 秒，确保连接完全关闭...")
                await asyncio.sleep(wait_time)
                
                # 4. 尝试重新获取连接（会自动创建新的连接）
                try:
                    logger.info(f"尝试创建新连接: {self.connection_name}")
                    new_conn = connections.get(self.connection_name)
                    
                    # 5. 检查新连接是否有效
                    if new_conn:
                        # 执行一个简单的查询来验证连接
                        logger.info(f"验证新连接: {self.connection_name}")
                        await new_conn.execute_query("SELECT 1")
                        elapsed_time = time.time() - start_time
                        logger.info(f"数据库连接已刷新并验证: {self.connection_name} (耗时: {elapsed_time:.2f}秒)")
                        return True
                    else:
                        logger.error(f"刷新数据库连接失败: 无法获取新连接")
                        if attempt < retry_count - 1:
                            logger.info(f"将在 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 1.5  # 指数退避
                        continue
                except Exception as get_conn_error:
                    logger.error(f"获取新连接时出错: {get_conn_error}")
                    # 针对 Packet sequence number 错误进行特殊处理
                    if "Packet sequence number wrong" in str(get_conn_error):
                        logger.error(f"检测到数据包序列号错误，这是 MySQL 协议层问题")
                        logger.error(f"将进行更彻底的连接重置...")
                        # 额外等待一段时间
                        if fast_mode:
                            await asyncio.sleep(1.0)  # 快速模式下使用较短的等待时间
                        else:
                            await asyncio.sleep(2.0)  # 正常模式下使用较长的等待时间
                    if attempt < retry_count - 1:
                        logger.info(f"将在 {retry_delay} 秒后重试...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 1.5  # 指数退避
                    continue
            except Exception as e:
                logger.error(f"刷新数据库连接失败: {e}")
                if attempt < retry_count - 1:
                    logger.info(f"将在 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5  # 指数退避
                continue
        
        # 所有尝试都失败
        logger.error(f"所有尝试都失败: 无法刷新数据库连接 {self.connection_name}")
        return False


    @with_transaction
    async def update_by_index(
        self,
        model_class,
        index_dict: Dict[str, Any],
        new_values_dict: Dict[str, Any],
        not_found_behavior: Literal["insert", "error", "skip"] = "error",
        use_transaction: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        基于索引更新记录，支持更新联合主键字段
        
        Args:
            model_class: Tortoise 模型类
            index_dict: 用于索引记录的字典，包含旧的键值
            new_values_dict: 新值构成的字典，可包含联合主键字段
            not_found_behavior: 找不到记录时的行为："insert" 新增，"error" 报错，"skip" 略过
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            执行结果字典，包含操作类型、影响行数等信息
            
        Raises:
            ValueError: 当 not_found_behavior 为 "error" 且找不到记录时
        """
        start_time = datetime.now()
        max_retries = 3
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                # 先检查连接是否健康，如果不健康就刷新连接
                is_healthy = await self.check_connection_health(fast_mode=True)
                if not is_healthy:
                    logger.warning(f"数据库连接不健康，将刷新连接: {self.connection_name}")
                    await self.refresh_connection(fast_mode=True)
                
                table_name = model_class._meta.db_table
                conn = Tortoise.get_connection(self.connection_name)
                
                # 构建 WHERE 子句（使用旧值）
                where_parts = []
                where_values = []
                for field, value in index_dict.items():
                    where_parts.append(f"`{field}` = %s")
                    where_values.append(value)
                
                where_clause = " WHERE " + " AND ".join(where_parts) if where_parts else ""
                
                # 检查记录是否存在
                check_sql = f"SELECT COUNT(*) as count FROM `{table_name}`{where_clause}"
                result = await conn.execute_query(check_sql, where_values)
                count = result[1][0]['count']
                
                if count == 0:
                    if not_found_behavior == "error":
                        raise ValueError(f"未找到匹配记录: {index_dict}")
                    elif not_found_behavior == "insert":
                        # 执行插入操作
                        all_fields = list(index_dict.keys()) + list(new_values_dict.keys())
                        all_fields = list(set(all_fields))  # 去重
                        
                        fields_str = ', '.join([f"`{field}`" for field in all_fields])
                        placeholders = ', '.join(['%s'] * len(all_fields))
                        
                        values = []
                        for field in all_fields:
                            if field in new_values_dict:
                                values.append(new_values_dict[field])
                            elif field in index_dict:
                                values.append(index_dict[field])
                        
                        insert_sql = f"INSERT INTO `{table_name}` ({fields_str}) VALUES ({placeholders})"
                        affected_rows, data_list = await self._execute_native_sql(
                            insert_sql, 
                            values,
                            description="基于索引更新 - 新增记录"
                        )
                        
                        operation_type = 'inserted'
                    else:  # skip
                        affected_rows = 0
                        operation_type = 'skipped'
                else:
                    # 执行更新操作
                    # 构建 SET 子句（使用新值）
                    set_parts = []
                    set_values = []
                    for field, value in new_values_dict.items():
                        set_parts.append(f"`{field}` = %s")
                        set_values.append(value)
                    
                    if not set_parts:
                        affected_rows = 0
                        operation_type = 'no_change'
                    else:
                        set_clause = " SET " + ", ".join(set_parts)
                        update_sql = f"UPDATE `{table_name}`{set_clause}{where_clause}"
                        
                        affected_rows, data_list = await self._execute_native_sql(
                            update_sql, 
                            set_values + where_values,
                            description="基于索引更新 - 更新记录"
                        )
                        
                        operation_type = 'updated'
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 更新统计信息
                self.stats['total_processed'] += 1
                self.stats['batches_executed'] += 1
                self.stats['last_execution_time'] = execution_time
                
                response = {
                    "success": True,
                    "operation_type": operation_type,
                    "affected_rows": affected_rows,
                    "index_dict": index_dict,
                    "updated_fields": list(new_values_dict.keys()),
                    "execution_time": execution_time
                }
                
                logger.success("索引更新", f"{table_name}@{self.connection_name}", f"影响{affected_rows}行")
                return response
                
            except Exception as e:
                error_msg = str(e)
                is_connection_error = "Cannot acquire connection after closing pool" in error_msg or "OperationalError" in str(type(e)) or "NoneType" in error_msg
                
                if is_connection_error and retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"数据库连接错误，将进行第{retry_count}次重试", f"{table_name}@{self.connection_name}", error_msg)
                    # 尝试刷新连接
                    await self.refresh_connection()
                    import asyncio
                    await asyncio.sleep(1)  # 等待1秒后重试
                    continue
                
                logger.fail("索引更新", f"{table_name}@{self.connection_name}", error_msg)
                raise


# 延迟初始化 db_managers
_db_managers = None

def get_db_managers():
    """
    获取数据库管理器实例字典
    返回同一个实例字典，确保统计信息的持久化
    """
    global _db_managers
    if _db_managers is None:
        _db_managers = {}
        for db in MYAPS_DBSET_LIST:
            _db_managers[db] = DbManager(db)
    return _db_managers

# 为了保持向后兼容，提供一个模块级别的变量
# 但在实际使用中，建议使用 get_db_managers() 函数来获取
def db_managers():
    """
    获取数据库管理器实例字典
    每次调用都会返回最新的实例字典，确保使用当前事件循环的连接
    """
    return get_db_managers()