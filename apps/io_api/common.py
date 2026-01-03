# import os, logging, queue
# from logging.handlers import TimedRotatingFileHandler, QueueHandler, QueueListener
# from pickle import LONG
from typing import Dict, Any, List, Tuple
# from enum import Enum
from copy import deepcopy
from dataclasses import dataclass

from fastapi import status, Query, HTTPException, status, Request, Header
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from tortoise import Tortoise
from tortoise.transactions import in_transaction
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_MAIN_DB, MYAPS_DB_SET, MYAPS_DBSET_LIST
from globalobjects.globalconst import SUPPLY_TYPE#ORDER_STATUS, 
from globalobjects import file_timed_logger

file_logger = file_timed_logger.setup_logging(__name__)

# 导入异步上下文管理器
from contextlib import asynccontextmanager


# 创建一个异步上下文管理器来管理Tortoise连接
@asynccontextmanager
async def get_tortoise_connection(db_name):
    """异步上下文管理器，用于获取和自动关闭Tortoise连接"""
    try:
        connection = Tortoise.get_connection(db_name)
        yield connection
    finally:
        connection.close()


@dataclass
class ProcessedData:
    """处理后的数据类，统一管理不同类型的数据"""
    processed_data: dict  # 处理后的数据（用于更新）
    create_data: dict     # 创建数据（深拷贝，用于创建）
    raw_input_data: Any   # model_validator之前的原始数据


def dict_to_lower_keys(d: dict) -> dict:
    return {k.lower(): v for k, v in d.items()}

# 路由相关公共格式
def standard_response(
    status_code: int = status.HTTP_200_OK,
    success: int = 1,
    message: str = "success",
    data: Any = None,
    meta: Dict[str, Any] = None
):
    return {
        "status_code": status_code,
        "success": success,
        "message": message,
        "meta": meta,
        "data": data
    }

# url - 公共参数
common_params = {
    "db_name": Query(MYAPS_MAIN_DB, example=MYAPS_MAIN_DB, description="账套"),
    "page_size": Query(1000, description="每页数量", gt=0, le=10000),
    "page_index": Query(0, description="分页页码，从0开始", ge=0),
    "supply_type": Query(..., description="供应类型", openapi_examples={key: {"value": key, "summary": value} for key, value in SUPPLY_TYPE.items()}),
    "x_api_key": Header(None, description="API密钥")
}


def get_raw_input_data(data_item: PydanticSchema | Dict[str, Any]) -> Any:
    """
    获取model_validator之前的原始数据
    
    Args:
        data_item: 单个数据项，可以是PydanticSchema对象或字典
        
    Returns:
        model_validator之前的原始数据
    """
    if isinstance(data_item, PydanticSchema):
        # 检查是否有_raw_input_data属性（在after验证阶段设置的）
        if hasattr(data_item, '_raw_input_data'):
            return data_item._raw_input_data
        else:
            # 如果没有，说明可能没有执行before验证或没有暂存数据
            # 尝试直接访问属性或使用model_dump(include='_raw_input_data')
            try:
                # 使用model_dump获取所有数据，包括私有属性
                all_data = data_item.model_dump(include={'_raw_input_data'}, exclude_none=False)
                return all_data['_raw_input_data']
            except Exception:
                return data_item.model_dump(exclude_none=False)
    else:
        # 如果不是PydanticSchema对象，直接使用原始值
        return data_item


def convert_to_dict(data_item: PydanticSchema | Dict[str, Any], exclude_none: bool = True) -> dict:
    """
    将数据项转换为字典
    
    Args:
        data_item: 单个数据项，可以是PydanticSchema对象或字典
        exclude_none: 是否排除None值
        
    Returns:
        转换后的字典
    """
    if isinstance(data_item, PydanticSchema):
        return data_item.model_dump(exclude_none=exclude_none)
    return data_item


def validate_databases(db_name: str) -> List[str]:
    """
    验证并返回有效的账套列表
    
    Args:
        db_name: 账套名称，支持逗号分隔的多个账套
        
    Returns:
        有效的账套列表
    """
    return [db for db in db_name.split(",") if db in MYAPS_DBSET_LIST]


