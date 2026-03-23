from typing import Dict, Any, List, Literal, Tuple, Optional
from copy import deepcopy
from dataclasses import dataclass

from fastapi import status
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_DB_SET
from globalobjects.db_manager import get_db_managers, DbManager
from globalobjects import logger as log_config

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
logger = log_config.get_logger(__name__)

# 获取文件日志器
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')



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
            # if not table_name.lower().startswith('v_'):
            #     file_logger.error(f"❌↑未找到对应模型（table_name：{table_name}），禁止查询 —— db_query")
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


    
async def db_query(db_name: str, model_or_tablename: TortoiseBaseModel | str, filter_string: str = '', order_string: str = ''):
    _, table_name = process_model_or_tablename(model_or_tablename)
    try:
        valid_db = validate_databases(db_name)[0]
        assert valid_db, "未指定账套或账套不存在"

        db_manager = get_db_manager(valid_db)
        
        query_result = await db_manager.query_data(
            table_name=table_name,
            filter_string=filter_string,
            order_string=order_string,
        )
        formatted_data = [format_query_result(row) for row in query_result['data']]
        total = query_result['total']
        
        return standard_response(
            data=formatted_data,
            meta={"total": total}
        )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )



async def preprocess_data(data_list: List[PydanticSchema | Dict[str, Any]], conflict_fields: Optional[Tuple[str, ...]] = None) -> List[ProcessedData]:
    """
    预处理数据，将Pydantic模型转换为字典，并可选地基于冲突字段去重
    
    Args:
        data_list: 原始数据列表，可以是PydanticSchema对象或字典
        conflict_fields: 冲突字段元组，用于去重（可选）
        
    Returns:
        预处理后的数据列表
    """
    processed_list = []
    for data_item in data_list:
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


async def db_supsert(db_names: str, model_or_tablename: TortoiseBaseModel | str, data_item: PydanticSchema | Dict[str, Any], use_rawdata: bool = True):
    """
    通用单条数据写入操作，支持创建和更新，整体逻辑类似于旧版的逐条创建或更新。比 db_bupsert 颗粒度更细，但会损失一定性能
    
    :param db_names: 账套名称，多个可用半角逗号分隔
    :param model_or_tablename: 模型类或表名
    :param data_item: 数据，字典或PydanticSchema对象
    :param use_rawdata: 是否使用原始数据（若传入的数据为PydanticSchema对象，默认使用未被 validator 处理的数据）
    :return: 操作结果
    """
    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到对应模型",
            meta={
                "input_table_name": table_name,
                "available_tables": list(TABLE_MODEL_MAPPING.keys()),
            },
            data=[data_item]
        )

    if isinstance(data_item, PydanticSchema):
        if use_rawdata:
            data = get_raw_input_data(data_item)
        else:
            data = data_item.model_dump(exclude_none=True)
    else:
        data = data_item    # 若为字典则直接使用

    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        filelog_error.error(f"❌ 未找到有效账套（available_dbs：{MYAPS_DB_SET}），禁止写入 —— db_supsert")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到有效账套",
            meta={
                "input_db_name": db_names,
                "available_dbs": MYAPS_DB_SET,
            },
            data=[data_item]
        )

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

    return standard_response(
        meta={
            "success_db": success_db,
            "create": create_count_total,
            "update": update_count_total,
        },
        data=[data_item]
    )


async def db_bupsert(db_names: str, model_or_tablename: TortoiseBaseModel | str, data_list: List[PydanticSchema | Dict[str, Any]], use_orm_or_sql: Literal["orm", "sql", "auto"] = "sql"):
    """
    通用批量写入操作，支持创建和更新
    融合了多账套处理逻辑与db_manager.py的高效数据库操作
    Args:
        db_name: 账套名称，支持逗号分隔的多个账套
        mdl: Tortoise模型类
        data: 数据列表，可以是PydanticSchema对象或字典
        use_orm_or_sql
        
    Returns:
        标准响应格式
    """
    # 验证账套
    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        filelog_error.error(f"❌ 未找到有效账套（available_dbs：{MYAPS_DB_SET}），禁止写入 —— db_bupsert")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到有效账套",
            meta={
                "input_db_name": db_names,
                "available_dbs": MYAPS_DB_SET,
            },
            # data=[item.processed_data for item in processed_data_list]
            data=data_list
        )

    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到对应模型",
            meta={
                "input_table_name": table_name,
                "available_tables": list(TABLE_MODEL_MAPPING.keys()),
            },
            data=data_list
        )

    origin_total = len(data_list)
    # 记录日志
    
    # 获取冲突字段
    model_key = DbManager._get_conflict_fields(mdl)
    
    # 预处理数据，并基于冲突字段去重
    processed_data_list = await preprocess_data(data_list, conflict_fields=model_key)
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
    filelog_normal.info(f"ℹ️↓接收到{origin_total}条数据，去重后剩余{len(upsert_data_list)}条，拟写入{mdl._meta.db_table}@[{db_names}] —— db_bupsert\n{formatted_data}")
    # 准备更新字段（排除主键字段）
    update_fields = [field for field in upsert_data_list[0].keys() if field not in model_key]
    
    # 排除字段（自增ID或不需要upsert的字段）
    exclude_fields = []
    if hasattr(mdl._meta, 'pk_attr') and mdl._meta.pk_attr in upsert_data_list[0]:
        pk_attr = mdl._meta.pk_attr
        # 检查主键是否是自增类型
        pk_field = mdl._meta.fields_map.get(pk_attr)
        if pk_field.generated:
            exclude_fields.append(pk_attr)
            if pk_attr in update_fields:
                update_fields.remove(pk_attr)
    try:
        # 处理每个账套，使用专属的DbManager实例
        for db_name in valid_dbs:
            # 获取该账套的专属DbManager实例
            db_manager = get_db_manager(db_name)
            
            result = await db_manager.bulk_upsert(
                model_class=mdl,
                data_list=upsert_data_list,
                update_fields=update_fields,
                exclude_fields=exclude_fields,
                conflict_fields=tuple(model_key) if model_key else None,
                use_orm_or_sql=use_orm_or_sql
            )

            # 更新统计
            create_count = result.get("inserted", 0)
            update_count = result.get("updated", 0)
            create_count_total += create_count
            update_count_total += update_count
            filelog_normal.info(f"✅ 生效账套@{db_name}，新增{create_count}条，修改{update_count}条")
            # 记录成功的账套
            success_db.append({"db_name": db_name, "create": create_count, "update": update_count})
        
        # 记录总日志
        filelog_normal.info(f"✅ 生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条")
        
        return standard_response(
            data=data_list,
            message=f"生效{len(success_db)}个账套，总计新增{create_count_total}条，修改{update_count_total}条",
            meta={"origin_total": origin_total, "success_db": success_db}
        )
        
    except Exception as e:
        filelog_error.error(f"❌ 操作失败：{mdl._meta.db_table}@[{db_names}] {str(e)} —— db_bupsert")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}",
            meta={"origin_total": origin_total, "success_db": success_db},
            # data=[item.processed_data for item in processed_data_list]
            data=data_list
        )


