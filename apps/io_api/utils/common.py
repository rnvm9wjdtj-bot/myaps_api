from typing import Dict, Any, List, Tuple
import enum
from datetime import datetime

from fastapi import status, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel as PydanticSchema

# from core.settings import MYAPS_MAIN_DB
# from globalobjects.globalconst import SupplyTypeEnum



def dict_to_lower_keys(d: dict) -> dict:
    return {k.lower(): v for k, v in d.items()}

def format_query_result(d: dict) -> dict:
    """
    格式化查询结果
    1. 将字典的键转换为小写
    2. 格式化字典中的日期时间字段（支持datetime对象和ISO 8601字符串格式）
    """
    result = {}
    for k, v in d.items():
        # 将键转换为小写
        lower_key = k.lower()
        # 格式化日期时间字段
        if isinstance(v, datetime):
            result[lower_key] = v.strftime("%Y-%m-%d %H:%M:%S")
        # elif isinstance(v, str) and 'T' in v:
        #     # 尝试解析ISO 8601格式的字符串
        #     try:
        #         # 移除可能的时区信息
        #         if '+' in v or '-' in v:
        #             v = v.split('+')[0].split('-')[0]
        #         # 解析字符串为datetime对象
        #         dt = datetime.fromisoformat(v)
        #         # 格式化为目标格式
        #         result[lower_key] = dt.strftime("%Y-%m-%d %H:%M:%S")
        #     except ValueError:
        #         # 如果解析失败，保留原始值
        #         result[lower_key] = v
        else:
            result[lower_key] = v
    return result

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

# # url - 公共参数
# common_params = {
#     "db_name": Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     "page_size": Query(1000, description="每页数量", gt=0, le=10000),
#     "page_index": Query(0, description="分页页码，从0开始", ge=0),
#     "supply_type": Query(..., description="供应类型", openapi_examples={key: {"value": key, "summary": value.value} for key, value in SupplyTypeEnum.__members__.items()}),
#     "x_api_key": Header(None, description="API密钥")
# }


def get_raw_input_data(data_item: PydanticSchema | Dict[str, Any]) -> Dict:
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


def format_data_for_logging(data):
    """
    格式化数据用于日志记录，将复杂类型转换为字符串表示
    
    Args:
        data: 要格式化的数据
        
    Returns:
        格式化后的数据
    """
    from decimal import Decimal
    import enum
    
    if isinstance(data, dict):
        return {k: format_data_for_logging(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [format_data_for_logging(item) for item in data]
    elif isinstance(data, enum.Enum):
        return data.value
    elif isinstance(data, Decimal):
        return str(data)
    else:
        return data


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



async def drop_matched_data(data: List[Any], db_names: str, table_name: str, match_on: Tuple[str, ...], db_fields: Tuple[str, ...]=None):
    """
    根据组合字段删除已存在的数据项
    Args:
        data: 新数据列表
        db_names: 数据库名称
        table_name: 数据库表名
        match_on: 组合字段，用于唯一标识数据项，如 ("materialno", "matver")
        db_fields: 数据库字段，用于删除数据，如 ("MaterialNo", "MatVer")
    """
    from .db_operation import db_delete
    # 收集唯一组合
    db_fields = db_fields or match_on
    unique_combinations = set()
    for item in data:
        field_values = []
        for field in match_on:
            if isinstance(item, dict):
                field_value = item.get(field)
            else:
                field_value = getattr(item, field, None)
            field_values.append(field_value)
        
        # 确保所有字段都有值
        if all(field_values):
            unique_combinations.add(tuple(field_values))
    
    # 分批删除
    if unique_combinations:
        batch_size = 100
        combinations_list = list(unique_combinations)
        
        for i in range(0, len(combinations_list), batch_size):
            batch = combinations_list[i:i+batch_size]
            conditions = []
            for values in batch:
                # 构建条件，支持任意数量的字段
                field_conditions = []
                for db_field, value in zip(db_fields, values):
                    field_conditions.append(f"`{db_field}`='{value}'")
                condition = " AND ".join(field_conditions)
                conditions.append(f"({condition})")
            filter_string = " OR ".join(conditions)
            await db_delete(db_names=db_names, model_or_tablename=table_name, filter_string=filter_string)