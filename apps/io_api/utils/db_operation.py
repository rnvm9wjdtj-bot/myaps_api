import asyncio
import json
import time
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple

from fastapi import status
from pydantic import BaseModel as PydanticSchema
from tortoise.models import Model as TortoiseBaseModel

from apps.common.monitor.models import FailedOperation
from core.settings import LOG_LEVEL, MYAPS_DB_SET, MYAPS_DBSET_LIST
from globalobjects import RemindType, remind_manager
from globalobjects import logger as log_config
from globalobjects.db_manager import DbManager, get_db_managers

from .common import (
    convert_to_dict,
    format_data_for_logging,
    format_query_result,
    get_raw_input_data,
    standard_response,
)


@dataclass
class DbError:
    """数据库操作错误信息"""
    db_name: str
    error: str
    error_type: str


@dataclass
class DbResult:
    """单账套操作结果"""
    success: int
    data: List[Any]
    message: str
    meta: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def has_errors(self) -> bool:
        return self.meta.get('has_errors', False)
    
    @property
    def affected_rows(self) -> int:
        return self.meta.get('affected_rows', 0)
    
    @property
    def total(self) -> int:
        return self.meta.get('total', 0)
    
    @property
    def page_size(self) -> int:
        return self.meta.get('page_size', 0)
    
    @property
    def page_index(self) -> int:
        return self.meta.get('page_index', 0)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "meta": self.meta
        }
    
    def raise_error(self) -> None:
        """抛出错误"""
        if self.has_errors:
            error_msg = f"数据库操作错误: {self.message}"
            raise Exception(error_msg)


@dataclass
class MultiDbResult(DbResult):
    """多账套操作结果"""
    
    @property
    def success_db(self) -> List[str]:
        return self.meta.get('success_db', [])
    
    @property
    def failed_db(self) -> List[str]:
        return self.meta.get('failed_db', [])
    
    @property
    def errors(self) -> List[Dict[str, Any]]:
        return self.meta.get('errors', [])
    
    @property
    def is_success(self) -> bool:
        return self.success == 1 and len(self.errors) == 0
    
    def get_error(self, db_name: str) -> Optional[Dict[str, Any]]:
        """获取指定账套的错误信息"""
        for error in self.errors:
            if error.get('db_name') == db_name:
                return error
        return None
    
    def filter_success(self) -> List[Dict[str, Any]]:
        """过滤出成功的结果"""
        return [r for r in self.data if r.get('success')]
    
    def get_summary(self) -> Dict[str, Any]:
        """获取操作摘要"""
        return {
            "total_dbs": len(self.meta.get('db_names', [])),
            "success_dbs": len(self.success_db),
            "failed_dbs": len(self.failed_db),
            "affected_rows": self.affected_rows,
            "has_errors": self.has_errors
        }
    
    def raise_first_error(self) -> None:
        """抛出第一个错误"""
        if self.errors:
            first_error = self.errors[0]
            error_msg = f"数据库操作错误: {first_error.get('error', 'Unknown error')} (账套: {first_error.get('db_name', 'unknown')})"
            raise Exception(error_msg)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
            "meta": self.meta
        }


_TABLE_COLUMN_CACHE: Dict[str, Tuple[Set[str], float]] = {}
_TABLE_COLUMN_CACHE_TTL = 300.0


async def _get_table_columns(db_name: str, table_name: str) -> Set[str]:
    """
    获取数据库表的实际字段集合（带缓存）

    Args:
        db_name: 账套名称
        table_name: 表名

    Returns:
        字段名集合（小写）
    """
    cache_key = f"{db_name}.{table_name}"
    now = time.time()

    if cache_key in _TABLE_COLUMN_CACHE:
        cached_columns, cached_time = _TABLE_COLUMN_CACHE[cache_key]
        if now - cached_time < _TABLE_COLUMN_CACHE_TTL:
            return cached_columns

    db_manager = get_db_manager(db_name)
    conn = await db_manager._get_valid_connection()
    columns_result = await conn.execute_query(f"SHOW COLUMNS FROM `{table_name}`", [])

    db_field_names = set()
    for column in columns_result[1]:
        field_name = column.get('Field', column.get('field', '')).lower()
        if field_name:
            db_field_names.add(field_name)

    _TABLE_COLUMN_CACHE[cache_key] = (db_field_names, now)
    return db_field_names


def _invalidate_table_column_cache(db_name: str = None, table_name: str = None) -> None:
    """
    失效表字段缓存

    当写入因 "Unknown column" 失败时调用：说明表结构可能已变更（如 ALTER TABLE 新增字段），
    缓存中的旧字段集合已过期，清除后下次查询将重新获取真实字段。

    Args:
        db_name: 账套名称（None 表示匹配所有账套）
        table_name: 表名（None 表示匹配所有表）
    """
    if db_name is None and table_name is None:
        _TABLE_COLUMN_CACHE.clear()
        return

    prefix = f"{db_name}." if db_name else None
    suffix = f".{table_name}" if table_name else None

    for key in list(_TABLE_COLUMN_CACHE.keys()):
        if prefix is not None and suffix is not None:
            if key == f"{db_name}.{table_name}":
                _TABLE_COLUMN_CACHE.pop(key, None)
        elif prefix is not None:
            if key.startswith(prefix):
                _TABLE_COLUMN_CACHE.pop(key, None)
        elif suffix is not None:
            if key.endswith(suffix):
                _TABLE_COLUMN_CACHE.pop(key, None)


def _filter_dict_by_table_fields(
    data: Dict[str, Any],
    table_columns: Set[str],
    table_name: str,
    operation_name: str
) -> Dict[str, Any]:
    """
    过滤字典中不在数据库表中的字段

    Args:
        data: 原始数据字典
        table_columns: 数据库表字段集合（小写）
        table_name: 表名（用于日志）
        operation_name: 操作名称（用于日志）

    Returns:
        过滤后的数据字典
    """
    original_keys = set(data.keys())
    filtered_keys = {k for k in original_keys if k.lower() in table_columns}
    missing_keys = original_keys - filtered_keys

    if missing_keys:
        logger.warning(
            f"{operation_name}检测到数据字段与数据库表字段存在差异",
            f"表={table_name}",
            f"数据中存在但表中不存在的字段={missing_keys}，这些字段将被忽略"
        )

    return {k: v for k, v in data.items() if k in filtered_keys}