async def preprocess_data(data: List[PydanticSchema | Dict[str, Any]]) -> List[ProcessedData]:
    """
    预处理数据列表，转换为统一的ProcessedData格式
    
    Args:
        data: 原始数据列表
        
    Returns:
        预处理后的ProcessedData列表
    """
    processed_list = []
    for data_item in data:
        # 获取原始输入数据
        raw_input_data = get_raw_input_data(data_item)
        # 转换为字典
        processed_dict = convert_to_dict(data_item, exclude_none=True)
        # 深拷贝用于创建操作
        create_dict = deepcopy(processed_dict)
        # 添加到处理列表
        processed_list.append(ProcessedData(
            processed_data=processed_dict,
            create_data=create_dict,
            raw_input_data=raw_input_data
        ))
    return processed_list


async def process_overwrite_operation(
    db, mdl, match_on: dict, new_value: dict, create_data: dict, only_fields: List[str],
    db_name: str
) -> Tuple[int, int]:
    """
    处理覆盖操作
    
    Args:
        db: 数据库连接
        mdl: 模型类
        match_on: 匹配条件
        new_value: 新值
        create_data: 创建数据
        only_fields: 仅查询的字段
        db_name: 账套名称
        
    Returns:
        (创建数量, 更新数量)
    """
    create_count = 0
    update_count = 0
    
    # 检查记录是否存在
    if await mdl.filter(**match_on).only(*only_fields).using_db(db).exists():
        # 构建参数化查询
        set_clauses = []
        params = []
        
        for k, v in new_value.items():
            if k != "vid":
                set_clauses.append(f"{k} = ?")
                params.append(v)
        
        # 构建WHERE条件
        where_clauses = []
        for k, v in match_on.items():
            where_clauses.append(f"{k} = ?")
            params.append(v)
        
        # 执行更新
        sql = f"""
            UPDATE {mdl._meta.db_table}
            SET {', '.join(set_clauses)}
            WHERE {' AND '.join(where_clauses)}
        """
        
        await db.execute_query(sql, params)
        update_count += 1
        # file_logger.info(f"✅↑UPDATE @{db_name}")
    else:
        # 创建新记录
        await mdl.create(**create_data, using_db=db)
        create_count += 1
        # file_logger.info(f"✅↑CREATE @{db_name}")
    
    return create_count, update_count


async def process_normal_operation(
    db, mdl, match_on: dict, update_data: dict, create_data: dict, only_fields: List[str],
    db_name: str, is_compound_key: bool
) -> Tuple[int, int]:
    """
    处理正常操作（非覆盖）
    
    Args:
        db: 数据库连接
        mdl: 模型类
        match_on: 匹配条件
        update_data: 更新数据
        create_data: 创建数据
        only_fields: 仅查询的字段
        db_name: 账套名称
        is_compound_key: 是否为联合主键
        
    Returns:
        (创建数量, 更新数量)
    """
    create_count = 0
    update_count = 0
    
    if is_compound_key:
        # 联合主键处理
        if await mdl.filter(**match_on).only(*only_fields).using_db(db).exists():
            # 更新记录
            await mdl.filter(**match_on).only(*only_fields).first().using_db(db).update(**update_data)
            update_count += 1
            # file_logger.info(f"✅↑UPDATE @{db_name}")
        else:
            # 创建新记录
            await mdl.create(**create_data, using_db=db)
            create_count += 1
            # file_logger.info(f"✅↑CREATE @{db_name}")
    else:
        # 单一主键处理
        exist = await mdl.get_or_none(**match_on, using_db=db)
        if exist:
            # 更新记录
            await exist.update_from_dict(update_data).save(using_db=db)
            update_count += 1
            # file_logger.info(f"✅↑UPDATE @{db_name}")
        else:
            # 创建新记录
            await mdl.create(**create_data, using_db=db)
            create_count += 1
            # file_logger.info(f"✅↑CREATE @{db_name}")
    
    return create_count, update_count


