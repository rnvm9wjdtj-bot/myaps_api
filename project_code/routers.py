from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Request, status, Query, Path
from fastapi.responses import JSONResponse
# from pydantic import BaseModel
from tortoise import Tortoise
from tortoise.transactions import in_transaction

from config.settings import DB_SET
from .models import TortoiseBaseModel, TMaterial
from .schemas import MaterialSchema


# tables = {
#     "t_material": TMaterial,
# }

################################################################
# 统一返回格式
def standard_response(
    code: int = status.HTTP_200_OK,
    message: str = "success",
    data: Any = None,
    meta: Dict[str, Any] = None
):
    return {
        "code": code,
        "message": message,
        "data": data,
        "meta": meta
    }

async def common_get(model: TortoiseBaseModel, db_name: str, page_size, page_index):
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
rt = APIRouter()

@rt.get("/material", tags=["主数据"], summary="获取物料信息", description="获取物料信息")
async def get_material(
    db_name: str = Query(DB_SET[0], description="账套"),
    page_size: int = Query(1000, description="每页数量", gt=0, le=10000),
    page_index: int = Query(0, description="分页页码，从0开始", ge=0)
    ):
    return await common_get(TMaterial, db_name, page_size, page_index)


@rt.post("/material", tags=["主数据"], summary="新增或修改", description="根据料号新增或修改物料")
async def post_material(data: List[MaterialSchema], db_name: str = Query(DB_SET[0], description="账套")):
    try:
        async with in_transaction(db_name) as db:
            # 批量查询现有物料（减少数据库查询次数）
            materialnos = [m.materialno for m in data]
            existing_materials = {m.materialno: m for m in await TMaterial.filter(materialno__in=materialnos).all()}
            # 批量创建/更新
            for material in data:
                if material.materialno in existing_materials:
                    await existing_materials[material.materialno].update_from_dict(
                        material.model_dump(exclude={"materialno"})
                    ).save(using_db=db)
                else:
                    await TMaterial.create(**material.model_dump(), using_db=db)
        return standard_response(data=data)
    except Exception as e:
        return standard_response(
            code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=str(e)
        )