def db_managers():
    """
    获取数据库管理器实例字典
    每次调用都会返回最新的实例字典，确保使用当前事件循环的连接
    """
    return get_db_managers()


def get_db_manager(db_name):
    """
    获取数据库管理器实例，确保使用当前事件循环的连接

    Args:
        db_name: 数据库连接名称

    Returns:
        DbManager 实例
    """
    return get_db_managers()[db_name]


async def _filter_data_by_table(
    db_name: str,
    table_name: str,
    data: Dict[str, Any],
    operation_name: str
) -> Dict[str, Any]:
    """
    根据数据库表的实际字段过滤数据字典，移除表中不存在的字段

    Args:
        db_name: 账套名称
        table_name: 表名
        data: 原始数据字典
        operation_name: 操作名称（用于日志）

    Returns:
        过滤后的数据字典
    """
    try:
        table_columns = await _get_table_columns(db_name, table_name)
        return _filter_dict_by_table_fields(data, table_columns, table_name, operation_name)
    except Exception as e:
        logger.warning(
            f"{operation_name}获取表字段失败，跳过字段过滤",
            f"{table_name}@{db_name}",
            str(e)
        )
        return data


from ..models import TABLE_MODEL_MAPPING


logger = log_config.get_logger(__name__, level=LOG_LEVEL)


@dataclass
class DbExecutionResult:
    """单账套执行结果"""
    db_name: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_type: Optional[str] = None


