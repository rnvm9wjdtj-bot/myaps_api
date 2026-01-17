from typing import Dict, Any, List, Tuple

from fastapi import status, Query, HTTPException, status, Request, Header
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_MAIN_DB
from globalobjects.globalconst import SupplyTypeEnum
from globalobjects import file_timed_logger



file_logger = file_timed_logger.setup_logging(__name__)



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
    "supply_type": Query(..., description="供应类型", openapi_examples={key: {"value": key, "summary": value} for key, value in SupplyTypeEnum.__members__.items()}),
    "x_api_key": Header(None, description="API密钥")
}


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