async def db_delete(db_names: str, model_or_tablename: TortoiseBaseModel | str, filter_string: str):
    """
    执行SQL删除操作
    :param db_names: 账套名称，多个可用半角逗号分隔
    :param model_or_tablename: 模型类或表名
    :param filter_string: WHERE子句，用于指定删除条件
    :return: 操作结果
    """
    _, table_name = process_model_or_tablename(model_or_tablename)
    try:
        valid_dbs = validate_databases(db_names)
        assert valid_dbs, "未指定账套或账套不存在"
        total_count = 0
        for db_name in valid_dbs:
            db_manager = get_db_manager(db_name)
            exe_result = await db_manager.delete_data(table_name=table_name, filter_string=filter_string)

            count = exe_result.get("affected_rows", 0)
            total_count += count
            filelog_normal.info(f"✅ 执行SQL删除操作成功，{table_name}@{db_name}，条件：{filter_string}，删除{count}条记录")
        filelog_normal.info(f"✅ 执行SQL删除操作成功，共删除{total_count}条记录，{table_name}@[{','.join(valid_dbs)}]")
        return standard_response(
            meta={"affect_count": total_count, "affect_dbs": ", ".join(valid_dbs)}
        )
        
    except Exception as e:
        filelog_error.error(f"❌ 执行SQL删除操作失败，{table_name}@{db_names}，条件：{filter_string}，错误信息：{str(e)}")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )



async def call_dbprocdure(db_names: str, procedure_name: str, params_list: List[List[Any]] = [[]]):
    """
    调用数据库存储过程
    :param db_names: 账套名称，多个可用半角逗号分隔
    :param procedure_name: 存储过程名称
    :param params_list: 存储过程参数列表，每个元素是一个参数列表
    :return: 操作结果
    """
    valid_dbs = validate_databases(db_names)
    assert valid_dbs, "未指定账套或账套不存在"
    total_affect_count = 0
    meta = {}
    try:
        for db_name in valid_dbs:
            db_manager = get_db_manager(db_name)
            exe_result = await db_manager.call_stored_procedure(procedure_name=procedure_name, params_list=params_list)
            affect_rows = exe_result.get('affected_rows', 0)
            total_affect_count += affect_rows
            filelog_normal.info(f"✅ 调用存储过程`{procedure_name}`成功，{db_name}，影响{affect_rows}条记录")
            meta[db_name] = affect_rows
        return standard_response(
            message=f"调用存储过程`{procedure_name}`成功，影响{total_affect_count}条记录",
            meta=meta
        )
    except Exception as e:
        filelog_error.error(f"❌ 调用存储过程`{procedure_name}`失败，{db_names}，错误信息：{str(e)}")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )


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
        标准响应格式
    """
    mdl, table_name = process_model_or_tablename(model_or_tablename)
    
    if not mdl:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到对应模型",
            meta={
                "input_table_name": table_name,
                "available_tables": list(TABLE_MODEL_MAPPING.keys()),
            },
            data=[index_dict, new_values_dict]
        )

    valid_dbs = validate_databases(db_names)
    if not valid_dbs:
        filelog_error.error(f"❌ 未找到有效账套（available_dbs：{MYAPS_DB_SET}），禁止写入 —— db_update_by_index")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="操作失败：未找到有效账套",
            meta={
                "input_db_name": db_names,
                "available_dbs": MYAPS_DB_SET,
            },
            data=[index_dict, new_values_dict]
        )

    success_db = []
    affect_count_total = 0

    try:
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
                filelog_normal.info(f"✅ 基于索引更新操作成功，{table_name}@{db_name}，操作类型：{result['operation_type']}，影响{result['affected_rows']}条记录")

        return standard_response(
            meta={
                "success_db": success_db,
                "affect_count": affect_count_total,
                "operation_type": result.get('operation_type')
            },
            data=[index_dict, new_values_dict]
        )
    except Exception as e:
        filelog_error.error(f"❌ 基于索引更新操作失败，{table_name}@[{db_names}]，错误信息：{str(e)}")
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}",
            data=[index_dict, new_values_dict]
        )