def build_multi_db_response(
    results: List[DbExecutionResult],
    valid_dbs: List[str],
    operation_name: str,
    extra_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    从多账套执行结果构建统一响应格式

    Args:
        results: execute_with_db_fault_tolerance 返回的执行结果列表
        valid_dbs: 有效账套列表
        operation_name: 操作名称（用于日志）
        extra_meta: 额外的 meta 字段

    Returns:
        Dict[str, Any]: 统一格式的返回值
    """
    success_db = [r.db_name for r in results if r.success]
    errors = [{"db_name": r.db_name, "error": r.error, "error_type": r.error_type}
              for r in results if not r.success]
    has_errors = len(errors) > 0

    success_value = calc_success_value(success_db, valid_dbs, has_errors)

    base_meta = {
        "db_names": valid_dbs,
        "success_db": success_db,
        "has_errors": has_errors,
    }
    if errors:
        base_meta["errors"] = errors
    if extra_meta:
        base_meta.update(extra_meta)

    return {
        "success": success_value,
        "meta": base_meta
    }


async def execute_with_db_fault_tolerance(
    valid_dbs: List[str],
    operation_func: Callable,
    operation_name: str,
    on_db_error: Literal["continue", "abort"] = "continue",
    **kwargs
) -> Tuple[List[DbExecutionResult], List[Dict[str, Any]]]:
    """
    多账套容错执行辅助函数
    
    Args:
        valid_dbs: 有效账套列表
        operation_func: 单账套执行函数
        operation_name: 操作名称（用于日志）
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断
        **kwargs: 传递给 operation_func 的其他参数
        
    Returns:
        Tuple[执行结果列表, 错误汇总列表]
    """
    results: List[DbExecutionResult] = []
    errors: List[Dict[str, Any]] = []
    
    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)
        try:
            result = await operation_func(db_manager, **kwargs)
            results.append(DbExecutionResult(
                db_name=db_name,
                success=True,
                result=result
            ))
        except Exception as e:
            error_info = {
                "db_name": db_name,
                "error": str(e),
                "error_type": e.__class__.__name__
            }
            errors.append(error_info)
            results.append(DbExecutionResult(
                db_name=db_name,
                success=False,
                error=str(e),
                error_type=e.__class__.__name__
            ))
            logger.fail(operation_name, db_name, str(e))
            
            if on_db_error == "abort":
                logger.warning(operation_name, f"@{valid_dbs}", f"因 {db_name} 出错中断，剩余账套未执行")
                break
    
    return results, errors


def retry_on_connection_error(max_retries: int = 3, retry_delay: float = 1.0):
    """
    连接错误重试装饰器
    当检测到 "Cannot acquire connection after closing pool" 等连接错误时，
    自动刷新连接并重试，所有重试都失败后持久化到SQLite并告警
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 重试延迟（秒）
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从参数中提取 db_names（第一个参数通常是 db_names）
            db_names = None
            if args and isinstance(args[0], str):
                db_names = args[0]
            elif 'db_names' in kwargs:
                db_names = kwargs['db_names']
            elif 'db_name' in kwargs:
                db_names = kwargs['db_name']
            
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_str = str(e)
                    error_str_upper = error_str.upper()
                    is_operational_error = "OperationalError" in str(type(e))
                    is_operational_connection_error = is_operational_error and (
                        'CONNECTION' in error_str_upper or
                        'CONNECT' in error_str_upper or
                        'POOL' in error_str_upper or
                        'TIMEOUT' in error_str_upper or
                        'NETWORK' in error_str_upper or
                        'HOST' in error_str_upper or
                        'PORT' in error_str_upper or
                        'SERVER' in error_str_upper
                    )
                    
                    # 检查是否是连接相关错误
                    is_connection_error = (
                        "Cannot acquire connection after closing pool" in error_str or
                        is_operational_connection_error or
                        "NoneType" in error_str or
                        "closed" in error_str.lower()
                    )
                    
                    if not is_connection_error or attempt >= max_retries:
                        # 如果不是连接错误或已达到最大重试次数
                        logger.fail(
                            f"执行 {func.__name__}",
                            f"（尝试 {attempt + 1}/{max_retries + 1}）",
                            error_str
                        )
                        
                        # 如果是连接错误，持久化到SQLite并告警
                        if is_connection_error and db_names:
                            valid_dbs = validate_databases(db_names)
                            operation_id = str(uuid.uuid4())

                            def safe_serialize(obj):
                                try:
                                    return json.dumps(obj, default=str)
                                except Exception:
                                    return str(obj)

                            args_json = safe_serialize(args)
                            kwargs_json = safe_serialize(kwargs)

                            error_summary_parts = []
                            for db_name in valid_dbs:
                                try:
                                    await FailedOperation.create(
                                        operation_id=operation_id,
                                        timestamp=datetime.now(timezone.utc),
                                        db_name=db_name,
                                        function_name=func.__name__,
                                        args_json=args_json,
                                        kwargs_json=kwargs_json,
                                        error_message=error_str,
                                        error_type=e.__class__.__name__,
                                        status="pending",
                                        retry_count=0,
                                        max_retries=10,
                                        next_retry_time=datetime.now(timezone.utc) + timedelta(minutes=5),
                                    )
                                    error_summary_parts.append(f"{db_name}: {error_str}")
                                    logger.info(
                                        f"已持久化失败操作",
                                        f"{db_name}/{func.__name__}",
                                        f"operation_id={operation_id}"
                                    )
                                except Exception as persist_error:
                                    logger.error(
                                        f"持久化失败操作失败",
                                        f"{db_name}/{func.__name__}",
                                        str(persist_error)
                                    )

                            if error_summary_parts:
                                error_summary = "; ".join(error_summary_parts)
                                await remind_manager.trigger_remind(
                                    RemindType.DB_CONNECTION_BREAK,
                                    {
                                        "operation_id": operation_id,
                                        "db_names": valid_dbs,
                                        "db_count": len(valid_dbs),
                                        "function": func.__name__,
                                        "error": error_str,
                                        "error_summary": error_summary,
                                        "retry_count": attempt + 1,
                                        "next_retry": "5分钟后"
                                    }
                                )

                        raise
                    
                    # 记录警告日志
                    logger.warning(
                        f"检测到连接错误，准备重试（尝试 {attempt + 1}/{max_retries + 1}）",
                        f"{func.__name__}",
                        error_str
                    )
                    
                    # 尝试刷新连接
                    if db_names:
                        valid_dbs = validate_databases(db_names)
                        for db_name in valid_dbs:
                            try:
                                db_manager = get_db_manager(db_name)
                                await db_manager.refresh_connection(fast_mode=True)
                                logger.info(
                                    f"已尝试刷新连接",
                                    f"{db_name}",
                                    f"为下一次重试做准备"
                                )
                            except Exception as refresh_error:
                                logger.error(
                                    f"刷新连接失败",
                                    f"{db_name}",
                                    str(refresh_error)
                                )
                    
                    # 等待一段时间后重试
                    await asyncio.sleep(retry_delay * (attempt + 1))
            
            # 如果到达这里，说明所有重试都失败了
            raise last_exception
        
        return wrapper
    return decorator



def process_model_or_tablename(model_or_tablename: TortoiseBaseModel | str) -> Tuple[Optional[TortoiseBaseModel], str]:
    """
    处理model_or_tablename参数，将其转换为模型类和表名
    
    Args:
        model_or_tablename: 模型类或表名
        
    Returns:
        Tuple[Optional[TortoiseBaseModel], str]: 模型类（如果是表名且存在对应模型）和表名
    """
    if isinstance(model_or_tablename, TortoiseBaseModel):
        return model_or_tablename, model_or_tablename._meta.db_table
    else:
        table_name = model_or_tablename
        if table_name not in TABLE_MODEL_MAPPING.keys():

            return None, table_name
        else:
            return TABLE_MODEL_MAPPING[table_name], table_name


@dataclass
class ProcessedData:
    """处理后的数据类，统一管理不同类型的数据"""
    processed_data: dict  # 处理后的数据（用于更新）
    create_data: dict     # 创建数据（深拷贝，用于创建）
    raw_input_data: Any   # model_validator之前的原始数据


def validate_databases(db_name: str) -> List[str]:
    """
    验证账套是否存在
    
    Args:
        db_name: 账套名称，支持逗号分隔的多个账套
        
    Returns:
        有效的账套名称列表
    """
    if isinstance(db_name, list):
        return [db for db in db_name if db in MYAPS_DBSET_LIST]
    
    db_names = [name.strip() for name in db_name.split(",") if name.strip()]
    valid_dbs = [db for db in db_names if db in MYAPS_DBSET_LIST]
    return valid_dbs


def calc_success_value(success_db: List, valid_dbs: List, has_errors: bool) -> int:
    """
    计算多账套操作的 success 值
    
    Args:
        success_db: 成功的账套列表
        valid_dbs: 有效账套列表
        has_errors: 是否有错误
        
    Returns:
        1: 全部成功
        0.5: 部分成功
        0: 全部失败
    """
    if not success_db and not valid_dbs:
        return 0
    elif has_errors and success_db:
        return 0.5
    elif has_errors and not success_db:
        return 0
    else:
        return 1



@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_exec_sql(db_name: str, sql: str, params: Optional[List[Any]] = None, description: str = '') -> DbResult:
    """
    执行原始SQL语句

    Args:
        db_name: 数据库连接名称
        sql: 要执行的SQL语句
        params: SQL参数列表（可选）

    Returns:
        DbResult: 统一格式的返回值
    """
    valid_dbs = validate_databases(db_name)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_name}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_name}, available_dbs: {MYAPS_DB_SET}")
    valid_db = valid_dbs[0]

    db_manager = get_db_manager(valid_db)

    async def _make_request():
        return await db_manager._execute_native_sql(
            sql=sql,
            params=params if params is not None else [],
            description=f"执行SQL {description}..."
        )

    count, data_list = await _execute_with_retry(
        db_manager=db_manager,
        coro_func=_make_request,
        table_name="",
        db_name=valid_db
    )

    return DbResult(
        success=1,
        data=data_list,
        message=f"执行SQL成功，影响{count}条记录",
        meta={
            "affected_rows": count,
            "db_names": [valid_db],
            "table_name": ""
        }
    )


    
