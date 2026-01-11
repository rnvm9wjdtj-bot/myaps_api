from datetime import date, datetime, timedelta
# from re import S
# from this import d
from typing import List#, Dict, Any, Literal
import inspect, functools, pandas as pd
import httpx

from fastapi import APIRouter, Query, Body, status#, Request, Path
# from tortoise import Tortoise

from config.settings import MYAPS_DB_SET, MYAPS_DBSET_LIST, MYAPS_MAIN_DB, THIS_BASE_URL
from globalobjects import globalconst as gc
from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom, TSupply, TDemand, TMold, TMatWcMold, TConfirm#,TortoiseBaseModel
from .schemas import (
    AcceptMaterial, AcceptWorkcenter, AcceptMatWc, AcceptMatVer, AcceptMatWcBom, AcceptSupply, AcceptDemand, AcceptMold, AcceptMatWcMold, AcceptConfirm,
    ConvertPl
    #DeleteSupply
    )
from .utils.common import (
    common_params, get_tortoise_connection,
    common_read_by_orm, common_write, common_delete_by_orm, common_read_by_sql, common_delete_by_sql, common_call_dbprocdure,
    standard_response)
from apps.data_opt.project_files import hap_conn


def _check_db_name(hap_wsid: str = None):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 获取函数签名
            sig = inspect.signature(func)
            
            # 查找db_name参数
            db_name_param = None
            db_name_index = None
            for i, (param_name, param) in enumerate(sig.parameters.items()):
                if param_name == 'db_name':
                    db_name_param = param
                    db_name_index = i
                    break
            
            # 获取db_name的值
            db_name = None
            
            if db_name_param is not None:
                if db_name_index is not None and db_name_index < len(args):
                    # db_name作为位置参数传递
                    db_name = args[db_name_index]
                elif 'db_name' in kwargs:
                    # db_name作为关键字参数传递
                    db_name = kwargs['db_name']
                else:
                    # 使用默认值
                    db_name = db_name_param.default
            
            # 如果没有db_name参数或db_name为None或空，调用 HAP API
            if db_name_param is None or db_name is None or db_name == "":
                # 获取原函数的data参数
                data_param = None
                data_index = None
                for i, (param_name, param) in enumerate(sig.parameters.items()):
                    if param_name == 'data':
                        data_param = param
                        data_index = i
                        break
                
                # 获取data的值
                data_value = None
                if data_param is not None:
                    if data_index is not None and data_index < len(args):
                        # data作为位置参数传递
                        data_value = args[data_index]
                    elif 'data' in kwargs:
                        # data作为关键字参数传递
                        data_value = kwargs['data']
                    else:
                        # 使用默认值
                        data_value = data_param.default
                
                # 处理pydantic对象列表到字典列表的转换
                processed_data = None
                if data_value is not None:
                    if hasattr(data_value, '__iter__') and not isinstance(data_value, (str, bytes)):
                        # 处理列表或可迭代对象
                        processed_data = []
                        for item in data_value:
                            processed_data.append(item._cached_raw_input_data)
                    else:
                        # 单个对象
                        if hasattr(data_value, 'dict'):
                            # pydantic v1 model
                            processed_data = data_value.dict()
                        elif hasattr(data_value, 'model_dump'):
                            # pydantic v2 model
                            processed_data = data_value.model_dump()
                        else:
                            # 普通对象
                            processed_data = data_value
                
                try:
                    if hap_conn is not None:

                        # 调用 add_rows()方法，传入原函数的data
                        result = hap_conn.add_rows(
                            worksheet_id=hap_wsid, 
                            rows=processed_data,
                            trigger_workflow=True
                        )
                        return standard_response(
                            status_code=status.HTTP_200_OK,
                            success=1,
                            message="call hap.add_rows success",
                            data=result
                        )
                    else:
                        return standard_response(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            success=0,
                            message="no db_name parameter or db_name is empty, trigger hap call"
                        )
                except Exception as e:
                    return standard_response(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        success=0,
                        message=f"failed to call hap.add_rows: {str(e)}"
                    )
            
            # db_name有效，正常执行原函数
            return await func(*args, **kwargs)
        return wrapper
    return decorator


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
    
    
# @rt.get(
#     "/t_material",
#     tags=["主数据 - 物料"],
#     summary="获取物料信息",
#     description="获取物料信息"
# )
# async def get_material(
#     db_name: str = common_params["db_name"],
#     page_size: int = common_params["page_size"],
#     page_index: int = common_params["page_index"]
# ):
#     return await common_read_by_orm(db_name=db_name, mdl=TMaterial, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="新增或修改物料",
    description="根据🗝️【料号】新增或修改物料"
    )
