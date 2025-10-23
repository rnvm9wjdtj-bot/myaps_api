# from typing import Dict, Any, List

# from fastapi import status, Query, HTTPException, Request
# from fastapi.responses import JSONResponse
# from fastapi.exceptions import RequestValidationError
# from tortoise import Tortoise
# from tortoise.transactions import in_transaction
# from tortoise.models import Model as TortoiseBaseModel
# from pydantic import BaseModel as PydanticSchema

# from config.settings import MYAPS_DB_SET


# # 路由相关公共格式
# def standard_response(
#     status_code: int = status.HTTP_200_OK,
#     success: int = 1,
#     message: str = "success",
#     data: Any = None,
#     meta: Dict[str, Any] = None
# ):
#     return {
#         "status_code": status_code,
#         "success": success,
#         "message": message,
#         "meta": meta,
#         "data": data
#     }

# # url - 公共参数
# common_params = {
#     "db_name": Query(MYAPS_DB_SET[0], description="账套"),
#     "page_size": Query(1000, description="每页数量", gt=0, le=10000),
#     "page_index": Query(0, description="分页页码，从0开始", ge=0)
# }

# ########################################################################

# # 路由公共方法 - get
# async def common_get_by_orm(db_name: str, mdl: TortoiseBaseModel, page_size: int, page_index: int):
#     db = Tortoise.get_connection(db_name)
#     # 分页查询
#     offset = page_size * page_index
#     if mdl._meta.unique_together:   # 如果是联合主键，则要排除虚拟主键的干扰
#         only_fields = [f for f in mdl._meta.fields if f != "vid"]
#         data = await mdl.all().only(*only_fields).using_db(db).offset(offset).limit(page_size)
#     else:
#         data = await mdl.all().using_db(db).offset(offset).limit(page_size)
#     return standard_response(data=data)

# # 注册异常处理器
# def register_exception_handlers(app):
#     # 全局异常处理 - 请求验证错误
#     @app.exception_handler(RequestValidationError)
#     async def validation_exception_handler(request: Request, exc: RequestValidationError):
#         return JSONResponse(
#             status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#             content=standard_response(
#                 status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
#                 success=0,
#                 message="请求参数验证失败",
#                 data={"detail": exc.errors()}
#             )
#         )

#     # 全局异常处理 - HTTPException
#     @app.exception_handler(HTTPException)
#     async def http_exception_handler(request: Request, exc: HTTPException):
#         return JSONResponse(
#             status_code=exc.status_code,
#             content=standard_response(
#                 status_code=exc.status_code,
#                 success=0,
#                 message=exc.detail or "请求失败"
#             )
#         )

#     # 全局异常处理 - 通用异常
#     @app.exception_handler(Exception)
#     async def general_exception_handler(request: Request, exc: Exception):
#         return JSONResponse(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             content=standard_response(
#                 status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                 success=0,
#                 message=f"服务器内部错误: {str(exc)}"
#             )
#         )