@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_query(
    db_name: str,
    model_or_tablename: TortoiseBaseModel | str,
    select="*",
    filter_string: str = '',
    order_string: str = '',
    page_size: int = 1000,
    page_index: int = 1
) -> DbResult:
    """
    查询数据

    Args:
        db_name: 数据库连接名称
        model_or_tablename: 模型类或表名
        select: 要查询的字段，默认为 "*"
        filter_string: WHERE子句，用于指定查询条件
        order_string: ORDER BY子句，用于指定排序
        page_size: 每页大小，默认为 1000
        page_index: 页码，默认为 1

    Returns:
        DbResult: 统一格式的返回值
    """
    valid_dbs = validate_databases(db_name)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_name}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_name}, available_dbs: {MYAPS_DB_SET}")
    valid_db = valid_dbs[0]

    db_manager = get_db_manager(valid_db)
    _, table_name = process_model_or_tablename(model_or_tablename)

    query_result = await db_manager.query_data(
        table_name=table_name,
        select_fields=select,
        filter_string=filter_string,
        order_string=order_string,
        page_size=page_size,
        page_index=page_index,
    )
    formatted_data = [format_query_result(row) for row in query_result['data']]
    total = query_result['total']
    
    return DbResult(
        success=1,
        data=formatted_data,
        message=f"查询成功，共{total}条记录",
        meta={
            "affected_rows": total,
            "page_size": page_size,
            "page_index": page_index,
            "db_names": [valid_db],
            "table_name": table_name
        }
    )


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_query_cursor(
    db_name: str,
    model_or_tablename: TortoiseBaseModel | str,
    select="*",
    filter_string: str = '',
    order_fields: List[Tuple[str, str]] = None,
    page_size: int = 1000,
    cursor_values: Optional[Dict[str, Any]] = None,
) -> DbResult:
    """
    游标分页查询，避免 LIMIT/OFFSET 的幻读问题

    与 db_query 的 OFFSET 分页不同，游标分页使用排序字段的上次最大值作为游标，
    每次查询追加 WHERE 条件而非 OFFSET，不受并发插入/删除影响。

    Args:
        db_name: 数据库连接名称
        model_or_tablename: 模型类或表名
        select: 要查询的字段，默认为 "*"
        filter_string: WHERE子句，用于指定查询条件
        order_fields: 排序字段列表，每个元素为 (字段名, 'ASC'|'DESC')，
                      例如 [('MaterialNo', 'ASC'), ('DateStr', 'ASC')]
                      必须指定，用于构建游标条件和 ORDER BY 子句。
                      注意：排序字段必须是 NOT NULL 列且包含在 select 字段中，
                      否则游标值为 NULL 时无法生成正确的游标条件，将抛出 ValueError。
        page_size: 每页大小，默认为 1000
        cursor_values: 游标值字典，键为排序字段名，值为上一页最后一条记录的对应字段值。
                       首页查询时传 None。

    Returns:
        DbResult: 统一格式的返回值，meta 中额外包含：
            - has_more: 是否还有更多数据
            - cursor_values: 本页最后一条记录的排序字段值，供下一页查询使用
    """
    valid_dbs = validate_databases(db_name)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_name}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_name}, available_dbs: {MYAPS_DB_SET}")
    valid_db = valid_dbs[0]

    db_manager = get_db_manager(valid_db)
    _, table_name = process_model_or_tablename(model_or_tablename)

    query_result = await db_manager.query_data_cursor(
        table_name=table_name,
        select_fields=select,
        filter_string=filter_string,
        order_fields=order_fields,
        page_size=page_size,
        cursor_values=cursor_values,
    )
    formatted_data = [format_query_result(row) for row in query_result['data']]

    has_more = query_result.get('has_more', False)
    next_cursor = query_result.get('cursor_values')

    return DbResult(
        success=1,
        data=formatted_data,
        message=f"游标分页查询成功，返回{len(formatted_data)}条记录，{'还有更多' if has_more else '已到末页'}",
        meta={
            "affected_rows": len(formatted_data),
            "page_size": page_size,
            "db_names": [valid_db],
            "table_name": table_name,
            "has_more": has_more,
            "cursor_values": next_cursor,
        }
    )



