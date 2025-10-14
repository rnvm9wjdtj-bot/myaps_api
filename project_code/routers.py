# from datetime import datetime
from typing import List

from fastapi import APIRouter, status#, Query, Request, Path
from tortoise.transactions import in_transaction

from .models import TMaterial, TMatVer, TWorkcenter#,TortoiseBaseModel
from .schemas import SchemaMaterial
from .common import standard_response, common_params, common_get

# 路由路径对应的数据资源
data_source = {
    "material": {"table": "t_material", "model": TMaterial},
    "version": {"table": "t_mat_ver", "model": TMatVer},
    "workcenter": {"table": "t_workcenter", "model": TWorkcenter},
}

################################################################

################################################################
rt = APIRouter()

@rt.get("/material", tags=["主数据 - 物料"], summary="获取物料信息", description="获取物料信息")
async def get_material(db_name: str = common_params["db_name"], page_size: int = common_params["page_size"], page_index: int = common_params["page_index"]):
    return await common_get(db_name, data_source["material"]["model"], page_size, page_index)


@rt.post("/material", tags=["主数据 - 物料"], summary="新增或修改物料", description="根据料号新增或修改物料")
async def post_material(data: List[SchemaMaterial], db_name: str = common_params["db_name"]):
    mdl = TMaterial
    model_key = ("materialno", )
    cerate_count = 0
    update_count = 0
    
    try:
        print('尝试开启数据库事务处理...')
        async with in_transaction(db_name) as db:
            for _d in data:
                match_on = {k : _d.__dict__.get(k) for k in model_key}
                exist = await mdl.get_or_none(**match_on, using_db=db)
                if exist:
                    await exist.update_from_dict(
                        _d.model_dump(exclude=model_key)
                    ).save(using_db=db)
                    update_count += 1
                else:
                    await mdl.create(**_d.model_dump(), using_db=db)
                    cerate_count += 1
        return standard_response(message=f"新增{cerate_count}条，修改{update_count}条", meta={"create": cerate_count, "update": update_count})
    except Exception as e:
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"操作失败：{str(e)}"
        )