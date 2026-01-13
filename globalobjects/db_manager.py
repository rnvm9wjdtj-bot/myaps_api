from typing import List, Dict, Any, Tuple, Optional, Union, Literal
import logging
from datetime import datetime

from tortoise import Tortoise
from tortoise.expressions import Q
from tortoise.transactions import in_transaction
from tortoise.exceptions import IntegrityError

from config.settings import MYAPS_DBSET_LIST

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
    async def call_stored_procedure(self, procedure_name: str, params_list: List[List[Any]] = None, use_transaction: Optional[bool] = None) -> Dict[str, Any]:
        """
        调用数据库存储过程
        
        Args:
            procedure_name: 存储过程名称
            params_list: 存储过程参数列表，每个元素是一个参数列表（可选，默认[[]]）
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
            
        Returns:
            包含执行结果的字典，包括成功状态、执行时间、影响记录数等
            
        Raises:
            Exception: 如果存储过程执行失败
        """
        if params_list is None:
            params_list = [[]]
            
        start_time = datetime.now()
        
        try:
            # 使用Tortoise的连接池机制，不需要手动关闭连接
            # Tortoise会自动管理连接的获取和释放
            conn = Tortoise.get_connection(self.connection_name)
            affect_count = 0
            results = []
            
            # 移除事务分支，统一执行核心逻辑
            for params in params_list:
                result = await conn.execute_query(
                    f'CALL {procedure_name}({", ".join(["%s"] * len(params))})', 
                    params
                )
                count = result[0] if result else 0
                affect_count += count
                results.append(result)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 更新统计信息
            self.stats['total_processed'] += len(params_list)
            self.stats['batches_executed'] += len(params_list)
            self.stats['last_execution_time'] = execution_time
            
            response = {
                "success": True,
                "procedure_name": procedure_name,
                "execution_time": execution_time,
                "total_calls": len(params_list),
                "affected_rows": affect_count,
                "results": results
            }
            
            logger.info(f"存储过程调用完成: {response}")
            return response
            
        except Exception as e:
            logger.error(f"存储过程调用失败: {e}")
            raise
    

    async def query_data(self, table_name: str, filter_string: str = '', order_string: str = '', batch_size: int = 1000) -> Dict[str, Any]:
        """
        查询数据库表数据
        
        Args:
            table_name: 表名
            filter_string: WHERE条件字符串（可选）
            order_string: ORDER BY排序字符串（可选）
            batch_size: 分批次查询的批次大小（默认1000）
            
        Returns:
            包含查询结果的字典，包括成功状态、数据列表、总数、执行时间等
            
        Raises:
            Exception: 如果查询失败
        """
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
            
            if total <= batch_size:
                # 数据量不大，直接查询全部
                sql = f'SELECT * FROM `{table_name}` {where} {order}'
                _, data = await conn.execute_query(sql)
                all_data.extend(data)
            else:
                # 数据量过大，分批次查询
                offset = 0
                while offset < total:
                    # 构建带LIMIT和OFFSET的分页查询SQL
                    sql = f'SELECT * FROM `{table_name}` {where} {order} LIMIT {batch_size} OFFSET {offset}'
                    _, batch_data = await conn.execute_query(sql)
                    all_data.extend(batch_data)
                    offset += batch_size
                    
                    # 如果当前批次数据不足batch_size，说明已经获取完所有数据
                    if len(batch_data) < batch_size:
                        break
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # 更新统计信息
            self.stats['total_processed'] += total
            self.stats['batches_executed'] += (total + batch_size - 1) // batch_size
            self.stats['last_execution_time'] = execution_time
            
            response = {
                "success": True,
                "table_name": table_name,
                "filter": filter_string,
                "order": order_string,
                "execution_time": execution_time,
                "total": total,
                "batch_size": batch_size,
                "data": all_data
            }
            
            logger.info(f"数据查询完成: {response}")
            return response
            
        except Exception as e:
            logger.error(f"数据查询失败: {e}")
            raise
    

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
            
            logger.info(f"数据删除完成: {response}")
            return response
            
        except Exception as e:
            logger.error(f"数据删除失败: {e}")
            raise
    

    async def _execute_native_sql(self, sql: str, params: List[Any], description: str = "") -> int:
        """
        执行原生 SQL 查询
        """
        try:
            start_time = datetime.now()
            # 使用Tortoise的连接池机制，不需要手动关闭连接
            # Tortoise会自动管理连接的获取和释放
            conn = Tortoise.get_connection(self.connection_name)
            result = await conn.execute_query(sql, params)
            execution_time = (datetime.now() - start_time).total_seconds()
            
            if description:
                logger.info(f"{description} - 执行时间: {execution_time:.3f}秒")
            
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"SQL 执行失败: {e}")
            logger.error(f"SQL: {sql[:200]}...")
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

        # 如果未提供exclude_fields，则使用conflict_fields作为默认排除字段
        if exclude_fields is None:
            exclude_fields = list(conflict_fields)

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
            if field not in all_fields:
                raise ValueError(f"字段 {field} 不在数据字段中")
        
        # 如果有update_fields，验证其是否在数据字段中
        if update_fields:
            for field in update_fields:
                if field not in all_fields:
                    raise ValueError(f"字段 {field} 不在数据字段中")
        
        fields_str = ', '.join(all_fields)
        total_inserted = 0
        total_updated = 0
        
        # 分批处理
        for i in range(0, len(data_list), self.batch_size):
            batch = data_list[i:i + self.batch_size]
            batch_size = len(batch)
            
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
                update_parts = [f"{field} = VALUES({field})" for field in update_fields]
                conflict_fields_str = ', '.join(conflict_fields)
                update_str = ', '.join(update_parts)
                
                sql = f"""
                INSERT INTO {table_name} ({fields_str}) 
                VALUES {', '.join(placeholders)}
                ON DUPLICATE KEY UPDATE
                {update_str}
                """
            else:
                # 如果没有update_fields，只执行INSERT IGNORE
                sql = f"INSERT IGNORE INTO {table_name} ({fields_str}) VALUES {', '.join(placeholders)}"
            
            # 执行 SQL
            affected = await self._execute_native_sql(
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
                inserted = batch_size
                updated = max(0, affected - batch_size)
                inserted -= updated
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
        conflict_fields = self._get_conflict_fields(model_class, conflict_fields)

        # 如果未提供exclude_fields，则使用conflict_fields作为默认排除字段
        if exclude_fields is None:
            exclude_fields = list(conflict_fields)

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
                
                # 获取数据库连接对象
                db = Tortoise.get_connection(self.connection_name)
                
                existing_records = await model_class.filter(
                    query
                ).using_db(db).all()
            else:
                existing_records = []
        
        # 创建模型实例
        instances = [model_class(**data) for data in filtered_data]
        
        # 使用 bulk_create
        # 如果没有update_fields，不执行更新操作（仅插入）
        if update_fields:
            await model_class.bulk_create(
                instances,
                on_conflict=conflict_fields,
                update_fields=update_fields
            )
        else:
            # 只执行插入操作，忽略冲突
            await model_class.bulk_create(
                instances,
                ignore_conflicts=True
            )
        
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
            key = tuple(data[field] for field in conflict_fields)
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
        force_use_orm: bool = False,
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
            force_use_orm: 强制使用 ORM 执行批量 upsert
            use_transaction: 是否使用事务（可选，默认使用实例配置的use_transaction）
        Returns:
            执行统计信息
        """
        
        start_time = datetime.now()
        
        try:
            # 获取冲突字段（需要在计算默认update_fields之前获取）
            if conflict_fields is None:
                conflict_fields = self._get_conflict_fields(model_class, conflict_fields)
            
            # 如果未提供exclude_fields，则使用conflict_fields作为默认排除字段
            if exclude_fields is None:
                exclude_fields = list(conflict_fields)
            
            # 如果未提供update_fields，则自动使用所有非冲突非排除字段作为默认更新字段
            if update_fields is None and data_list:
                # 获取所有字段
                all_fields = set(data_list[0].keys())
                # 获取冲突字段和排除字段的集合
                excluded_set = set(conflict_fields) | set(exclude_fields)
                # 计算默认更新字段：所有非冲突非排除字段
                update_fields = list(all_fields - excluded_set)
            
            # 移除事务分支，统一执行核心逻辑
            # 选择执行策略
            if not force_use_orm and len(data_list) > 50:
                method = "native_sql"
                result = await self._bulk_upsert_native_sql(
                    model_class, data_list, update_fields, 
                    exclude_fields, conflict_fields
                )
            else:
                method = "orm"
                result = await self._bulk_upsert_orm(
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
            
            logger.info(f"批量 upsert 完成: {response}")
            return response
            
        except IntegrityError as e:
            logger.error(f"数据完整性错误: {e}")
            raise
        except Exception as e:
            logger.error(f"批量 upsert 失败: {e}")
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
        fields_str = ', '.join(all_fields)
        
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
                    update_parts.append(f"{field} = {expression}")
                
                # 添加条件
                where_clause = f"WHERE {condition_field} = %s"
                values.append(condition_value)
                
                conflict_fields_str = ', '.join(conflict_fields)
                update_str = ', '.join(update_parts)
                
                sql = f"""
                INSERT INTO {table_name} ({fields_str}) 
                VALUES {', '.join(placeholders)}
                ON DUPLICATE KEY UPDATE
                {update_str}
                {where_clause}
                """
                
                affected = await self._execute_native_sql(
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
        logger.info(f"已切换数据库连接至: {connection_name}")


def get_db_managers():
    db_managers = {}
    for db in MYAPS_DBSET_LIST:
        db_managers[db] = DbManager(db)
    return db_managers

db_managers = get_db_managers()