async def preprocess_data(
    data_list: List[PydanticSchema | Dict[str, Any]],
    model_class: Optional[TortoiseBaseModel] = None,
    conflict_fields: Optional[Tuple[str, ...]] = None,
    exclude_none: bool = True
) -> List[ProcessedData]:
    """
    预处理数据，将Pydantic模型转换为字典，并可选地基于冲突字段去重
    
    Args:
        data_list: 原始数据列表，可以是PydanticSchema对象或字典
        model_class: Tortoise模型类，用于过滤字段（可选）
        conflict_fields: 冲突字段元组，用于去重（可选）
        exclude_none: 是否排除None值
        
    Returns:
        预处理后的数据列表
    """
    processed_list = []
    
    # 获取模型字段列表和字段类型（如果提供了模型类）
    model_fields = set()
    model_field_types = {}
    if model_class:
        model_fields = set(model_class._meta.fields_map.keys())
        for field_name, field in model_class._meta.fields_map.items():
            model_field_types[field_name] = type(field)
    
    for data_item in data_list:
        # 获取原始输入数据
        raw_input_data = get_raw_input_data(data_item)
        # 转换为字典
        processed_dict = convert_to_dict(data_item, exclude_none=exclude_none)
        
        # 如果提供了模型类，过滤掉不在模型中的字段，并处理日期时间字段
        if model_class:
            filtered_dict = {}
            for key, value in processed_dict.items():
                if key in model_fields:
                    # 处理日期时间字段
                    from tortoise.fields import DatetimeField
                    if key in model_field_types and model_field_types[key] == DatetimeField and isinstance(value, str):
                        # 尝试将字符串转换为datetime对象
                        from datetime import datetime
                        try:
                            # 尝试不同的日期时间格式
                            if '.' in value:
                                # 包含毫秒的格式
                                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
                            else:
                                # 不包含毫秒的格式
                                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            # 如果转换失败，保留原始值
                            pass
                    filtered_dict[key] = value
            processed_dict = filtered_dict
        
        # 深拷贝用于创建操作
        create_dict = deepcopy(processed_dict)
        # 添加到处理列表
        processed_list.append(ProcessedData(
            processed_data=processed_dict,
            create_data=create_dict,
            raw_input_data=raw_input_data
        ))
    
    # 如果提供了冲突字段，进行去重处理
    if conflict_fields:
        # 使用字典去重，保留最后出现的记录
        unique_dict = {}
        for item in processed_list:
            # 创建冲突键
            conflict_key = tuple(item.processed_data.get(field) for field in conflict_fields)
            # 保留最后出现的记录
            unique_dict[conflict_key] = item
        # 转换回列表
        processed_list = list(unique_dict.values())
    
    return processed_list


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_supsert(
    db_names: str,
    model_or_tablename: TortoiseBaseModel | str,
    data_item: PydanticSchema | Dict[str, Any],
    use_rawdata: bool = True,
    on_db_error: Literal["continue", "abort"] = "continue"
) -> MultiDbResult:
    """
    通用单条数据写入操作，支持创建和更新，整体逻辑类似于旧版的逐条创建或更新。比 db_bupsert 颗粒度更细，但会损失一定性能

    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        data_item: 数据，字典或PydanticSchema对象
        use_rawdata: 是否使用原始数据（若传入的数据为PydanticSchema对象，默认使用未被 validator 处理的数据）
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断

    Returns:
        MultiDbResult: 统一格式的返回值
    """
    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        raise ValueError(f"操作失败：未找到对应模型，input_table_name: {table_name}, available_tables: {list(TABLE_MODEL_MAPPING.keys())}")

    if isinstance(data_item, PydanticSchema):
        if use_rawdata:
            data = get_raw_input_data(data_item)
        else:
            data = data_item.model_dump(exclude_none=True)
    else:
        data = data_item    # 若为字典则直接使用

    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_names}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_names}, available_dbs: {MYAPS_DB_SET}")

    success_db = []
    create_count_total = 0
    update_count_total = 0
    errors = []

    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)
        try:
            async def _make_request():
                # 每次执行前重新过滤，确保表结构变化（如 ALTER TABLE 新增字段）后重试能感知新字段
                filtered_data = await _filter_data_by_table(db_name, table_name, data, "单条upsert")

                # 防御：数据字段全部不存在于表中时，single_upsert 会因冲突字段为空生成无效 WHERE 语法
                if not filtered_data:
                    raise ValueError(
                        f"数据字段 {sorted(data.keys())} 在表 {table_name}@{db_name} 中均不存在，"
                        "无法执行单条upsert，请检查表结构"
                    )

                return await db_manager.single_upsert(
                    model_class=mdl,
                    data=filtered_data,
                )

            result = await _execute_with_retry(
                db_manager=db_manager,
                coro_func=_make_request,
                table_name=table_name,
                db_name=db_name
            )

            if result['success']:
                success_db.append(db_name)
                create_count_total += result['inserted']
                update_count_total += result['updated']
        except Exception as e:
            error_info = {"db_name": db_name, "error": str(e), "error_type": e.__class__.__name__}
            errors.append(error_info)
            logger.fail("单条upsert", f"{table_name}@{db_name}", str(e))
            if on_db_error == "abort":
                logger.warning("单条upsert", f"@{db_names}", f"因 {db_name} 出错中断")
                break

    has_errors = len(errors) > 0
    if has_errors:
        error_msg = f"，其中 {len(errors)} 个账套出错"
    else:
        error_msg = ""

    success_value = calc_success_value(success_db, valid_dbs, has_errors)

    return MultiDbResult(
        success=success_value,
        data=[data_item],
        message=f"数据写入成功{error_msg}，新增{create_count_total}条，修改{update_count_total}条",
        meta={
            "affected_rows": create_count_total + update_count_total,
            "created_rows": create_count_total,
            "updated_rows": update_count_total,
            "db_names": valid_dbs,
            "success_db": success_db,
            "table_name": table_name,
            "has_errors": has_errors,
            "errors": errors
        }
    )


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_bupsert(
    db_names: str,
    model_or_tablename: TortoiseBaseModel | str,
    data_list: List[PydanticSchema | Dict[str, Any]],
    use_orm_or_sql: Literal["orm", "sql", "auto"] = "sql",
    exclude_none: bool = True,
    batch_size: int = 1000,
    on_batch_error: Literal["continue", "skip"] = "continue",
    on_db_error: Literal["continue", "abort"] = "continue"
) -> MultiDbResult:
    """
    通用批量写入操作，支持创建和更新
    融合了多账套处理逻辑与db_manager.py的高效数据库操作
    Args:
        db_names: 账套名称，支持逗号分隔的多个账套
        model_or_tablename: 模型类或表名
        data_list: 数据列表，可以是PydanticSchema对象或字典
        use_orm_or_sql: 使用ORM还是SQL，可选值："orm", "sql", "auto"
        exclude_none: 是否排除None值
        batch_size: 批次大小，默认为1000
        on_batch_error: 批次出错时的策略，"continue"继续下一批次，"skip"跳过后续所有批次
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断
        
    Returns:
        MultiDbResult: 统一格式的返回值
    """
    # 验证账套
    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        logger.fail("数据库验证", "", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_names}, available_dbs: {MYAPS_DB_SET}")

    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        raise ValueError(f"操作失败：未找到对应模型，input_table_name: {table_name}, available_tables: {list(TABLE_MODEL_MAPPING.keys())}")

    origin_total = len(data_list)
    # 记录日志
    
    # 获取冲突字段
    model_key = DbManager._get_conflict_fields(mdl)
    
    # 预处理数据，并基于冲突字段去重
    processed_data_list = await preprocess_data(data_list, model_class=mdl, conflict_fields=model_key, exclude_none=exclude_none)
    # 初始化统计信息
    success_db = []
    create_count_total = 0
    update_count_total = 0

    # 准备upsert数据
    upsert_data_list = []
    for item in processed_data_list:
        upsert_data_list.append(item.processed_data)

    # 格式化数据用于日志记录，将枚举和Decimal等类型转换为字符串
    formatted_data = format_data_for_logging(upsert_data_list)
    logger.insert("批量upsert", mdl._meta.db_table, f"接收{origin_total}条，去重后{len(upsert_data_list)}")
    
    # 检查upsert_data_list是否为空
    if not upsert_data_list:
        logger.info_console(f"批量upsert {mdl._meta.db_table} 没有可处理的数据")
        return MultiDbResult(
            success=1,
            data=data_list,
            message=f"生效{len(success_db)}个账套，无数据处理",
            meta={"origin_total": origin_total, "success_db": success_db}
        )
    
    # 收集所有记录中的所有字段，确保update_fields包含所有可能的字段
    all_fields = set()
    for item in upsert_data_list:
        all_fields.update(item.keys())
    update_fields = [field for field in all_fields if field not in model_key]
    
    # 排除字段（自增ID或不需要upsert的字段）
    exclude_fields = []
    if hasattr(mdl._meta, 'pk_attr'):
        pk_attr = mdl._meta.pk_attr
        # 检查主键是否是自增类型
        pk_field = mdl._meta.fields_map.get(pk_attr)
        if pk_field and pk_field.generated:
            exclude_fields.append(pk_attr)
            if pk_attr in update_fields:
                update_fields.remove(pk_attr)
    
    # 处理每个账套，使用专属的DbManager实例
    db_results = []
    
    for db_name in valid_dbs:
        # 获取该账套的专属DbManager实例
        db_manager = get_db_manager(db_name)
        
        db_create_count = 0
        db_update_count = 0
        db_errors = []
        db_skipped_count = 0
        db_skipped_batches = []
        db_success = True
        
        total_batches = (len(upsert_data_list) + batch_size - 1) // batch_size
        try:
            for i in range(total_batches):
                start_idx = i * batch_size
                end_idx = min((i + 1) * batch_size, len(upsert_data_list))
                batch_data = upsert_data_list[start_idx:end_idx]
                
                try:
                    async def _make_request():
                        return await db_manager.bulk_upsert(
                            model_class=mdl,
                            data_list=batch_data,
                            update_fields=update_fields,
                            exclude_fields=exclude_fields,
                            conflict_fields=tuple(model_key) if model_key else None,
                            use_orm_or_sql=use_orm_or_sql
                        )
                    
                    result = await _execute_with_retry(
                        db_manager=db_manager,
                        coro_func=_make_request,
                        table_name=table_name,
                        db_name=db_name
                    )

                    batch_create = result.get("inserted") or 0
                    batch_update = result.get("updated") or 0
                    db_create_count = (db_create_count or 0) + batch_create
                    db_update_count = (db_update_count or 0) + batch_update
                    logger.insert("账套批次生效", f"{db_name} (批次{i+1}/{total_batches})", f"新增{batch_create}条，修改{batch_update}条")

                    # 消费底层写库失败信息，避免静默丢失数据。两类来源：
                    # 1) _bulk_upsert_native_sql 批内吞错后累计的 errors 列表；
                    # 2) with_transaction 非事务模式整体失败返回的 {success: False, error: ...} 字典
                    batch_errors = result.get("errors") or []
                    if result.get("success") is False and result.get("error"):
                        batch_errors.append({"batch": i + 1, "error": result["error"]})
                    if batch_errors:
                        db_errors.extend(batch_errors)
                        db_success = False
                        db_skipped_count += len(batch_data)
                        db_skipped_batches.append(i + 1)
                        logger.fail("账套批次失败", f"{db_name} (批次{i+1}/{total_batches})", str(batch_errors))
                except Exception as batch_error:
                    db_errors.append({"batch": i + 1, "error": str(batch_error), "skipped_count": len(batch_data)})
                    db_skipped_count += len(batch_data)
                    db_skipped_batches.append(i + 1)
                    logger.fail("账套批次失败", f"{db_name} (批次{i+1}/{total_batches})", str(batch_error))
                    if on_batch_error == "skip":
                        remaining_batches = total_batches - i - 1
                        remaining_count = sum(len(upsert_data_list[j * batch_size:min((j + 1) * batch_size, len(upsert_data_list))]) for j in range(i + 1, total_batches))
                        db_skipped_count += remaining_count
                        db_skipped_batches.extend(range(i + 2, total_batches + 1))
                        logger.warning("批量upsert", f"{db_name} 跳过后续{remaining_batches}个批次", f"跳过{remaining_count}条数据")
                        break
        except Exception as db_error:
            db_success = False
            db_error_info = {"db_name": db_name, "error": str(db_error), "error_type": db_error.__class__.__name__}
            logger.fail("账套批量upsert", f"{table_name}@{db_name}", str(db_error))
            if on_db_error == "abort":
                logger.warning("批量upsert", f"@{db_names}", f"因 {db_name} 出错中断，剩余账套未执行")
                db_results.append({
                    "db_name": db_name,
                    "success": False,
                    "create": 0,
                    "update": 0,
                    "errors": [db_error_info],
                    "skipped_count": len(upsert_data_list),
                    "skipped_batches": list(range(1, total_batches + 1))
                })
                break
        
        create_count_total = (create_count_total or 0) + (db_create_count or 0)
        update_count_total = (update_count_total or 0) + (db_update_count or 0)
        logger.insert("账套生效", db_name, f"新增{db_create_count or 0}条，修改{db_update_count or 0}条")
        db_results.append({
            "db_name": db_name,
            "success": db_success,
            "create": db_create_count,
            "update": db_update_count,
            "errors": db_errors,
            "skipped_count": db_skipped_count,
            "skipped_batches": db_skipped_batches
        })
    
    success_db_names = [r["db_name"] for r in db_results if r["success"]]
    has_errors = any(not r.get("success", True) or len(r["errors"]) > 0 for r in db_results)

    logger.success("批量upsert", f"{table_name}@{db_names}", f"生效{len(db_results)}个账套，新增{create_count_total}条，修改{update_count_total}条")

    success_value = calc_success_value(success_db_names, valid_dbs, has_errors)

    if has_errors:
        error_summary = []
        for r in db_results:
            if r["errors"]:
                error_summary.append({
                    "db_name": r["db_name"],
                    "errors": r["errors"],
                    "skipped_count": r["skipped_count"],
                    "skipped_batches": r["skipped_batches"]
                })
        logger.warning("批量upsert", f"{table_name}@{db_names}", f"存在错误批次")
        return MultiDbResult(
            success=success_value,
            data=data_list,
            message=f"生效{len(db_results)}个账套，总计新增{create_count_total}条，修改{update_count_total}条，但存在错误",
            meta={
                "affected_rows": (create_count_total or 0) + (update_count_total or 0),
                "created_rows": create_count_total or 0,
                "updated_rows": update_count_total or 0,
                "origin_total": origin_total,
                "distinct_total": len(processed_data_list),
                "db_names": valid_dbs,
                "table_name": table_name,
                "has_errors": True,
                "error_summary": error_summary,
                "total_skipped_count": sum(r.get("skipped_count") or 0 for r in db_results)
            }
        )

    return MultiDbResult(
        success=success_value,
        data=data_list,
        message=f"生效{len(db_results)}个账套，总计新增{create_count_total}条，修改{update_count_total}条",
        meta={
            "affected_rows": (create_count_total or 0) + (update_count_total or 0),
            "created_rows": create_count_total or 0,
            "updated_rows": update_count_total or 0,
            "origin_total": origin_total,
            "distinct_total": len(processed_data_list),
            "db_names": valid_dbs,
            "table_name": table_name
        }
    )


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_delete(
    db_names: str,
    model_or_tablename: TortoiseBaseModel | str,
    filter_string: str | None = None,
    on_db_error: Literal["continue", "abort"] = "continue"
) -> MultiDbResult:
    """
    执行SQL删除操作
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        filter_string: WHERE子句，用于指定删除条件；若为None则清空整个表
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断

    Returns:
        MultiDbResult: 统一格式的返回值
    """
    _, table_name = process_model_or_tablename(model_or_tablename)
    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_names}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_names}, available_dbs: {MYAPS_DB_SET}")

    total_count = 0
    is_truncate = filter_string is None
    success_db = []
    errors = []
    
    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)
        try:
            async def _make_request():
                return await db_manager.delete_data(table_name=table_name, filter_string=filter_string or '')
            
            exe_result = await _execute_with_retry(
                db_manager=db_manager,
                coro_func=_make_request,
                table_name=table_name,
                db_name=db_name
            )
            count = exe_result.get("affected_rows", 0)
            total_count += count
            success_db.append(db_name)
            logger.delete(f"{table_name}@{db_name}", "ALL DATA" if is_truncate else filter_string, count)
        except Exception as e:
            error_info = {"db_name": db_name, "error": str(e), "error_type": e.__class__.__name__}
            errors.append(error_info)
            logger.fail("SQL删除", f"{table_name}@{db_name}", str(e))
            if on_db_error == "abort":
                logger.warning("SQL删除", f"@{db_names}", f"因 {db_name} 出错中断")
                break
    
    has_errors = len(errors) > 0
    if has_errors:
        error_msg = f"，其中 {len(errors)} 个账套出错"
    else:
        error_msg = ""

    success_value = calc_success_value(success_db, valid_dbs, has_errors)

    logger.success("SQL删除", f"{table_name}@{db_names}", f"共删除{total_count}条{error_msg}")
    return MultiDbResult(
        success=success_value,
        data=[],
        message=f"删除成功{error_msg}，共删除{total_count}条记录",
        meta={
            "affected_rows": total_count, 
            "db_names": valid_dbs,
            "success_db": success_db,
            "table_name": table_name,
            "is_truncate": is_truncate,
            "has_errors": has_errors,
            "errors": errors
        }
    )



