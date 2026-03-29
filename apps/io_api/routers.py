from datetime import date, datetime, timedelta
# from re import S
# from this import d
from typing import List, Dict, Optional, Literal#, Any
import inspect, functools, pandas as pd
# import httpx

from fastapi import APIRouter, Path, Query, Body, status#, Request
# from tortoise import Tortoise

from config.settings import MYAPS_DB_SET, MYAPS_DBSET_LIST, MYAPS_MAIN_DB, THIS_BASE_URL
from globalobjects import globalconst as gc
# from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom, TSupply, TDemand, TMold, TMatWcMold, TConfirm#,TortoiseBaseModel
from .schemas import (
    AcceptMaterial, AcceptWorkcenter, AcceptMatWc, AcceptMatVer, AcceptMatWcBom, AcceptSupply, AcceptDemand, AcceptMold, AcceptMatWcMold, AcceptConfirm,
    ModifySupply, ModifyDemand
    #DeleteSupply
)

from .utils.common import common_params, standard_response
from .utils.db_operation import db_managers, db_query, db_supsert, db_bupsert, db_delete, call_dbprocdure, db_update_by_index
from project_files import hap_conn
from apps.data_opt.utils.data_processor import DataProcessor



# def _check_db_name(hap_wsid: str = None):
#     """
#     检查函数是否有db_name参数，如果没有则调用 HAP API
#     """
#     def decorator(func):
#         @functools.wraps(func)
#         async def wrapper(*args, **kwargs):
#             # 获取函数签名
#             sig = inspect.signature(func)
            
#             # 查找db_name参数
#             db_name_param = None
#             db_name_index = None
#             for i, (param_name, param) in enumerate(sig.parameters.items()):
#                 if param_name == 'db_name':
#                     db_name_param = param
#                     db_name_index = i
#                     break
            
#             # 获取db_name的值
#             db_name = None
            
#             if db_name_param is not None:
#                 if db_name_index is not None and db_name_index < len(args):
#                     # db_name作为位置参数传递
#                     db_name = args[db_name_index]
#                 elif 'db_name' in kwargs:
#                     # db_name作为关键字参数传递
#                     db_name = kwargs['db_name']
#                 else:
#                     # 使用默认值
#                     db_name = db_name_param.default
            
#             # 如果没有db_name参数或db_name为None或空，调用 HAP API
#             if db_name_param is None or db_name is None or db_name == "":
#                 # 获取原函数的data参数
#                 data_param = None
#                 data_index = None
#                 for i, (param_name, param) in enumerate(sig.parameters.items()):
#                     if param_name == 'data':
#                         data_param = param
#                         data_index = i
#                         break
                
#                 # 获取data的值
#                 data_value = None
#                 if data_param is not None:
#                     if data_index is not None and data_index < len(args):
#                         # data作为位置参数传递
#                         data_value = args[data_index]
#                     elif 'data' in kwargs:
#                         # data作为关键字参数传递
#                         data_value = kwargs['data']
#                     else:
#                         # 使用默认值
#                         data_value = data_param.default
                
#                 # 处理pydantic对象列表到字典列表的转换
#                 processed_data = None
#                 if data_value is not None:
#                     if hasattr(data_value, '__iter__') and not isinstance(data_value, (str, bytes)):
#                         # 处理列表或可迭代对象
#                         processed_data = []
#                         for item in data_value:
#                             processed_data.append(item._cached_raw_input_data)
#                     else:
#                         # 单个对象
#                         if hasattr(data_value, 'dict'):
#                             # pydantic v1 model
#                             processed_data = data_value.dict()
#                         elif hasattr(data_value, 'model_dump'):
#                             # pydantic v2 model
#                             processed_data = data_value.model_dump()
#                         else:
#                             # 普通对象
#                             processed_data = data_value
                
#                 try:
#                     if hap_conn is not None:
#                         result = hap_conn.worksheet(hap_wsid).create_rows(
#                             data_list=processed_data,
#                             trigger_workflow=True
#                         )
#                         return standard_response(
#                             status_code=status.HTTP_200_OK,
#                             success=1,
#                             message="HAP create rows success",
#                             data=result
#                         )
#                     else:
#                         return standard_response(
#                             status_code=status.HTTP_400_BAD_REQUEST,
#                             success=0,
#                             message="no db_name parameter or db_name is empty, trigger hap call"
#                         )
#                 except Exception as e:
#                     return standard_response(
#                         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                         success=0,
#                         message=f"HAP create rows failed: {str(e)}"
#                     )
            
