from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Query#, status, Request, Path
from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom#,TortoiseBaseModel
from .schemas import MaterialInput, WorkcenterInput, MatWcInput, MatVerInput, MatWcBomInput, SupplyInput
from .common import common_params, common_get_by_orm, common_post, common_delete, common_get_by_sql

# 路由路径对应的数据资源
# data_source = {
#     "material": {"table": "t_material", "model": TMaterial},
#     "version": {"table": "t_mat_ver", "model": TMatVer},
#     "workcenter": {"table": "t_workcenter", "model": TWorkcenter},
# }

################################################################
rt = APIRouter()

########################################################################
# 主数据接口

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
    return await common_get_by_orm(db_name=db_name, mdl=TMaterial, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="新增或修改物料",
    description="根据🗝️【料号】新增或修改物料"
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
    description="根据🗝️【料号】删除物料"
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
    return await common_get_by_orm(db_name=db_name, mdl=TWorkcenter, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="新增或修改工作中心",
    description="根据🗝️【工作中心编号】新增或修改工作中心"
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
    return await common_get_by_orm(db_name=db_name, mdl=TMatWc, page_size=page_size, page_index=page_index)
    
@rt.post(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="新增或修改工序",
    description="根据🗝️【料号+产线版本号+工序项目】形成的联合索引新增或修改工序记录"
    )
async def post_mat_wc(
    data: List[MatWcInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatWc, data=data)

@rt.get(
    "/t_mat_ver",
    tags=["主数据 - 产线版本"],
    summary="获取产线版本信息",
    description="获取产线版本信息"
)
async def get_mat_ver(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get_by_orm(db_name=db_name, mdl=TMatVer, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_mat_ver",
    tags=["主数据 - 产线版本"],
    summary="新增或修改产线版本",
    description="根据🗝️【料号+产线版本号】形成的联合索引新增或修改产线版本记录"
    )
async def post_mat_ver(
    data: List[MatVerInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatVer, data=data)

@rt.get(
    "/t_mat_wc_bom",
    tags=["主数据 - 工序BOM"],
    summary="获取工序BOM信息",
    description="获取工序BOM信息"
)
async def get_mat_wc_bom(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get_by_orm(db_name=db_name, mdl=TMatWcBom, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_mat_wc_bom",
    tags=["主数据 - 工序BOM"],
    summary="新增或修改工序BOM",
    description="根据🗝️【产品料号+子件料号+产线版本号+工序项目】形成的联合索引新增或修改工序BOM记录"
    )
async def post_mat_wc_bom(
    data: List[MatWcBomInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatWcBom, data=data)


########################################################################
# 生产数据接口
@rt.post(
    "/t_mat_production",
    tags=["生产数据 - 供应"],
    summary="新增或修改供应记录",
    description="根据🗝️【料号+供应号】新增或修改生产记录"
    )
async def post_mat_production(
    data: List[SupplyInput],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatProduction, data=data)

########################################################################
# 报表接口

@rt.get(
    "/v_matdailyqtyreport",
    tags=["报表 - 库存动态"],
    summary="获取库存动态报表",
    description="获取库存动态报表"
)
async def get_matdailyqtyreport(
    db_name: str = common_params["db_name"],
    start_date: date = Query(date.today(), description="开始日期"),
    end_date: date = Query(date.today() + timedelta(days=30), description="结束日期"),
    materialno: str = Query(None, description="料号"),
):
    start_date = start_date or date.today()
    end_date = end_date or start_date
    filter_string = f"DateStr >= '{start_date}' AND DateStr <= '{end_date}'"
    if materialno:
        filter_string = f"({filter_string}) AND MaterialNo = '{materialno}'"    
    return await common_get_by_sql(db_name=db_name, table_name="v_matdailyqtyreport", filter_string=filter_string)