@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def call_dbprocdure(
    db_names: str,
    procedure_name: str,
    params_list: List[List[Any]] = [[]],
    on_db_error: Literal["continue", "abort"] = "continue"
) -> MultiDbResult:
    """
    调用数据库存储过程
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        procedure_name: 存储过程名称
        params_list: 存储过程参数列表，每个元素是一个参数列表
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断

    Returns:
        MultiDbResult: 统一格式的返回值
    """
    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        logger.fail("数据库验证", f"{db_names}", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_names}, available_dbs: {MYAPS_DB_SET}")

    async def single_db_operation(db_manager: DbManager) -> Dict[str, Any]:
        return await db_manager.call_stored_procedure(procedure_name=procedure_name, params_list=params_list)

    results, errors = await execute_with_db_fault_tolerance(
        valid_dbs=valid_dbs,
        operation_func=single_db_operation,
        operation_name=f"存储过程调用 {procedure_name}",
        on_db_error=on_db_error
    )

    total_affect_rows = sum(r.result.get('affected_rows', 0) for r in results if r.success and r.result)

    response = build_multi_db_response(
        results=results,
        valid_dbs=valid_dbs,
        operation_name=f"存储过程调用 {procedure_name}",
        extra_meta={
            "affected_rows": total_affect_rows,
            "procedure_name": procedure_name
        }
    )

    response["data"] = []
    response["message"] = f"存储过程调用成功，影响{total_affect_rows}条记录"

    return MultiDbResult(**response)