async def process_single_database(
    db_name: str, mdl: TortoiseBaseModel, processed_data_list: List[ProcessedData],
    only_fields: List[str], model_key: List[str]
) -> Tuple[int, int]:
    """
    处理单个数据库的操作
    
    Args:
        db_name: 数据库名称
        mdl: 模型类
        processed_data_list: 预处理后的数据列表
        only_fields: 仅查询的字段
        model_key: 模型主键
        
    Returns:
        (创建数量, 更新数量)
    """
    create_count = 0
    update_count = 0
    match_on = None
    new_value = None
    
    async with in_transaction(db_name) as db:
        for i, processed_data in enumerate(processed_data_list):
            # 检查是否需要覆盖操作
            if "_overwrite" in processed_data.processed_data:
                if i == 0:
                    match_on = processed_data.processed_data["_overwrite"]["match_on"]
                    new_value = processed_data.processed_data["_overwrite"]["new_value"]
                
                # 处理覆盖操作
                create, update = await process_overwrite_operation(
                    db, mdl, match_on, new_value, processed_data.create_data, only_fields,
                    db_name
                )
                create_count += create
                update_count += update
            else:
                # 构建匹配条件
                match_on = {k: processed_data.create_data.get(k) for k in model_key}
                
                is_compound_key = len(model_key) > 1
                # 处理正常操作
                create, update = await process_normal_operation(
                    db=db, mdl=mdl, match_on=match_on, update_data=processed_data.raw_input_data, create_data=processed_data.create_data,
                    only_fields=only_fields, db_name=db_name, is_compound_key=is_compound_key
                )
                create_count += create
                update_count += update
    
    return create_count, update_count


async def common_write(db_name: str, mdl: TortoiseBaseModel, data: List[PydanticSchema | Dict[str, Any]]):
    """
    通用写入操作，支持创建和更新
    
    Args:
        db_name: 账套名称，支持逗号分隔的多个账套
        mdl: Tortoise模型类
        data: 数据列表，可以是PydanticSchema对象或字典
        
    Returns:
        标准响应格式
    """
    # 预处理数据
    processed_data_list = await preprocess_data(data)
    origin_total = len(data)
    
    # 记录日志
    file_logger.info(f"ℹ️↓接收到{origin_total}条数据，拟写入{mdl._meta.db_table}@[{db_name}] —— common_write\n{[i.raw_input_data for i in processed_data_list]}")
    
    # 验证账套
    valid_dbs = validate_databases(db_name)
    if not valid_dbs:
        file_logger.error(f"❌↑未找到有效账套（available_dbs：{MYAPS_DB_SET}），禁止写入 —— common_write")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到有效账套",
            meta={
                "input_db_name": db_name,
                "available_dbs": MYAPS_DB_SET,
            },
            data=[item.processed_data for item in processed_data_list]
        )
    
    # 获取模型信息
    unique_together = mdl._meta.unique_together
    model_key = unique_together[0] if unique_together else [mdl._meta.pk_attr]
    is_compound_key = len(model_key) > 1
    only_fields = [f for f in mdl._meta.fields if f != "vid"] if is_compound_key else None
    
    # 初始化统计信息
    success_db = []
    create_count_total = 0
    update_count_total = 0
    
    try:
        # 处理每个账套
        for db_name in valid_dbs:
            # 处理单个账套
            create_count, update_count = await process_single_database(
                db_name=db_name, mdl=mdl, processed_data_list=processed_data_list, only_fields=only_fields, model_key=model_key
            )
            
            # 更新统计
            create_count_total += create_count
            update_count_total += update_count
            file_logger.info(f"✅生效账套@{db_name}，新增{create_count}条，修改{update_count}条")
            # 记录成功的账套
            success_db.append({"db_name": db_name, "create": create_count, "update": update_count})
        
        # 记录总日志
        file_logger.info(f"✅生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条")
        
        return standard_response(
            data=[item.create_data for item in processed_data_list],
            message=f"生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条",
            meta={"origin_total": origin_total, "success_db": success_db}
        )
    except Exception as e:
        file_logger.error(f"❌↑操作失败：{str(e)} —— common_write")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)} —— common_write",
            meta={"origin_total": origin_total, "success_db": success_db, "error_db": db_name},
            data=[item.processed_data for item in processed_data_list]
        )


# 路由公共方法
async def common_read_by_orm(db_name: str, mdl: TortoiseBaseModel, page_size: int, page_index: int):
    dbs = validate_databases(db_name)
    assert dbs, "账套参数错误"
    
    # 使用异步上下文管理器管理连接
    async with get_tortoise_connection(dbs[0]) as db:
        # 分页查询
        offset = page_size * page_index
        if mdl._meta.unique_together:   # 如果是联合主键，则要排除虚拟主键的干扰
            only_fields = [f for f in mdl._meta.fields if f != "vid"]
            data = await mdl.all().only(*only_fields).using_db(db).offset(offset).limit(page_size)
        else:
            data = await mdl.all().using_db(db).offset(offset).limit(page_size)
        
        # 在连接关闭前获取总数
        total = await mdl.all().using_db(db).count()
    
    return standard_response(
        data=data,
        meta={
            "db_name": dbs[0],
            "total": total,
            "pageSize": page_size,
            "pageIndex": page_index,
        }
    )


