# from datetime import datetime
from typing import List

from fastapi import APIRouter, status#, Query, Request, Path
from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom#,TortoiseBaseModel
from .schemas import MaterialInput, WorkcenterInput, MatWcInput, MatVerInput, MatWcBomInput
from .common import common_params, common_get, common_post, common_delete

# 路由路径对应的数据资源
# data_source = {
#     "material": {"table": "t_material", "model": TMaterial},
#     "version": {"table": "t_mat_ver", "model": TMatVer},
#     "workcenter": {"table": "t_workcenter", "model": TWorkcenter},
# }

################################################################
rt = APIRouter()

@rt.get(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="获取物料信息",
    description="获取物料信息"
)
async def get_material(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get(db_name=db_name, mdl=TMaterial, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="新增或修改物料",
    description="根据料号新增或修改物料"
    )
async def post_material(
    data: List[MaterialInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMaterial, data=data)

@rt.delete(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="删除物料",
    description="根据料号删除物料"
    )
async def delete_material(
    data: List[MaterialInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_delete(db_name=db_name, mdl=TMaterial, model_key=("materialno", ), data=data)

@rt.get(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="获取工作中心信息",
    description="获取工作中心信息"
)
async def get_workcenter(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get(db_name=db_name, mdl=TWorkcenter, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="新增或修改工作中心",
    description="根据编号新增或修改工作中心"
    )
async def post_workcenter(
    data: List[WorkcenterInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TWorkcenter, data=data)

@rt.get(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="获取工序信息",
    description="获取工序信息"
)
async def get_mat_wc(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get(db_name=db_name, mdl=TMatWc, page_size=page_size, page_index=page_index)
    
@rt.post(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="新增或修改工序",
    description="根据料号、产线版本、工序项目形成的联合索引新增或修改工序"
    )
async def post_mat_wc(
    data: List[MatWcInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatWc, data=data)