# 定义需要重试的瞬态错误关键字
TRANSIENT_ERROR_KEYWORDS = {
    "Packet sequence number",
    "Lost connection",
    "Connection reset",
    "Can't connect to MySQL server",
    "server closed the connection unexpectedly",
    "MySQL server has gone away",
    "Unexpected end of stream",
}

async def _execute_with_retry(db_manager, coro_func=None, table_name="", db_name="", 
                                mdl=None, index_dict=None, new_values_dict=None, not_found_behavior=None):
    """
    带重试的数据库操作执行
    
    支持两种调用方式：
    1. 通过 coro_func 参数传入协程函数（通用方式）
    2. 通过 mdl, index_dict 等参数（db_update_by_index 专用）
    """
    max_retries = 2
    retry_delay = 0.5  # 初始重试延迟（秒）
    
    for attempt in range(max_retries + 1):
        try:
            # 优先使用 coro_func（通用方式）
            if coro_func is not None:
                return await coro_func()
            # 兼容 db_update_by_index 的旧调用方式
            elif mdl is not None:
                return await db_manager.update_by_index(
                    model_class=mdl,
                    index_dict=index_dict,
                    new_values_dict=new_values_dict,
                    not_found_behavior=not_found_behavior
                )
            else:
                raise ValueError("必须提供 coro_func 或数据库操作参数")
        except Exception as e:
            error_msg = str(e)

            # 写入报"未知列"通常意味着表结构已变更（如 ALTER TABLE 新增字段），
            # 字段缓存中的旧集合已过期，失效缓存让重试重新获取真实字段
            if "Unknown column" in error_msg:
                _invalidate_table_column_cache(db_name, table_name)

            # 检查是否是瞬态错误（"未知列"在缓存失效后可恢复，一并纳入重试）
            is_transient = any(keyword in error_msg for keyword in TRANSIENT_ERROR_KEYWORDS)

            if (is_transient or "Unknown column" in error_msg) and attempt < max_retries:
                delay = retry_delay * (2 ** attempt)  # 指数退避
                logger.warning(f"数据库错误，重试 {attempt+1}/{max_retries} ({db_name}.{table_name}): {error_msg}")
                await asyncio.sleep(delay)
                continue

            # 非瞬态错误或重试次数用尽，抛出异常
            raise


