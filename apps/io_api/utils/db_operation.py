from typing import Dict, Any, List, Literal, Tuple, Optional, Callable
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
import asyncio
import json
import uuid
from datetime import datetime, timedelta

from fastapi import status
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from core.settings import MYAPS_DB_SET, LOG_LEVEL
from globalobjects.db_manager import get_db_managers, DbManager
from globalobjects import logger as log_config
from apps.common.monitor.models import FailedOperation
from globalobjects import AlertType, alert_manager

# 为了保持向后兼容，重新导出 db_managers
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
    # 每次都调用get_db_managers()获取最新的实例字典
    return get_db_managers()[db_name]
from .common import standard_response, format_query_result, get_raw_input_data, convert_to_dict, format_data_for_logging
from ..models import TABLE_MODEL_MAPPING




# 获取控制台日志器
logger = log_config.get_logger(__name__, level=LOG_LEVEL)


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
                    
                    # 检查是否是连接相关错误
                    is_connection_error = (
                        "Cannot acquire connection after closing pool" in error_str or
                        "OperationalError" in str(type(e)) or
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
                            for db_name in valid_dbs:
                                try:
                                    operation_id = str(uuid.uuid4())
                                    
                                    # 序列化参数
                                    try:
                                        args_json = json.dumps([json.dumps(arg) if not isinstance(arg, (str, int, float, bool, type(None))) else arg for arg in args])
                                    except (TypeError, OverflowError):
                                        args_json = json.dumps([str(arg) for arg in args])
                                    
                                    try:
                                        kwargs_json = json.dumps({k: json.dumps(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in kwargs.items()})
                                    except (TypeError, OverflowError):
                                        kwargs_json = json.dumps({k: str(v) for k, v in kwargs.items()})
                                    
                                    # 持久化到SQLite
                                    await FailedOperation.create(
                                        operation_id=operation_id,
                                        timestamp=datetime.now(),
                                        db_name=db_name,
                                        function_name=func.__name__,
                                        args_json=args_json,
                                        kwargs_json=kwargs_json,
                                        error_message=error_str,
                                        error_type=e.__class__.__name__,
                                        status="pending",
                                        retry_count=0,
                                        max_retries=10,
                                        next_retry_time=datetime.now() + timedelta(minutes=5),
                                    )
                                    
                                    # 触发告警
                                    await alert_manager.trigger_remind(
                                        AlertType.DB_CONNECTION,
                                        {
                                            "operation_id": operation_id,
                                            "db_name": db_name,
                                            "function": func.__name__,
                                            "error": error_str,
                                            "retry_count": attempt + 1,
                                            "next_retry": "5分钟后"
                                        }
                                    )
                                    
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
    db_names = [name.strip() for name in db_name.split(",") if name.strip()]
    valid_dbs = [db for db in db_names if db in MYAPS_DB_SET]
    return valid_dbs



@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_exec_sql(db_name: str, sql: str, params: Optional[List[Any]] = None, description: str = ''):
    """
    执行原始SQL语句

    Args:
        db_name: 数据库连接名称
        sql: 要执行的SQL语句
        params: SQL参数列表（可选）

    Returns:
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
    """
    valid_db = validate_databases(db_name)[0]
    assert valid_db, "未指定账套或账套不存在"

    db_manager = get_db_manager(valid_db)

    count, data_list = await db_manager._execute_native_sql(
        sql=sql,
        params=params if params is not None else [],
        description=f"执行SQL {description}..."
    )

    return {
        "success": 1,
        "data": data_list,
        "message": f"执行SQL成功，影响{count}条记录",
        "meta": {
            "affected_rows": count,
            "db_names": [valid_db],
            "table_name": ""
        }
    }


    
@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_query(db_name: str, model_or_tablename: TortoiseBaseModel | str, select="*", filter_string: str = '', order_string: str = '', page_size: int = 1000, page_index: int = 1):
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
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
    """
    _, table_name = process_model_or_tablename(model_or_tablename)
    valid_db = validate_databases(db_name)[0]
    assert valid_db, "未指定账套或账套不存在"

    db_manager = get_db_manager(valid_db)
    
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
    
    return {
        "success": 1,
        "data": formatted_data,
        "message": f"查询成功，共{total}条记录",
        "meta": {
            "affected_rows": total,
            "page_size": page_size,
            "page_index": page_index,
            "db_names": [valid_db],
            "table_name": table_name
        }
    }



async def preprocess_data(data_list: List[PydanticSchema | Dict[str, Any]], model_class: Optional[TortoiseBaseModel] = None, conflict_fields: Optional[Tuple[str, ...]] = None, exclude_none: bool = True) -> List[ProcessedData]:
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
async def db_supsert(db_names: str, model_or_tablename: TortoiseBaseModel | str, data_item: PydanticSchema | Dict[str, Any], use_rawdata: bool = True):
    """
    通用单条数据写入操作，支持创建和更新，整体逻辑类似于旧版的逐条创建或更新。比 db_bupsert 颗粒度更细，但会损失一定性能
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        data_item: 数据，字典或PydanticSchema对象
        use_rawdata: 是否使用原始数据（若传入的数据为PydanticSchema对象，默认使用未被 validator 处理的数据）

    Returns:
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
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

    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)

        result = await db_manager.single_upsert(
            model_class=mdl,
            data=data,
        )

        if result['success']:
            success_db.append(db_name)
            create_count_total += result['inserted']
            update_count_total += result['updated']

    return {
        "success": 1,
        "data": [data_item],
        "message": f"数据写入成功，新增{create_count_total}条，修改{update_count_total}条",
        "meta": {
            "affected_rows": create_count_total + update_count_total,
            "created_rows": create_count_total,
            "updated_rows": update_count_total,
            "db_names": valid_dbs,
            "table_name": table_name
        }
    }


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_bupsert(db_names: str, model_or_tablename: TortoiseBaseModel | str, data_list: List[PydanticSchema | Dict[str, Any]], use_orm_or_sql: Literal["orm", "sql", "auto"] = "sql", exclude_none: bool = True, batch_size: int = 1000, on_batch_error: Literal["continue", "skip"] = "continue"):
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
        
    Returns:
        Dict[str, Any]: 包含 'success', 'data', 'message', 'meta'
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
        logger.warning("批量upsert", mdl._meta.db_table, "没有可处理的数据")
        return {
            "success": 1,
            "data": data_list,
            "message": f"生效{len(success_db)}个账套，无数据处理",
            "meta": {"origin_total": origin_total, "success_db": success_db}
        }
    
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
    for db_name in valid_dbs:
        # 获取该账套的专属DbManager实例
        db_manager = get_db_manager(db_name)
        
        db_create_count = 0
        db_update_count = 0
        db_errors = []
        db_skipped_count = 0
        db_skipped_batches = []
        
        total_batches = (len(upsert_data_list) + batch_size - 1) // batch_size
        for i in range(total_batches):
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, len(upsert_data_list))
            batch_data = upsert_data_list[start_idx:end_idx]
            
            try:
                result = await db_manager.bulk_upsert(
                    model_class=mdl,
                    data_list=batch_data,
                    update_fields=update_fields,
                    exclude_fields=exclude_fields,
                    conflict_fields=tuple(model_key) if model_key else None,
                    use_orm_or_sql=use_orm_or_sql
                )

                batch_create = result.get("inserted", 0)
                batch_update = result.get("updated", 0)
                db_create_count += batch_create
                db_update_count += batch_update
                logger.insert("账套批次生效", f"{db_name} (批次{i+1}/{total_batches})", f"新增{batch_create}条，修改{batch_update}条")
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
        
        create_count_total += db_create_count
        update_count_total += db_update_count
        logger.insert("账套生效", db_name, f"新增{db_create_count}条，修改{db_update_count}条")
        success_db.append({
            "db_name": db_name,
            "create": db_create_count,
            "update": db_update_count,
            "errors": db_errors,
            "skipped_count": db_skipped_count,
            "skipped_batches": db_skipped_batches
        })
    
    has_errors = any(len(db_info["errors"]) > 0 for db_info in success_db)
    
    logger.success("批量upsert", f"{table_name}@{db_names}", f"生效{len(success_db)}个账套，新增{create_count_total}条，修改{update_count_total}条")
    
    if has_errors:
        error_summary = []
        for db_info in success_db:
            if db_info["errors"]:
                error_summary.append({
                    "db_name": db_info["db_name"],
                    "errors": db_info["errors"],
                    "skipped_count": db_info["skipped_count"],
                    "skipped_batches": db_info["skipped_batches"]
                })
        logger.warning("批量upsert", f"{table_name}@{db_names}", f"存在错误批次")
        return {
            "success": 1,
            "data": data_list,
            "message": f"生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条，但存在错误",
            "meta": {
                "affected_rows": create_count_total + update_count_total,
                "created_rows": create_count_total,
                "updated_rows": update_count_total,
                "origin_total": origin_total,
                "distinct_total": len(processed_data_list),
                "db_names": valid_dbs,
                "table_name": table_name,
                "has_errors": True,
                "error_summary": error_summary,
                "total_skipped_count": sum(db_info["skipped_count"] for db_info in success_db)
            }
        }
    
    return {
        "success": 1,
        "data": data_list,
        "message": f"生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条",
        "meta": {
            "affected_rows": create_count_total + update_count_total,
            "created_rows": create_count_total,
            "updated_rows": update_count_total,
            "origin_total": origin_total,
            "distinct_total": len(processed_data_list),
            "db_names": valid_dbs,
            "table_name": table_name
        }
    }


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_delete(db_names: str, model_or_tablename: TortoiseBaseModel | str, filter_string: str | None = None):
    """
    执行SQL删除操作
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        filter_string: WHERE子句，用于指定删除条件；若为None则清空整个表

    Returns:
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
    """
    _, table_name = process_model_or_tablename(model_or_tablename)
    valid_dbs = validate_databases(db_names)
    assert valid_dbs, "未指定账套或账套不存在"
    total_count = 0
    is_truncate = filter_string is None
    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)
        exe_result = await db_manager.delete_data(table_name=table_name, filter_string=filter_string or '')

        count = exe_result.get("affected_rows", 0)
        total_count += count
        logger.delete(f"{table_name}@{db_name}", "ALL DATA" if is_truncate else filter_string, count)
    logger.success("SQL删除", f"{table_name}@{db_names}", f"共删除{total_count}条")
    return {
        "success": 1,
        "data": [],
        "message": f"删除成功，共删除{total_count}条记录",
        "meta": {
            "affected_rows": total_count, 
            "db_names": valid_dbs,
            "table_name": table_name,
            "is_truncate": is_truncate
        }
    }