@_check_db_name(hap_wsid="t_material")
async def post_material(
    data: List[AcceptMaterial] = Body(..., description="新增或修改的物料数据"),
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMaterial, data=data)


# @rt.get(
#     "/t_workcenter",
#     tags=["主数据 - 工作中心"],
#     summary="获取工作中心信息",
#     description="获取工作中心信息"
# )
# async def get_workcenter(
#     db_name: str = common_params["db_name"],
#     page_size: int = common_params["page_size"],
#     page_index: int = common_params["page_index"]
# ):
#     return await common_read_by_orm(db_name=db_name, mdl=TWorkcenter, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="新增或修改工作中心",
    description="根据🗝️【工作中心编号】新增或修改工作中心"
    )
@_check_db_name(hap_wsid="t_workcenter")
async def post_workcenter(
    data: List[AcceptWorkcenter],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TWorkcenter, data=data)

# @rt.get(
#     "/t_mat_wc",
#     tags=["主数据 - 工序"],
#     summary="获取工序信息",
#     description="获取工序信息"
# )
# async def get_mat_wc(
#     db_name: str = common_params["db_name"],
#     page_size: int = common_params["page_size"],
#     page_index: int = common_params["page_index"]
# ):
#     return await common_read_by_orm(db_name=db_name, mdl=TMatWc, page_size=page_size, page_index=page_index)
    
@rt.post(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="新增或修改工序",
    description="根据🗝️【料号+产线版本号+工序项目】形成的联合索引新增或修改工序记录"
    )
@_check_db_name(hap_wsid="t_mat_wc")
async def post_mat_wc(
    data: List[AcceptMatWc],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMatWc, data=data)

# @rt.get(
#     "/t_mat_ver",
#     tags=["主数据 - 产线版本"],
#     summary="获取产线版本信息",
#     description="获取产线版本信息"
# )
# async def get_mat_ver(
#     db_name: str = common_params["db_name"],
#     page_size: int = common_params["page_size"],
#     page_index: int = common_params["page_index"]
# ):
#     return await common_read_by_orm(db_name=db_name, mdl=TMatVer, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_mat_ver",
    tags=["主数据 - 产线版本"],
    summary="新增或修改产线版本",
    description="根据🗝️【料号+产线版本号】形成的联合索引新增或修改产线版本记录"
    )
@_check_db_name(hap_wsid="t_mat_ver")
async def post_mat_ver(
    data: List[AcceptMatVer],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMatVer, data=data)

# @rt.get(
#     "/t_mat_wc_bom",
#     tags=["主数据 - BOM"],
#     summary="获取BOM信息",
#     description="获取BOM信息"
# )
# async def get_mat_wc_bom(
#     db_name: str = common_params["db_name"],
#     page_size: int = common_params["page_size"],
#     page_index: int = common_params["page_index"]
# ):
#     return await common_read_by_orm(db_name=db_name, mdl=TMatWcBom, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_mat_wc_bom",
    tags=["主数据 - BOM"],
    summary="新增或修改BOM",
    description="根据🗝️【产品料号+子件料号+产线版本号+工序项目】形成的联合索引新增或修改BOM记录"
    )
@_check_db_name(hap_wsid="t_mat_wc_bom")
async def post_mat_wc_bom(
    data: List[AcceptMatWcBom],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMatWcBom, data=data)


@rt.post(
    "/t_mold",
    tags=["主数据 - 模具"],
    summary="新增或修改模具",
    description="根据🗝️【模具编号】新增或修改模具"
    )
@_check_db_name(hap_wsid="t_mold")
async def post_mold(
    data: List[AcceptMold],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMold, data=data)


@rt.post(
    "/t_mat_wc_mold",
    tags=["主数据 - 机台模具"],
    summary="新增或修改机台模具",
    description="根据🗝️【料号+工作中心+工序项目+模具编号】形成的联合索引新增或修改机台模具记录"
    )
@_check_db_name(hap_wsid="t_mat_wc_mold")
async def post_mat_wc_mold(
    data: List[AcceptMatWcMold],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TMatWcMold, data=data)


########################################################################
# 生产数据接口
########################################################################
@rt.get(
    "/t_supply",
    tags=["生产数据 - 供应"],
    summary="获取供应记录",
    description="获取供应记录"
)
async def get_supply(
    db_name: str = common_params["db_name"],
    page_size: int = common_params["page_size"],
    page_index: int = common_params["page_index"],
    # x_api_key: str = common_params["x_api_key"]
):
    return await common_read_by_orm(db_name=db_name, mdl=TSupply, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_supply",
    tags=["生产数据 - 供应"],
    summary="新增或修改供应记录（供应来源包含：生产生产计划PL、生产工单MO、库存ST、采购订单PO）",
    description="根据🗝️【料号+供应号】新增或修改供应记录"
    )
