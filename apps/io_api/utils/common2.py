from typing import Dict, Any, List, Tuple
from copy import deepcopy
from dataclasses import dataclass

from fastapi import status
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_DB_SET
from globalobjects.db_manager import db_managers
from globalobjects import file_timed_logger

file_logger = file_timed_logger.setup_logging(__name__)


@dataclass
class ProcessedData:
    """处理后的数据类，统一管理不同类型的数据"""
    processed_data: dict  # 处理后的数据（用于更新）
    create_data: dict     # 创建数据（深拷贝，用于创建）
    raw_input_data: Any   # model_validator之前的原始数据


def standard_response(
    success: int = 1,
    status_code: int = status.HTTP_200_OK,
    message: str = "操作成功",
    data: Any = None,
    meta: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    标准响应格式
    
    Args:
        success: 成功标识，1表示成功，0表示失败
        status_code: HTTP状态码
        message: 响应消息
        data: 响应数据
        meta: 附加信息
        
    Returns:
        标准格式的响应字典
    """
    if meta is None:
        meta = {}
    
    return {
        "success": success,
        "message": message,
        "data": data if data is not None else [],
        "meta": meta
    }


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


async def preprocess_data(data: List[PydanticSchema | Dict[str, Any]]) -> List[ProcessedData]:
    """
    预处理数据，将Pydantic模型转换为字典
    
    Args:
        data: 原始数据列表，可以是PydanticSchema对象或字典
        
    Returns:
        预处理后的数据列表
    """
    processed_data_list = []
    
    for item in data:
        if hasattr(item, "dict"):
            raw_data = item.dict()
        else:
            raw_data = deepcopy(item)
        
        processed_data = deepcopy(raw_data)
        create_data = deepcopy(raw_data)
        
        # 处理特殊字段（如果有）
        if "_overwrite" in processed_data:
            create_data.pop("_overwrite", None)
        
        processed_data_list.append(
            ProcessedData(
                processed_data=processed_data,
                create_data=create_data,
                raw_input_data=raw_data
            )
        )
    
    return processed_data_list


async def common_write(db_name: str, mdl: TortoiseBaseModel, data: List[PydanticSchema | Dict[str, Any]]):
    """
    通用写入操作，支持创建和更新
    融合了common.py的多账套处理逻辑与db_manager.py的高效数据库操作
    
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
    file_logger.info(f"ℹ️↓接收到{origin_total}条数据，拟写入{mdl._meta.db_table}@[{db_name}] —— common_write\n{[item.raw_input_data for item in processed_data_list]}")
    
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
    unique_together = getattr(mdl._meta, 'unique_together', [])
    model_key = unique_together[0] if unique_together else [mdl._meta.pk_attr]
    is_compound_key = len(model_key) > 1
    
    # 准备upsert数据
    upsert_data_list = []
    for item in processed_data_list:
        # 检查是否有覆盖操作
        if "_overwrite" in item.processed_data:
            # 处理覆盖操作
            overwrite_info = item.processed_data.pop("_overwrite")
            match_on = overwrite_info["match_on"]
            new_value = overwrite_info["new_value"]
            
            # 更新数据中的字段
            for field, value in new_value.items():
                if field in item.processed_data:
                    item.processed_data[field] = value
        
        upsert_data_list.append(item.processed_data)
    
    # 初始化统计信息
    success_db = []
    create_count_total = 0
    update_count_total = 0
    
    try:
        # 处理每个账套，使用专属的DbManager实例
        for db_name in valid_dbs:
            if db_name not in db_managers:
                file_logger.error(f"❌↑账套@{db_name} 没有对应的DbManager实例 —— common_write")
                continue
            
            # 获取该账套的专属DbManager实例
            db_manager = db_managers[db_name]
            
            # 准备更新字段（排除主键字段）
            update_fields = [field for field in upsert_data_list[0].keys() if field not in model_key]
            
            # 排除字段（自增ID或不需要upsert的字段）
            exclude_fields = []
            if hasattr(mdl._meta, 'pk_attr') and mdl._meta.pk_attr in upsert_data_list[0]:
                # 检查主键是否是自增类型
                pk_field = mdl._meta.fields_map.get(mdl._meta.pk_attr)
                if pk_field and hasattr(pk_field, 'auto_increment') and pk_field.auto_increment:
                    exclude_fields.append(mdl._meta.pk_attr)
            
            # 执行批量upsert
            result = await db_manager.bulk_upsert(
                model_class=mdl,
                data_list=upsert_data_list,
                update_fields=update_fields,
                exclude_fields=exclude_fields,
                conflict_fields=tuple(model_key) if model_key else None
            )
            
            # 更新统计
            create_count = result.get("inserted", 0)
            update_count = result.get("updated", 0)
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
            message=f"操作失败：{str(e)}",
            meta={"origin_total": origin_total, "success_db": success_db},
            data=[item.processed_data for item in processed_data_list]
        )
