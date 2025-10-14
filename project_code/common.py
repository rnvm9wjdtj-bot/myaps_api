
from typing import Dict, Any, List

from fastapi import status, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from tortoise import Tortoise
from tortoise.models import Model as TortoiseBaseModel
# from pydantic import ValidationError

from config.settings import DB_SET


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
        "data": data,
        "meta": meta
    }


# url - 公共参数
common_params = {
    "db_name": Query(DB_SET[0], description="账套"),
    "page_size": Query(1000, description="每页数量", gt=0, le=10000),
    "page_index": Query(0, description="分页页码，从0开始", ge=0)
}
# 路由公共方法 - 获取数据
async def common_get(db_name: str, model: TortoiseBaseModel, page_size: int, page_index: int):
    db = Tortoise.get_connection(db_name)
    # 分页查询
    offset = page_size * page_index
    materials = await model.all().using_db(db).offset(offset).limit(page_size)
    return standard_response(
        data=materials,
        meta={
            "total": await model.all().using_db(db).count(),
            "pageSize": page_size,
            "pageIndex": page_index,
        }
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