async def post_supply(
    data: List[AcceptSupply],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TSupply, data=data)

@rt.patch(
    "/t_supply/pl",
    tags=["生产数据 - 供应"],
    summary="将生产计划PL转为MO",
    description="根据供应号更新PL记录，与POST方法的区别是：POST方法以【料号+供应号】为联合索引，且不会修改供应号；而PATCH方法以供应号为索引，且允许修改供应号"
    )
async def convert_pl_to_mo_by_dbprocdure(
    data: List[ConvertPl] = Body(..., description="更新PL记录的列表"),
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    # 调用存储过程SupplyConvertMOByE2A，将PL转为MO
    params_list = [[item.plno, item.mono, item.status, item.memo, item.is_execute_updates] for item in data]
    return await common_call_dbprocdure(db_name=db_name, procedure_name="SupplyConvertMOByE2A", params_list=params_list)


@rt.delete(
    "/t_supply",
    tags=["生产数据 - 供应"],
    summary="删除供应记录",
    description="根据供应类型、料号、供应号删除供应记录。如果del_relation为True，还会删除关联的工序记录（仅对PL、MO类型有效）"
    )
async def delete_supply(
    db_name: str = common_params["db_name"],
    type: str = common_params["supply_type"],
    materialno: str | None = Query(None, description="料号"),
    supplyno: str | None = Query(None, description="供应号"),
    del_relation: bool | None = Query(True, description="是否删除关联的工序记录（仅对PL、MO类型有效）"),
    x_api_key: str = common_params["x_api_key"]
    ):
    # 使用一个更具描述性的变量名替换内置函数名
    supply_type_param = type
    supply_type_param = supply_type_param.upper()
    all_supply_type = list(gc.SUPPLY_TYPE.keys())
    
    if not supply_type_param:
        return standard_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            success=0,
            message="Required parameter 'type' not found.")
    if supply_type_param not in all_supply_type:
        return standard_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            success=0,
            message=f"Invalid input type. Expected list of DeleteSupply or dict with 'bytype' in {all_supply_type}.")

    filter_conditions = [f"Type='{supply_type_param}'", ]
    if materialno:
        filter_conditions.append(f"MaterialNo='{materialno}'")
    if supplyno:
        filter_conditions.append(f"SupplyNo='{supplyno}'")
    filter_string = " AND ".join(filter_conditions)
    result = await common_delete_by_sql(db_name=db_name, table_name="t_supply", filter_string=filter_string)
    if del_relation and supply_type_param in ['PL', 'MO'] and supplyno and result["success"]: # 删除关联的工序记录
        await common_delete_by_sql(db_name=db_name, table_name="t_orderwc", filter_string=f"SupplyNo='{supplyno}'")
    return result


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
    return await common_read_by_orm(db_name=db_name, mdl=TDemand, page_size=page_size, page_index=page_index)

@rt.post(
    "/t_demand",
    tags=["生产数据 - 需求"],
    summary="新增或修改需求记录（需求来源包含：销售订单SO、计划需求DM、工单预留RS、预测FC、安全库存SS）",
    description="根据🗝️【料号+需求号+项目号】新增或修改需求记录"
    )
async def post_demand(
    data: List[AcceptDemand],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    return await common_write(db_name=db_name, mdl=TDemand, data=data)

########################################################################
# 报表接口
########################################################################
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
    # x_api_key: str = common_params["x_api_key"]
):
    if supplyno:
        filter_string = f"SupplyNo = '{supplyno}'"
    else:
        starttime = starttime or date.today()
        endtime = endtime or starttime + timedelta(days=7)
        filter_string = f"DT_OrdStart >= '{starttime}' AND DT_OrdEnd <= '{endtime}'"
    result = await common_read_by_sql(db_name=db_name, table_name="v_supply_mo", filter_string=filter_string)
    if result['success'] and result['meta']['total'] == 1:  # 筛选到唯一的工单，则补充工序信息（v_orderwc）
        orderwc = await common_read_by_sql(db_name=db_name, table_name="v_orderwc", filter_string=f"SupplyNo = '{supplyno}'", order_string="SortNo ASC")
        result['data'][0]['orderwc'] = orderwc['data']
    return result

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
    # x_api_key: str = common_params["x_api_key"]
):
    if supplyno:
        filter_string = f"SupplyNo = '{supplyno}'"
    else:
        starttime = starttime or date.today()
        endtime = endtime or starttime + timedelta(days=7)
        filter_string = f"DT_Start >= '{starttime}' AND DT_End <= '{endtime}'"
    return await common_read_by_sql(db_name=db_name, table_name="v_orderwc", filter_string=filter_string)