#             # db_name有效，正常执行原函数
#             return await func(*args, **kwargs)
#         return wrapper
#     return decorator


########################################################################
rt = APIRouter()
########################################################################
########################################################################
# 主数据接口
########################################################################

@rt.get("/meta")
async def get_meta():
    return standard_response(
        success=1,
        message="获取元数据成功",
        meta={
            "db_set": MYAPS_DBSET_LIST,
            "dbs_str": MYAPS_DB_SET,
            "main_db": MYAPS_MAIN_DB,
        },
    )
    


@rt.get(
    "/v_material/{materialnos}",
    tags=["主数据 - 物料"],
    summary="根据料号获取物料信息",
    description="根据料号获取物料信息"
)
async def get_material(
    materialnos: str = Path(..., description="料号，多个用逗号隔开"),
    db_name: str = common_params["db_name"]
):
    db_name = db_name.replace(" ", "")
    materialnos = ",".join([f"'{_}'" for _ in materialnos.split(",")])
    filter_string = f"`MaterialNo` IN ({materialnos})"
    materials = await db_query(db_name=db_name, model_or_tablename="v_material", filter_string=filter_string)
    return materials



@rt.post(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="新增或修改物料",
    description="根据🗝️【料号】新增或修改物料"
)
async def post_material(
    data: List[AcceptMaterial] = Body(..., description="新增或修改的物料数据"),
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_material", data_list=data) 



@rt.post(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="新增或修改工作中心",
    description="根据🗝️【工作中心编号】新增或修改工作中心"
)
async def post_workcenter(
    data: List[AcceptWorkcenter],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    # if len(data) > 1:
    #     return await db_bupsert(db_names=db_name, model_or_tablename="t_workcenter", data_list=data)
    # else:
    #     return await db_supsert(db_names=db_name, model_or_tablename="t_workcenter", data_item=data[0])
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_workcenter", data_list=data)



@rt.post(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="新增或修改工序",
    description="根据🗝️【料号+产线版本号+工序项目】形成的联合索引新增或修改工序记录"
)
async def post_mat_wc(
    data: List[AcceptMatWc | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_mat_wc", data_list=data)


@rt.post(
    "/t_mat_ver",
    tags=["主数据 - 产线版本"],
    summary="新增或修改产线版本",
    description="根据🗝️【料号+产线版本号】形成的联合索引新增或修改产线版本记录"
)
async def post_mat_ver(
    data: List[AcceptMatVer | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_mat_ver", data_list=data)


@rt.post(
    "/t_mat_wc_bom",
    tags=["主数据 - BOM"],
    summary="新增或修改BOM",
    description="根据🗝️【产品料号+子件料号+产线版本号+工序项目】形成的联合索引新增或修改BOM记录"
)
async def post_mat_wc_bom(
    data: List[AcceptMatWcBom | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_mat_wc_bom", data_list=data)


@rt.post(
    "/t_mold",
    tags=["主数据 - 模具"],
    summary="新增或修改模具",
    description="根据🗝️【模具编号】新增或修改模具"
)
async def post_mold(
    data: List[AcceptMold | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_mold", data_list=data)


@rt.post(
    "/t_mat_wc_mold",
    tags=["主数据 - 机台模具"],
    summary="新增或修改机台模具",
    description="根据🗝️【料号+工作中心+工序项目+模具编号】形成的联合索引新增或修改机台模具记录"
)
async def post_mat_wc_mold(
    data: List[AcceptMatWcMold | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_mat_wc_mold", data_list=data)


########################################################################
# 生产数据接口
########################################################################
@rt.get(
    "/v_supply/{supplyno}",
    tags=["生产数据 - 供应"],
    summary="获取供应记录",
    description="获取供应记录"
)
async def get_supply(
    db_name: str = common_params["db_name"],
    supplyno: str = Path(..., description="供应号"),
    # type_: str = Path(..., enum=['PL', 'MO', 'PR', 'PO'], description="供应类型"),
):
    filter_string = f"`SupplyNo`='{supplyno}'"
    # if not type_ == "...":
    #     filter_string += f" AND `Type`='{type_}'"
    supply_query_result = await db_query(db_name=db_name, model_or_tablename="v_supply", filter_string=filter_string)
    supply_data = supply_query_result['data']

    # if supply_data:
    #     for item in supply_data:
    #         vendorno = item.get('vendorno')
    #         if vendorno:
    #             so_query_result = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=f"`DemandNo`='{vendorno}' AND `Type`='SO'")
    #             so_data = so_query_result['data']
    #             if so_data:
    #                 item['so'] = so_data[0]
    return standard_response(data=supply_data)


@rt.post("/t_supply",
    tags=["生产数据 - 供应"],
    summary="新增或修改供应记录（供应来源包含：生产生产计划PL、生产工单MO、库存ST、采购订单PO）",
    description="根据🗝️【料号+供应号】新增或修改供应记录"
)
async def post_supply(
    data: List[AcceptSupply | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_supply", data_list=data)



@rt.patch(
    "/t_supply/{supplyno}/{materialno}",
    tags=["生产数据 - 供应"],
    summary="修改供应记录",
    description="根据供应号、料号修改供应记录"
)
async def patch_supply_by_materialno(
    supplyno: str = Path(..., description="要修改的供应记录的供应号"),
    materialno: str = Path(..., description="料号"),
    data: ModifySupply = Body(..., description="修改为这些信息"),
    if_not_exist: Literal["skip", "insert"] = Query("skip", description="如果不存在如何处理"),
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    if isinstance(data, ModifySupply):
        data = data.model_dump(exclude_unset=True)
        # data = data.model_dump()
    if "supplyno" in data:
        data.pop("supplyno")    # 从data中移除supplyno，防止意外修改 供应号
    index_dict = {"SupplyNo": supplyno}
    if not materialno == "...":
        index_dict["MaterialNo"] = materialno
    return await db_update_by_index(
        db_names=db_name,
        model_or_tablename="t_supply",
        index_dict=index_dict,
        new_values_dict=data,
        not_found_behavior=if_not_exist
    )



@rt.patch(
    "/t_supply/{supplyno}",
    tags=["生产数据 - 供应"],
    summary="将 PL 转为 MO",
    description="根据供应号更新 PL 记录 ，转化时允许修改供应号"
)
async def patch_supply(
    supplyno: str = Path(..., description="要修改的供应记录的供应号"),
    data: ModifySupply = Body(..., description="修改为这些信息"),
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    query_result = await db_query(db_name=db_name, model_or_tablename="t_supply", filter_string=f"`SupplyNo`='{supplyno}'")

    query_data = query_result['data']
    if not query_data[0]["type"] == "PL":
        return standard_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            success=0,
            message=f"Supply {supplyno} is not a PL.")

    if isinstance(data, ModifySupply):
        # data = data.model_dump(exclude_unset=True, exclude_none=True)
        data = data.model_dump(exclude_none=True)
    data['materialno'] = query_data[0]['materialno']
    # 如果未指定供应号，则延用
    if not data.get('supplyno'):
        data['supplyno'] = supplyno
    # 调用存储过程SupplyConvertMOByE2A，将PL转为MO
    params_list = [[supplyno, data['supplyno'], data['status'], data['apiex_id'], data['apiex_entryid'], data['memo']]]
    return await call_dbprocdure(db_names=db_name, procedure_name="SupplyConvertMOByE2A", params_list=params_list)
    


@rt.put("/t_supply/type/{type_}",
    tags=["生产数据 - 供应"],
    summary="按类型替换供应记录",
    description="根据供应类型删除所有该类型的供应记录，然后新增这些供应记录。可用于库存、PO等单据刷新"
)
async def replace_supply(
    db_name: str = common_params["db_name"],
    type_: str = Path(..., enum=['PL', 'MO', 'PR', 'PO', 'ST'], description="供应类型"),
    data: List[AcceptSupply | Dict] = Body(..., description="替换为这些供应记录"),
    x_api_key: str = common_params["x_api_key"]
):
    wrong_type_count = 0
    for item in data:
        if item.get('type') != type_:
            wrong_type_count += 1
    if wrong_type_count > 0:
        return standard_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            success=0,
            message=f"Supply type {type_} in data does not match.")
            
    db_name = db_name.replace(" ", "")
    delete_result = await db_delete(db_names=db_name, model_or_tablename="t_supply", filter_string=f"`Type`='{type_}'")
    if data:
        create_result = await db_bupsert(db_names=db_name, model_or_tablename="t_supply", data_list=data)
        return create_result
    else:
        return delete_result


@rt.delete(
    "/t_supply/{supplyno}",
    tags=["生产数据 - 供应"],
    summary="删除供应记录",
    description="根据供应号删除供应记录。若为MO PL，还会删除关联的工序记录和报工记录"
)
async def delete_supply(
    db_name: str = common_params["db_name"],
    supplyno: str = Path(..., description="要删除的供应记录的供应号"),
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo`='{supplyno}'"
    query_result = await db_query(db_name=db_name, model_or_tablename="t_supply", filter_string=filter_string)
    result = await db_delete(db_names=db_name, model_or_tablename="t_supply", filter_string=filter_string)
    _type = query_result['data'][0]['type']
    if result['success']: # 删除关联的工序记录、报工
        orderwc_delete_result = await db_delete(db_names=db_name, model_or_tablename="t_orderwc", filter_string=filter_string)
        confirm_delete_result = await db_delete(db_names=db_name, model_or_tablename="t_confirm", filter_string=filter_string)
        return standard_response(
            success=1,
            message=f"Supply {supplyno} deleted successfully.")
    else:
        return standard_response(
            status_code=result["status_code"],
            success=0,
            message=result["message"])



# 需求
@rt.get(
    "/v_demand/{demandno}",
    tags=["生产数据 - 需求"],
    summary="根据需求号获取物料需求详情",
    description="根据 APS pegging 算法，需求号与供应号一致，所以该接口也即是：根据工单的 supplyno 获取原料需求"
)
async def get_demand(
    db_name: str = common_params["db_name"],
    demandno: str = Path(..., description="需求号"),
    # type_: str = Path(..., enum=["DM", "RS"], description="需求类型"),
):
    filter_string = f"`DemandNo`='{demandno}'"
    # if not type_ == "...":
    #     filter_string += f" AND `Type`='{type_}'"
    # else:   # 默认查找生产相关的全部类型需求
    #     filter_string += f" AND `Type` IN ('DM', 'RS')"

    query_result_demand = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=filter_string)
    if query_result_demand["success"] == 0:
        return query_result_demand
    query_result_supply = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=f"`SupplyNo`='{demandno}'")
    if query_result_supply["success"] == 0:
        return query_result_demand
    if query_result_supply["data"]:
        # 合并需求和供应数据
        query_result_demand["meta"]["mo"] = query_result_supply["data"][0]
    return query_result_demand


@rt.post(
    "/t_demand",
    tags=["生产数据 - 需求"],
    summary="新增或修改需求记录（需求来源包含：销售订单SO、计划需求DM、工单预留RS、预测FC、安全库存SS）",
    description="根据🗝️【料号+需求号+项目号】新增或修改需求记录"
)
async def post_demand(
    data: List[AcceptDemand | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_demand", data_list=data)



@rt.patch(
    "/t_demand/{demandno}/{materialno}/{itemno}",
    tags=["生产数据 - 需求"],
    summary="修改需求记录",
    description="根据需求号修改记录"
)
async def patch_demand(
    demandno: str = Path(..., description="需要修改的需求记录的需求号"),
    materialno: str = Path(..., description="料号"),
    itemno: str = Path(..., description="项目号"),
    data: ModifyDemand = Body(..., description="修改为这些信息"),
    db_name: str = common_params["db_name"],
    if_not_exist: Literal["skip", "insert"] = Query("skip", description="如果不存在如何处理"),
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    index_dict = {"DemandNo": demandno}
    if not materialno == "...":
        index_dict["MaterialNo"] = materialno
    if not itemno == "...":
        index_dict["ItemNo"] = itemno

    # new_values_dict = data.model_dump(exclude_unset=True, exclude_none=True)
    new_values_dict = data.model_dump(exclude_none=True)
    # new_values_dict['apiex_sn'] = demandno    # 已在MOA2E存储过程修改
    response = await db_update_by_index(
        db_names=db_name,
        model_or_tablename="t_demand",
        index_dict=index_dict,
        new_values_dict=new_values_dict,
        not_found_behavior=if_not_exist,
    )

    return response
########################################################################
# 报表接口
########################################################################
@rt.get(
    "/v_supply_mo/{supplyno}",
    tags=["报表 - 工单报表"],
    summary="获取工单报表",
    description="按供应号获取工单信息。"
)
async def get_mo_by_supplyno(
    db_name: str = common_params["db_name"],
    supplyno: str = Path(..., description="工单（供应）号"),
    prev_mo: bool = Query(False, description="是否查询前 前置 工单"),
    next_mo: bool = Query(False, description="是否查询后 后续 工单"),
    # x_api_key: str = common_params["x_api_key"]
):

    async def get_prev_mo(mono: str):
        """
        通过工单 supplyno 号查询前 前置 工单
        """
        for_demands = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=f"`DemandNo`='{mono}' AND `Type` IN ('DM', 'RS', 'PR', 'PO')")
        demands_data = for_demands['data']
        prev_mo = []
        if demands_data:
            demands_no = ','.join([f"'{i['demandno']}'" for i in demands_data])
            peg_query_result = await db_query(db_name=db_name, model_or_tablename="v_peg", filter_string=f"`DemandNo` IN ({demands_no}) AND `S_Type` IN ('PL', 'MO')")
            if peg_query_result['data']:
                supplies_no = ','.join([f"'{i['s_supplyno']}'" for i in peg_query_result['data']])
                prev_mo_query_result = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=f"`SupplyNo` IN ({supplies_no})")
                prev_mo = prev_mo_query_result['data']
        return prev_mo

    async def get_next_mo(mono: str): 
        """
        通过工单 supplyno 号查询后 后置 工单
        """
        in_pegs = await db_query(db_name=db_name, model_or_tablename="v_peg", filter_string=f"`S_SupplyNo`='{mono}' AND `Type` IN ('DM', 'RS')")
        pegs_data = in_pegs['data']
        next_mo = []
        if pegs_data:
            demands_no = ','.join([f"'{i['demandno']}'" for i in pegs_data])
            next_mo_query_result = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=f"`SupplyNo` IN ({demands_no}) AND `Type` IN ('MO', 'PL')")
            # next_mo.append(next_mo_query_result['data'])
            next_mo = next_mo_query_result['data']
        return next_mo

    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo` = '{supplyno}'"

    result = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=filter_string)
    if result['success'] and result['meta']['total'] == 1:  # 筛选到唯一的工单，则补充工序信息（v_orderwc）
        orderwc = await db_query(
            db_name=db_name, model_or_tablename="v_orderwc",
            filter_string=f"`SupplyNo` = '{supplyno}'"
        )
        result['data'][0]['orderwc'] = orderwc['data']
        vendorno = result['data'][0].get('vendorno')
        if result['data'][0].get('category') == 'MTO' and vendorno:
            so_query_result = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=f"`DemandNo`='{vendorno}' AND `Type`='SO'")
            so_data = so_query_result['data']
            if so_data:
                result['data'][0]['so'] = so_data
                
        if prev_mo:
            result['data'][0]['prev_mo'] = await get_prev_mo(supplyno)
        if next_mo:
            result['data'][0]['next_mo'] = await get_next_mo(supplyno)

    return result


@rt.get(
    "/v_supply_mo",
    tags=["报表 - 工单报表"],
    summary="获取工单报表",
    description="按工单开完工时间获取工单报表，默认开工时间为今日，默认完工时间为一周后。"
)
async def get_mo_by_time(
    db_name: str = common_params["db_name"],
    starttime: datetime = Query(None, description="工单开工时间"),
    endtime: datetime = Query(None, description="工单完工时间"),
    # x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")

    starttime = starttime or date.today()
    endtime = endtime or starttime + timedelta(days=7)
    filter_string = f"`DT_OrdStart` >= '{starttime}' AND `DT_OrdEnd` <= '{endtime}'"
    result = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=filter_string)
    return result



@rt.get(
    "/v_supply_complete",
    tags=["生产数据 - 报工"],
    summary="查询报工记录",
    description="查询报工记录"
)
async def query_workreport(
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    """
    查询报工记录
    db_name: str，数据库名称，多个数据库名称用逗号分隔
    """
    db_name = db_name.replace(" ", "")
    return await db_query(db_name=db_name, model_or_tablename="v_supply_complete")



@rt.get(
    "/v_orderwc",
    tags=["报表 - 工序报表"],
    summary="获取工序报表",
    description="按工序开完工时间获取工序报表，默认开工时间为今日，默认完工时间为一周后。"
)
async def get_orderwc(
    db_name: str = common_params["db_name"],
    starttime: datetime = Query(None, description="工序开工时间"),
    endtime: datetime = Query(None, description="工序完工时间"),
    # x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    starttime = starttime or date.today()
    endtime = endtime or starttime + timedelta(days=7)
    filter_string = f"`DT_Start` >= '{starttime}' AND `DT_End` <= '{endtime}'"
    return await db_query(db_name=db_name, model_or_tablename="v_orderwc", filter_string=filter_string)


@rt.get(
    "/v_orderwc/{supplyno}",
    tags=["报表 - 工序报表"],
    summary="获取工序报表",
    description="按编号（供应号）获取工序报表"
)
async def get_orderwc(
    db_name: str = common_params["db_name"],
    supplyno: str = Path(..., description="工单（供应）号"),
    # x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo` = '{supplyno}'"
    return await db_query(db_name=db_name, model_or_tablename="v_orderwc", filter_string=filter_string)



@rt.get(
    "/v_matdailyqtyreport",
    tags=["报表 - 库存动态"],
    summary="获取按日期分组的库存动态报表",
    description="获取按日期分组的库存动态报表"
)
async def get_matdailyqtyreport(
        db_name: str = common_params["db_name"],
        period: int | str = Query(default=30, description="查询时间范围（天）"),
        groupdates: Optional[str] = Query(default=None, description="分组日期，逗号分隔"),
        materialno: Optional[str] = Query(default=None, description="料号，多个料号用逗号分隔")
):
    """
    获取按日期分组的库存动态报表，用于指导采购决策。
    period: 查询时间范围（天）或截止日期字符串，默认30天。
    groupdates: 分组日期，逗号分隔，默认空。
    materialno: 料号，多个料号用逗号分隔，默认空。
    """
    start_date: datetime.date = datetime.now().date()

    try:
        period = int(period)
        end_date = start_date + timedelta(days=period)
    except ValueError:
        try:
            end_date = datetime.strptime(period, '%Y-%m-%d').date()
        except ValueError:
            return standard_response(status_code=status.HTTP_400_BAD_REQUEST, success=0, message="Invalid date format for period. Use YYYY-MM-DD.")

    db_name = db_name.replace(" ", "")
    request_result = []
    if groupdates and groupdates != 'None':
        dates = [_.strip() for _ in groupdates.split(',')]
    else:
        dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(period)]
    filter_string = f"`DateStr` >= '{start_date}' AND `DateStr` <= '{end_date}'"
    order_string = "`MaterialNo`, `DateStr`"
    if materialno:
        sql_matno = ','.join([f"'{matno.strip()}'" for matno in materialno.split(',')])
        filter_string += f" AND `MaterialNo` IN ({sql_matno})"
    query_result = await db_query(db_name=db_name, model_or_tablename="v_matdailyqtyreport", filter_string=filter_string, order_string=order_string)
    if data := query_result.get('data'):
        request_result.extend(data)

    if not request_result:
        return standard_response(status_code=status.HTTP_204_NO_CONTENT, message="No data available", meta={'total': 0}, data=request_result)

    # 转换为DataFrame并过滤
    df = pd.DataFrame(request_result)
    df = df.sort_values(by=['materialno', 'datestr'], ascending=[True, True])
    # df = df[df['type'] == 'F'].sort_values(by=['materialno', 'datestr'], ascending=[True, True])

    df['original_datestr'] = df['datestr']
    # 日期映射
    if dates:
        sorted_dates = sorted([datetime.strptime(d, '%Y-%m-%d').date() for d in dates])
        # 为每个原始日期找到对应的分组区间，并使用区间左端点作为要求交期
        def get_group_start_date(x):
            x_date = x
            # 遍历排序后的分组日期
            for i in range(len(sorted_dates)):
                # 对于最后一个分组，所有大于等于它的日期都属于这个分组
                if i == len(sorted_dates) - 1:
                    if x_date >= sorted_dates[i]:
                        return str(sorted_dates[i])
                # 对于其他分组，判断日期是否在当前分组和下一个分组之间
                else:
                    if sorted_dates[i] <= x_date < sorted_dates[i+1]:
                        return str(sorted_dates[i])
            # 如果日期小于第一个分组日期，返回第一个分组日期
            return str(sorted_dates[0])
        
        df['datestr'] = pd.to_datetime(df['datestr']).dt.date.apply(get_group_start_date)
    
    # 分组汇总
    group_fields = ['materialno', 'datestr']
    sum_fields = ['totaldemand', 'totalsupply', 'dailybalance']

    # 动态生成聚合字典
    agg_dict = {
        **{col: 'last' for col in df.columns if col not in group_fields + sum_fields + ['original_datestr']},
        **{f: 'sum' for f in sum_fields},
        # 'original_datestr': lambda x: ','.join(sorted(set(dt.strftime('%Y-%m-%d') for dt in x))),
        'original_datestr': lambda x: ','.join(sorted(set(str(dt) for dt in x))),
    }
    
    df_grouped = (df.groupby(group_fields).agg(agg_dict).reset_index()
                    .rename(columns={
                            "original_datestr": "期间",
                            "totaldemand": "期间合计需求",
                            "totalsupply": "期间合计供应",
                            "dailybalance": "期间盈余",
                            "cumulativebalance": "累计盈余",
                            "stockqty": "首期库存",
                            "datestr": "要求交期",
                            "name": "物料来源"
                            })
    )
    
    # 计算期初盈余和期末盈余
    result = []
    material_balances = {}
    
    for record in df_grouped.to_dict('records'):
        mat_no = record["materialno"]
        if mat_no not in material_balances:
            # 首个日期组
            opening_balance = record["首期库存"]
            closing_balance = opening_balance + record["期间合计需求"]
            record["期间要货数"] = abs(min(0, record["期间合计供应"] + record["期间合计需求"]))
        else:
            # 后续日期组
            opening_balance = material_balances[mat_no]
            closing_balance = opening_balance + record["期间合计需求"] + record["期间合计供应"]
            record["期间要货数"] = abs(min(max(0, opening_balance) + record["期间合计供应"] + record["期间合计需求"], 0))
        
        date_range = record["期间"].split(',')
        # 更新记录
        record.update({
            "期初盈余": opening_balance,
            "期末盈余": closing_balance,
            "期间": f"{date_range[0]},{date_range[-1]}",
        })
        material_balances[mat_no] = closing_balance
        result.append(record)
    
    return standard_response(status_code=status.HTTP_200_OK, meta={'total': len(result)}, data=result)


@rt.post(
    "/t_confirm",
    tags=["生产数据 - 报工"],
    summary="新增报工记录",
    description="新增报工记录"
)
async def create_workreport(
    data: List[AcceptConfirm | Dict],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    """
    新增报工记录
    db_name: str，数据库名称，多个数据库名称用逗号分隔
    """
    db_name = db_name.replace(" ", "")
    # await db_query(db_name=db_name, model_or_tablename="t_orderwc", filter_string=f"`SupplyNo`='{supplyno}' AND `ItemNo`='{itemno}'")
    return await db_bupsert(db_names=db_name, model_or_tablename="t_confirm", data_list=data)


@rt.delete(
    "/t_confirm/{supplyno}/{itemno}",
    tags=["生产数据 - 报工"],
    summary="删除报工记录",
    description="删除报工记录"
)
async def delete_workreport(
    db_name: str = common_params["db_name"],
    supplyno: str = Path(..., description="工单号"),
    itemno: str = Path(..., description="工序项目"),
    x_api_key: str = common_params["x_api_key"]
):
    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo`='{supplyno}'"
    if not itemno == "...":
        filter_string += f" AND `ItemNo`='{itemno}'"
    result = await db_delete(db_names=db_name, model_or_tablename="t_confirm", filter_string=filter_string)
    return result


@rt.patch(
    "/t_confirm",
    tags=["生产数据 - 报工"],
    summary="确认报工记录",
    description="确认报工记录"
)
async def confirm_workreport(
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
):
    """
    确认报工记录
    db_name: str，数据库名称，多个数据库名称用逗号分隔
    """
    db_name = db_name.replace(" ", "")
    return await call_dbprocdure(db_names=db_name, procedure_name="UpdateConfirmQtyToOrderWC")

