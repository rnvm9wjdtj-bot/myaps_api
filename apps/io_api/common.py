from typing import Dict, Any, List

from fastapi import status, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from tortoise import Tortoise
from tortoise.transactions import in_transaction
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_DEFAULT_DB


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
    "db_name": Query(MYAPS_DEFAULT_DB, description="账套"),
    "page_size": Query(1000, description="每页数量", gt=0, le=10000),
    "page_index": Query(0, description="分页页码，从0开始", ge=0)
}

########################################################################

# 路由公共方法 - get
async def common_get_by_orm(db_name: str, mdl: TortoiseBaseModel, page_size: int, page_index: int, field_mapper: Dict[str, str] = None):
    db = Tortoise.get_connection(db_name)
    # 分页查询
    offset = page_size * page_index
    if mdl._meta.unique_together:   # 如果是联合主键，则要排除虚拟主键的干扰
        # model_fields = set(mdl._meta.fields)
        # only_fields = model_fields - {"vid", }     # 必须用set集合{"vid", }
        only_fields = [f for f in mdl._meta.fields if f != "vid"]
        data = await mdl.all().only(*only_fields).using_db(db).offset(offset).limit(page_size)
    else:
        data = await mdl.all().using_db(db).offset(offset).limit(page_size)
    if field_mapper:
        data = [{field_mapper.get(k, k): v for k, v in d.items()} for d in data]
    return standard_response(
        data=data,
        meta={
            "total": await mdl.all().using_db(db).count(),
            "pageSize": page_size,
            "pageIndex": page_index,
        }
    )

async def common_post(db_name: str, mdl: TortoiseBaseModel, data: List[PydanticSchema]):
    cerate_count = 0
    update_count = 0
    unique_together = mdl._meta.unique_together
    model_key = unique_together[0] if unique_together else [mdl._meta.pk_attr]
    only_fields = [f for f in mdl._meta.fields if f != "vid"] if len(model_key) > 1 else None
    try:
        async with in_transaction(db_name) as db:
            for _d in data:
                _d_dict = _d.model_dump()
                if hasattr(_d, "_overwrite"):   # 当联合主键之一需要被覆写
                    match_on = _d._overwrite["match_on"]
                    new_value = _d._overwrite["new_value"]
                    if await mdl.filter(**match_on).only(*only_fields).using_db(db).exists():
                        where_clause = " AND ".join([f"{k} = '{v}'" for k, v in match_on.items()])
                        sql = f"""
                            UPDATE {mdl._meta.db_table}
                            SET {", ".join([f"{k} = '{v}'" for k, v in new_value.items() if k != "vid"])}
                            WHERE {where_clause}
                        """
                        await db.execute_query(sql)
                        update_count += 1
                    else:
                        await mdl.create(**_d_dict, using_db=db)
                        cerate_count += 1
                else:
                    match_on = {k : _d_dict.get(k) for k in model_key}
                    if len(model_key) > 1:     # 如果是联合主键，则要排除虚拟主键的干扰
                        if await mdl.filter(**match_on).only(*only_fields).using_db(db).exists():
                            # 先删除None值
                            keys_to_remove = [k for k, v in _d_dict.items() if v is None]
                            for key in keys_to_remove:
                                del _d_dict[key]
                            await mdl.filter(**match_on).only(*only_fields).first().using_db(db).update(**_d_dict)# 必须重新写一遍查询逻辑，因为前面返回的是一个对象，不能直接update
                            update_count += 1
                        else:
                            await mdl.create(**_d_dict, using_db=db)
                            cerate_count += 1
                    else:   # 单一主键
                        exist = await mdl.get_or_none(**match_on, using_db=db)
                        if exist:
                            await exist.update_from_dict(_d_dict).save(using_db=db, force_update=True, force_create=False)
                            update_count += 1
                        else:
                            await mdl.create(**_d_dict, using_db=db)
                            cerate_count += 1
        return standard_response(
            message=f"新增{cerate_count}条，修改{update_count}条",
            meta={"create": cerate_count, "update": update_count}
            )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)} —— common_post"
        )

# 路由公共方法 - delete
async def common_delete(db_name: str, mdl: TortoiseBaseModel, model_key: tuple[str], data: List[PydanticSchema]):
    delete_count = 0
    try:
        async with in_transaction(db_name) as db:
            for _d in data:
                _d_dict = _d.model_dump()
                match_on = {k : _d_dict.get(k) for k in model_key}
                exist = await mdl.get_or_none(**match_on, using_db=db)
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


async def common_get_by_sql(db_name: str, table_name: str, filter_string: str, field_mapper: Dict[str, str] = {}):
    db = Tortoise.get_connection(db_name)
    where = f" WHERE {filter_string}" if filter_string else ''
    sql = f'SELECT * FROM `{table_name}` {where}'
    total, data = await db.execute_query(sql)
    # 映射字段名
    if field_mapper:
        data = [{field_mapper.get(k, k): v for k, v in row.items()} for row in data]
    db.close()
    return standard_response(
        data=data,
        meta={"total": total}
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