@rt.get(
    "/v_matdailyqtyreport",
    tags=["报表 - 库存动态"],
    summary="获取按日期分组的库存动态报表",
    description="获取按日期分组的库存动态报表"
)
async def get_matdailyqtyreport(
        db_name: str = common_params["db_name"],
        period: int = Query(default=30, description="查询时间范围（天）"),
        groupdates: str = Query(default=None, description="分组日期，逗号分隔"),
        materialno: str = Query(default=None, description="料号，多个料号用逗号分隔")
    ):
    start_date: datetime.date = datetime.now().date()
    end_date = start_date + timedelta(days=period)
    request_result = []
    dates = groupdates.split(',') if groupdates else None

    filter_string = f"DateStr >= '{start_date}' AND DateStr <= '{end_date}'"
    order_string = "MaterialNo, DateStr"
    if materialno:
        filter_string += f" AND MaterialNo IN ({materialno})"
    query_result = await common_read_by_sql(db_name=db_name, table_name="v_matdailyqtyreport", filter_string=filter_string, order_string=order_string)
    if data := query_result.get('data'):
        request_result.extend(data)

    if not request_result:
        return standard_response(status_code=status.HTTP_204_NO_CONTENT, message="No data available", meta={'total': 0}, data=request_result)
    
    # if not groupdates:
    #     return standard_response(meta={'total': len(request_result)}, data=request_result)
    # 转换为DataFrame并过滤
    df = pd.DataFrame(request_result)
    df = df[df['type'] == 'F'].sort_values(by=['materialno', 'datestr'], ascending=[True, True])

    df['original_datestr'] = df['datestr']
    # 日期映射
    if dates:
        sorted_dates = sorted([datetime.strptime(d, '%Y-%m-%d').date() for d in dates])
        df['datestr'] = pd.to_datetime(df['datestr']).dt.date.apply(
            lambda x: next((d for d in sorted_dates if d >= x), sorted_dates[-1])
        ).astype(str)
    
    # 分组汇总
    group_fields = ['materialno', 'datestr']
    sum_fields = ['totaldemand', 'totalsupply', 'dailybalance']

    # 动态生成聚合字典
    agg_dict = {
        **{col: 'last' for col in df.columns if col not in group_fields + sum_fields + ['original_datestr']},
        **{f: 'sum' for f in sum_fields},
        'original_datestr': lambda x: ','.join(sorted(set(dt.strftime('%Y-%m-%d') for dt in x))),
    }
    
    df_grouped = df.groupby(group_fields).agg(agg_dict).reset_index()
    
    # 计算期初盈余和期末盈余
    result = []
    material_balances = {}
    
    for record in df_grouped.to_dict('records'):
        mat_no = record['materialno']
        if mat_no not in material_balances:
            # 首个日期组
            opening_balance = record['stockqty']
            closing_balance = opening_balance + record['totaldemand']
            record['本期要货数'] = abs(min(0, record['totalsupply'] + record['totaldemand']))
        else:
            # 后续日期组
            opening_balance = material_balances[mat_no]
            closing_balance = opening_balance + record['totaldemand'] + record['totalsupply']
            record['本期要货数'] = abs(min(max(0, opening_balance) + record['totalsupply'] + record['totaldemand'], 0))
        
        # 更新记录
        record.update({
            '期初盈余': opening_balance,
            '期末盈余': closing_balance
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
    data: List[AcceptConfirm],
    db_name: str = common_params["db_name"],
    x_api_key: str = common_params["x_api_key"]
    ):
    # 使用异步上下文管理器自动管理连接
    async with get_tortoise_connection(db_name) as db:
        for d in data:
            if not hasattr(d, "itemno") or d.itemno in gc.NONE_AND_EMPTY:
                workcenter = d.workcenter if hasattr(d, "workcenter") else None
                assert workcenter not in gc.NONE_AND_EMPTY, "workcenter cannot be empty when itemno is empty"
                
                query = f"SELECT ItemNo FROM t_orderwc WHERE `SupplyNo` = '{d.supplyno}' AND `WorkCenter` = '{workcenter}'"
                record_count, result = await db.execute_query(query)
                if record_count == 1:
                    itemno = result[0]['ItemNo']
                    d.itemno = itemno
            d.workcenter = None
    
    return await common_write(db_name=db_name, mdl=TConfirm, data=data)
