from typing import Dict, Any, List
from enum import Enum

from fastapi import status, Query, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from tortoise import Tortoise
from tortoise.transactions import in_transaction
from tortoise.models import Model as TortoiseBaseModel
from pydantic import BaseModel as PydanticSchema

from config.settings import MYAPS_MAIN_DB
from config.globalconst import ORDER_STATUS, SUPPLY_TYPE


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
    "db_name": Query(MYAPS_MAIN_DB, description="账套"),
    "page_size": Query(1000, description="每页数量", gt=0, le=10000),
    "page_index": Query(0, description="分页页码，从0开始", ge=0),
    "supply_type": Query(..., description="供应类型", openapi_examples={key: {"value": key, "summary": value} for key, value in SUPPLY_TYPE.items()}),
}


########################################################################

# 路由公共方法
async def common_read_by_orm(db_name: str, mdl: TortoiseBaseModel, page_size: int, page_index: int):
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
    return standard_response(
        data=data,
        meta={
            "total": await mdl.all().using_db(db).count(),
            "pageSize": page_size,
            "pageIndex": page_index,
        }
    )


async def common_write(db_name: str, mdl: TortoiseBaseModel, data: List[PydanticSchema | Dict[str, Any]]):

    unique_together = mdl._meta.unique_together
    model_key = unique_together[0] if unique_together else [mdl._meta.pk_attr]
    only_fields = [f for f in mdl._meta.fields if f != "vid"] if len(model_key) > 1 else None

    dbs = db_name.split(",")
    data_dict_list = []
    for _d in data:
        # _d_dict = _d.model_dump(exclude_unset=True, exclude_none=True) if isinstance(_d, PydanticSchema) else _d
        _d_dict = _d.model_dump(exclude_none=True) if isinstance(_d, PydanticSchema) else _d
        data_dict_list.append(_d_dict)

    success_db = []
    cerate_count_total = 0
    update_count_total = 0
    try:
        for _db in dbs:
            cerate_count = 0
            update_count = 0

            async with in_transaction(_db) as db:
                for _d in data_dict_list:
                    if hasattr(_d, "_overwrite"):   # 当联合主键之一需要被覆写，_overwrite = {"match_on": {...}, "new_value": {...}}
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
                            update_count_total += 1
                        else:
                            await mdl.create(**_d_dict, using_db=db)
                            cerate_count += 1
                            cerate_count_total += 1
                    else:
                        match_on = {k : _d_dict.get(k) for k in model_key}
                        if len(model_key) > 1:     # 如果是联合主键，则要排除虚拟主键的干扰
                            if await mdl.filter(**match_on).only(*only_fields).using_db(db).exists():
                                # 先删除None值
                                for k, v in _d_dict.items():
                                    if v is None:
                                        _d_dict.pop(k)
                                await mdl.filter(**match_on).only(*only_fields).first().using_db(db).update(**_d_dict)# 必须重新写一遍查询逻辑，因为前面返回的是一个对象，不能直接update
                                update_count += 1
                                update_count_total += 1
                            else:
                                await mdl.create(**_d_dict, using_db=db)
                                cerate_count += 1
                                cerate_count_total += 1
                        else:   # 单一主键
                            exist = await mdl.get_or_none(**match_on, using_db=db)
                            # exist = await mdl.filter(**match_on).using_db(db).first()
                            if exist:
                                _d_dict.pop(model_key[0])
                                await exist.update_from_dict(_d_dict).save(using_db=db)
                                update_count += 1
                                update_count_total += 1
                            else:
                                await mdl.create(**_d_dict, using_db=db)
                                cerate_count += 1
                                cerate_count_total += 1

            success_db.append({"db_name": _db, "create": cerate_count, "update": update_count})
        
        return standard_response(
            data=data_dict_list,
            message=f"生效{len(success_db)}个账套，总计新增{cerate_count_total}条，修改{update_count_total}条",
            meta=success_db
            )
    except Exception as e:
        return standard_response(
            success=0,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)} —— common_write",
            meta={"success_db": success_db, "error_db": _db},
            data=data_dict_list
        )

# 路由公共方法 - delete
async def common_delete_by_orm(db_name: str, mdl: TortoiseBaseModel, targets: List[dict]):
    delete_count = 0
    try:
        async with in_transaction(db_name) as db:
            for _ in targets:
                exist = await mdl.get_or_none(**_, using_db=db)
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
                count, data  = await db.execute_query(f'CALL {procedure_name}({", ".join(["%s"] * len(params))})', params)
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
        db = Tortoise.get_connection(db_name)
        where = f" WHERE {filter_string}" if filter_string else ''
        order = f" ORDER BY {order_string}" if order_string else ''
        sql = f'SELECT * FROM `{table_name}` {where} {order}'
        total, data = await db.execute_query(sql)
        lower_keys_data = [dict_to_lower_keys(row) for row in data]
        await db.close()
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
    try:
        db = Tortoise.get_connection(db_name)
        where = f" WHERE {filter_string}" if filter_string else ''
        sql = f'DELETE FROM `{table_name}` {where}'
        total, data = await db.execute_query(sql)
        await db.close()
        return standard_response(
            data=data,
            meta={"total": total}
        )
    except Exception as e:
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