async def db_update_by_index(
    db_names: str,
    model_or_tablename: TortoiseBaseModel | str,
    index_dict: Dict[str, Any],
    new_values_dict: Dict[str, Any],
    not_found_behavior: Literal["insert", "error", "skip"] = "skip",
    on_db_error: Literal["continue", "abort"] = "continue"
) -> MultiDbResult:
    """
    基于索引更新记录，支持更新联合主键字段
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        index_dict: 用于索引记录的字典，包含旧的键值
        new_values_dict: 新值构成的字典，可包含联合主键字段
        not_found_behavior: 找不到记录时的行为："insert" 新增，"error" 报错，"skip" 略过
        on_db_error: 账套出错时的策略，"continue" 继续下一账套，"abort" 中断
        
    Returns:
        MultiDbResult: 统一格式的返回值
        
    特性:
        - 支持针对瞬态数据库错误的自动重试（最多2次）
        - 重试延迟采用指数退避策略
        - 识别的瞬态错误包括：网络丢包、连接重置、MySQL断开等
    """
    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        raise ValueError(f"操作失败：未找到对应模型，input_table_name: {table_name}, available_tables: {list(TABLE_MODEL_MAPPING.keys())}")

    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        logger.fail("数据库验证", "", f"未找到有效账套（available_dbs：{MYAPS_DB_SET}）")
        raise ValueError(f"操作失败：未找到有效账套，input_db_name: {db_names}, available_dbs: {MYAPS_DB_SET}")

    success_db = []
    affect_count_total = 0
    operation_type = None
    errors = []

    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)

        try:
            async def _make_request():
                # 每次执行前重新过滤，确保表结构变化（如 ALTER TABLE 新增字段）后重试能感知新字段
                filtered_index_dict = await _filter_data_by_table(db_name, table_name, index_dict, "索引更新-index")
                filtered_new_values_dict = await _filter_data_by_table(db_name, table_name, new_values_dict, "索引更新-values")

                logger.debug(f"index_dict: {filtered_index_dict}")
                logger.debug(f"new_values_dict: {filtered_new_values_dict}")

                # 防御：索引字段全部不存在于表中时禁止继续，
                # 否则 update_by_index 的 index_dict 为空会生成无 WHERE 的 SQL，导致全表更新
                if not filtered_index_dict:
                    raise ValueError(
                        f"索引字段 {sorted(index_dict.keys())} 在表 {table_name}@{db_name} 中均不存在，"
                        "无法执行索引更新，请检查表结构"
                    )

                return await db_manager.update_by_index(
                    model_class=mdl,
                    index_dict=filtered_index_dict,
                    new_values_dict=filtered_new_values_dict,
                    not_found_behavior=not_found_behavior
                )

            result = await _execute_with_retry(
                db_manager=db_manager,
                coro_func=_make_request,
                table_name=table_name,
                db_name=db_name
            )

            if result['success']:
                success_db.append(db_name)
                affect_count_total += result['affected_rows']
                operation_type = result.get('operation_type')
                # logger.update("索引", f"{table_name}@{db_name}", f"操作{operation_type}，影响{result['affected_rows']}条")
        except Exception as e:
            error_info = {"db_name": db_name, "error": str(e), "error_type": e.__class__.__name__}
            errors.append(error_info)
            logger.fail("索引更新", f"{table_name}@{db_name}", str(e))
            if on_db_error == "abort":
                logger.warning("索引更新", f"@{db_names}", f"因 {db_name} 出错中断")
                break

    has_errors = len(errors) > 0
    if has_errors:
        error_msg = f"，其中 {len(errors)} 个账套出错"
    else:
        error_msg = ""

    success_value = calc_success_value(success_db, valid_dbs, has_errors)

    return MultiDbResult(
        success=success_value,
        data=[index_dict, new_values_dict],
        message=f"索引更新成功{error_msg}，影响{affect_count_total}条记录",
        meta={
            "affected_rows": affect_count_total,
            "operation_type": operation_type,
            "db_names": valid_dbs,
            "success_db": success_db,
            "table_name": table_name,
            "not_found_behavior": not_found_behavior,
            "has_errors": has_errors,
            "errors": errors
        }
    )