@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def call_dbprocdure(db_names: str, procedure_name: str, params_list: List[List[Any]] = [[]]):
    """
    调用数据库存储过程
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        procedure_name: 存储过程名称
        params_list: 存储过程参数列表，每个元素是一个参数列表

    Returns:
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
    """
    valid_dbs = validate_databases(db_names)
    assert valid_dbs, "未指定账套或账套不存在"
    total_affect_count = 0
    # meta = {}
    affect_rows = 0
    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)
        exe_result = await db_manager.call_stored_procedure(procedure_name=procedure_name, params_list=params_list)
        affect_rows += exe_result.get('affected_rows', 0)
        total_affect_count += affect_rows
        # logger.success("存储过程调用", f"{procedure_name}@{db_name}", f"影响{affect_rows}条记录")
        # meta[db_name] = affect_rows
    return {
        "success": 1,
        "data": [],
        "message": f"存储过程调用成功，影响{affect_rows}条记录",
        "meta": {
            "affected_rows": affect_rows, 
            "db_names": valid_dbs,
            "procedure_name": procedure_name
        }
    }


@retry_on_connection_error(max_retries=3, retry_delay=1.0)
async def db_update_by_index(
    db_names: str,
    model_or_tablename: TortoiseBaseModel | str,
    index_dict: Dict[str, Any],
    new_values_dict: Dict[str, Any],
    not_found_behavior: Literal["insert", "error", "skip"] = "skip"
):
    """
    基于索引更新记录，支持更新联合主键字段
    
    Args:
        db_names: 账套名称，多个可用半角逗号分隔
        model_or_tablename: 模型类或表名
        index_dict: 用于索引记录的字典，包含旧的键值
        new_values_dict: 新值构成的字典，可包含联合主键字段
        not_found_behavior: 找不到记录时的行为："insert" 新增，"error" 报错，"skip" 略过
        
    Returns:
        Dict[str, Any]: 统一格式的返回值，包含 'success', 'data', 'message', 'meta'
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

    for db_name in valid_dbs:
        db_manager = get_db_manager(db_name)


        logger.debug(f"index_dict: {index_dict}")
        logger.debug(f"new_values_dict: {new_values_dict}")


        result = await db_manager.update_by_index(
            model_class=mdl,
            index_dict=index_dict,
            new_values_dict=new_values_dict,
            not_found_behavior=not_found_behavior
        )

        if result['success']:
            success_db.append(db_name)
            affect_count_total += result['affected_rows']
            operation_type = result.get('operation_type')
            logger.update("索引更新", f"{table_name}@{db_name}", f"操作{operation_type}，影响{result['affected_rows']}条")

    return {
        "success": 1,
        "data": [index_dict, new_values_dict],
        "message": f"索引更新成功，影响{affect_count_total}条记录",
        "meta": {
            "affected_rows": affect_count_total,
            "operation_type": operation_type,
            "db_names": valid_dbs,
            "table_name": table_name,
            "not_found_behavior": not_found_behavior
        }
    }
