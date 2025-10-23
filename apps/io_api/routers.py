from datetime import date, datetime, timedelta
from typing import List

from fastapi import APIRouter, Query, Body#, status, Request, Path

from config import forcustomer as fc
from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom, TSupply, TDemand#,TortoiseBaseModel
from .schemas import AcceptMaterial, AcceptWorkcenter, AcceptMatWc, AcceptMatVer, AcceptMatWcBom, AcceptSupply, AcceptDemand
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
    data: List[AcceptMaterial] = Body(..., description="新增或修改的物料数据"),
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
    data: List[AcceptMaterial],
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
    data: List[AcceptWorkcenter],
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
    data: List[AcceptMatWc],
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
    data: List[AcceptMatVer],
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
    data: List[AcceptMatWcBom],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TMatWcBom, data=data)


########################################################################
# 生产数据接口
@rt.get(
    "/t_supply",
    tags=["生产数据 - 供应"],
    summary="获取供应记录",
    description="获取供应记录"
)
async def get_supply(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get_by_orm(db_name=db_name, mdl=TSupply, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_supply",
    tags=["生产数据 - 供应"],
    summary="新增或修改供应记录",
    description="根据🗝️【料号+供应号】新增或修改生产记录"
    )
async def post_mat_production(
    data: List[AcceptSupply],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TSupply, data=data)

# 需求
@rt.get(
    "/t_demand",
    tags=["生产数据 - 需求"],
    summary="获取需求记录",
    description="获取需求记录"
)
async def get_demand(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"]
):
    return await common_get_by_orm(db_name=db_name, mdl=TDemand, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_demand",
    tags=["生产数据 - 需求"],
    summary="新增或修改需求记录",
    description="根据🗝️【料号+需求号+项目号】新增或修改需求记录"
    )
async def post_demand(
    data: List[AcceptDemand],
    db_name: str = common_params["db_name"]
    ):
    return await common_post(db_name=db_name, mdl=TDemand, data=data)
########################################################################
# 报表接口

@rt.get(
    "/v_supply_mo",
    tags=["报表 - 工单报表"],
    summary="获取工单报表",
    description="按工单开完工时间获取工单报表，默认开工时间为今日，默认完工时间为一周后。也支持按工单（供应）号筛选，若传工单（供应）号，则忽略时间筛选条件。"
)
async def get_supply_mo(
    db_name: str = common_params["db_name"],
    starttime: datetime = Query(date.today(), description="工单开工时间"),
    endtime: datetime = Query(date.today() + timedelta(days=7), description="工单完工时间"),
    supplyno: str = Query(None, description="工单（供应）号"),
):
    if supplyno:
        filter_string = f"SupplyNo = '{supplyno}'"
    else:
        starttime = starttime or date.today()
        endtime = endtime or starttime + timedelta(days=7)
        filter_string = f"DT_OrdStart >= '{starttime}' AND DT_OrdEnd <= '{endtime}'"
    return await common_get_by_sql(db_name=db_name, table_name="v_supply_mo", filter_string=filter_string, field_mapping=fc.v_supply_mo)

@rt.get(
    "/v_orderwc",
    tags=["报表 - 工序报表"],
    summary="获取工序报表",
    description="按工序开完工时间获取工序报表，默认开工时间为今日，默认完工时间为一周后。也支持按工单（供应）号筛选，若传工单（供应）号，则忽略时间筛选条件。"
)
async def get_orderwc(
    db_name: str = common_params["db_name"],
    starttime: datetime = Query(date.today(), description="工序开工时间"),
    endtime: datetime = Query(date.today() + timedelta(days=7), description="工序完工时间"),
    supplyno: str = Query(None, description="工单（供应）号"),
):
    if supplyno:
        filter_string = f"SupplyNo = '{supplyno}'"
    else:
        starttime = starttime or date.today()
        endtime = endtime or starttime + timedelta(days=7)
        filter_string = f"DT_Start >= '{starttime}' AND DT_End <= '{endtime}'"
    return await common_get_by_sql(db_name=db_name, table_name="v_orderwc", filter_string=filter_string, field_mapping=fc.v_orderwc)

@rt.get(
    "/v_matdailyqtyreport",
    tags=["报表 - 库存动态"],
    summary="获取库存动态报表",
    description="获取库存动态报表"
)
async def get_matdailyqtyreport(
    db_name: str = common_params["db_name"],
    startdate: date = Query(date.today(), description="开始日期"),
    enddate: date = Query(date.today() + timedelta(days=7), description="结束日期"),
    materialno: str = Query(None, description="料号"),
):
    startdate = startdate or date.today()
    enddate = enddate or startdate + timedelta(days=7)
    filter_string = f"DateStr >= '{startdate}' AND DateStr <= '{enddate}'"
    if materialno:
        filter_string = f"({filter_string}) AND MaterialNo = '{materialno}'"    
    return await common_get_by_sql(db_name=db_name, table_name="v_matdailyqtyreport", filter_string=filter_string, field_mapping=fc.v_matdailyqtyreport)