# 路由公共方法 - delete
async def common_delete_by_orm(db_name: str, mdl: TortoiseBaseModel, targets: List[dict]):
    delete_count = 0
    try:
        async with in_transaction(db_name) as db:
            for target in targets:
                exist = await mdl.get_or_none(**target, using_db=db)
                if exist:
                    await exist.delete(using_db=db)
                    delete_count += 1
        return standard_response(
            message=f"删除{delete_count}条",
            meta={"delete": delete_count}
            )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )


async def common_call_dbprocdure(db_name: str, procedure_name: str, params_list: List[List[Any]] = [[]]):
    """
    调用数据库存储过程
    :param db_name: 数据库名称
    :param procedure_name: 存储过程名称
    :param params_list: 存储过程参数列表，每个元素是一个参数列表
    :return: 操作结果
    """
    affect_count = 0
    try:
        async with in_transaction(db_name) as db:
            for params in params_list:
                count, data = await db.execute_query(
                    f'CALL {procedure_name}({", ".join(["%s"] * len(params))})', 
                    params
                )
                affect_count += data[0].get('t_supply_updated', 0)
            return standard_response(
                message=f"调用存储过程`{procedure_name}`成功，影响{affect_count}条记录",
                meta={"affect": affect_count}
            )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )


async def common_read_by_sql(db_name: str, table_name: str, filter_string: str = '', order_string: str = ''):
    try:
        valid_dbs = validate_databases(db_name)
        assert valid_dbs, "未指定账套或账套不存在"
        
        # 使用异步上下文管理器管理连接
        async with get_tortoise_connection(valid_dbs[0]) as db:
            where = f" WHERE {filter_string}" if filter_string else ''
            order = f" ORDER BY {order_string}" if order_string else ''
            sql = f'SELECT * FROM `{table_name}` {where} {order}'
            total, data = await db.execute_query(sql)
            lower_keys_data = [dict_to_lower_keys(row) for row in data]
        
        return standard_response(
            data=lower_keys_data,
            meta={"total": total}
        )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )


async def common_delete_by_sql(db_name: str, table_name: str, filter_string: str):
    """
    执行SQL删除操作
    :param db_name: 账套名称，多个可用半角逗号分隔
    :param table_name: 表名称
    :param filter_string: WHERE子句，用于指定删除条件
    :return: 操作结果
    """
    try:
        where = f" WHERE {filter_string}" if filter_string else ''
        sql = f'DELETE FROM `{table_name}` {where}'
        valid_dbs = validate_databases(db_name)
        assert valid_dbs, "未指定账套或账套不存在"
        total_count = 0
        for valid_db in valid_dbs:
            count = 0
            async with get_tortoise_connection(valid_db) as db:
            # db = Tortoise.get_connection(valid_db)
                count, data = await db.execute_query(sql)
                total_count += count
            # await db.close()
            file_logger.info(f"✅执行SQL删除操作成功，{table_name}@{valid_db}，条件：{filter_string}，删除{count}条记录")
        file_logger.info(f"✅执行SQL删除操作成功，共删除{total_count}条记录，{table_name}@[{','.join(valid_dbs)}]")
        return standard_response(
            data=data,
            meta={"affect_count": total_count, "affect_dbs": ", ".join(valid_dbs)}
        )
        
    except Exception as e:
        file_logger.error(f"❌执行SQL删除操作失败，{table_name}@{db_name}，条件：{filter_string}，错误信息：{str(e)}")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )


################################################################
# pydantic验证错误统一格式
class CustomValidationError(HTTPException):
    def __init__(self, errors: List[Dict[str, Any]]):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        detail = standard_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            success=0,
            message="数据验证错误",
            meta={
                "error_details": errors
        }
    )
        super().__init__(status_code=status_code, detail=detail)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": "->".join(str(loc) for loc in error['loc']),
            "message": error['msg'],
            "type": error['type']
        })
    raise CustomValidationError(errors=errors)


async def http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        detail = exc.detail
    else:
        detail = {
            "message": str(exc.detail),
            "meta": None
        }
    return JSONResponse(
        status_code=exc.status_code,
        content=standard_response(
            status_code=exc.status_code,
            success=0,
            message=detail.get("message", "Error occurred"),
            data=None,
            meta=detail.get("meta", None)
        )
    )


def register_exception_handlers(app):
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)