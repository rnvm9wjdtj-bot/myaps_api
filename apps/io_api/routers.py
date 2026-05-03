from datetime import date, datetime, timedelta
# from re import S
# from this import d
from typing import List, Dict, Optional, Literal#, Any
import inspect, functools, pandas as pd, asyncio
# import httpx
from fastapi import APIRouter, Path, Query, Body, Header, status, Request, HTTPException, Depends
# from tortoise import Tortoise

from core.settings import MYAPS_DB_SET, MYAPS_DBSET_LIST, MYAPS_MAIN_DB, THIS_BASE_URL
from globalobjects import globalconst as gc, logger as log_config, ProjectDefaultValues as pdv
# from .models import TMaterial, TWorkcenter, TMatWc, TMatVer, TMatWcBom, TSupply, TDemand, TMold, TMatWcMold, TConfirm#,TortoiseBaseModel
from .schemas import (
    AcceptMaterial, AcceptWorkcenter, AcceptMatWc, AcceptMatVer, AcceptMatWcBom, AcceptSupply, AcceptDemand, AcceptMold, AcceptMatWcMold, AcceptConfirm,
    ModifySupply, ModifyDemand
    #DeleteSupply
)

from .utils.common import standard_response, drop_matched_data
from .utils.db_operation import db_exec_sql, db_managers, db_query, db_supsert, db_bupsert, db_delete, call_dbprocdure, db_update_by_index
# from project_files import hap_conn
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components import ApsPayloadSponsor


logger = log_config.get_logger(__name__)

# 健康检查状态缓存
_db_health_cache = {}
_cache_timestamp = 0
CACHE_DURATION = 60  # 缓存60秒


########################################################################
def get_client_ip(request: Request):
    """获取客户端IP地址"""
    client_ip = request.client.host
    return client_ip


def only_localhost():
    """仅允许本地主机访问的依赖项"""
    async def dependency(request: Request):
        client_ip = get_client_ip(request)
        if client_ip not in ["127.0.0.1", "localhost", "::1"]:
            raise HTTPException(status_code=403, detail="Access denied: Only localhost access allowed")
    return dependency


rt = APIRouter()
########################################################################
########################################################################
# 主数据接口
########################################################################

@rt.get("/meta", include_in_schema=False, dependencies=[Depends(only_localhost())])
async def get_meta():
    """
    获取元数据信息，包括数据库状态等
    """
    try:
        import asyncio
        import time
        from globalobjects.db_manager import DbManager
        
        global _db_health_cache, _cache_timestamp
        current_time = time.time()
        
        # 检查缓存是否有效
        if current_time - _cache_timestamp < CACHE_DURATION and _db_health_cache:
            logger.debug("使用缓存的健康检查结果")
            return standard_response(
                success=1,
                message="获取元数据成功（缓存）",
                meta=_db_health_cache,
            )
        
        # 检查每个账套的可访问性（带超时处理）
        async def check_single_db(db):
            """检查单个数据库状态"""
            try:
                start_time = time.time()
                db_manager = DbManager(db)
                # 调整单个检查超时为3秒
                is_healthy = await asyncio.wait_for(
                    db_manager.check_connection_health(timeout=3), 
                    timeout=3
                )
                response_time = time.time() - start_time
                status = f"{'🟢' if is_healthy else '🔴'}{db}"
                if response_time > 1.0:
                    logger.warning(f"数据库检查响应缓慢: {db} - {response_time:.3f}秒")
                return status
            except asyncio.TimeoutError:
                logger.warning(f"数据库检查超时: {db}")
                return f"🔴{db} (超时)"
            except Exception as e:
                logger.error(f"数据库检查失败: {db} - {str(e)}")
                return f"🔴{db} (错误)"
        
        # 分批检查，每批最多2个账套，减少并发压力
        batch_size = 2
        db_status = []
        
        for i in range(0, len(MYAPS_DBSET_LIST), batch_size):
            batch_dbs = MYAPS_DBSET_LIST[i:i+batch_size]
            try:
                batch_results = await asyncio.gather(
                    *(check_single_db(db) for db in batch_dbs),
                    return_exceptions=True
                )
                # 处理异常结果
                for j, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        db = batch_dbs[j]
                        logger.error(f"批量检查异常: {db} - {str(result)}")
                        db_status.append(f"🔴{db} (异常)")
                    else:
                        db_status.append(result)
            except Exception as e:
                logger.error(f"批量检查失败: {str(e)}")
                # 为当前批次的所有数据库标记为错误
                for db in batch_dbs:
                    db_status.append(f"🔴{db} (批量检查失败)")
        
        # 更新缓存
        _db_health_cache = {
            "db_set": MYAPS_DBSET_LIST,
            "dbs_str": MYAPS_DB_SET,
            "main_db": MYAPS_MAIN_DB,
            "db_status": db_status,
            "timestamp": current_time,
            "cache_duration": CACHE_DURATION
        }
        _cache_timestamp = current_time
        
        logger.debug("更新健康检查缓存")
        return standard_response(
            success=1,
            message="获取元数据成功",
            meta=_db_health_cache,
        )
        
    except Exception as e:
            logger.error(f"获取元数据失败: {str(e)}")
            # 即使出错也返回基本信息，确保接口不会崩溃
            return standard_response(
                success=0,
                message=f"获取元数据失败: {str(e)}",
                meta={
                    "db_set": MYAPS_DBSET_LIST,
                    "dbs_str": MYAPS_DB_SET,
                    "main_db": MYAPS_MAIN_DB,
                    "db_status": [f"🔴{db} (接口错误)" for db in MYAPS_DBSET_LIST],
                    "timestamp": time.time(),
                    "error": str(e)
                }
            )
    

@rt.get(
    '/t_material/page',
    tags=["主数据 - 物料"],
    summary="获取物料分页数据",
    description="根据分页参数获取物料分页数据",
    include_in_schema=False,
    dependencies=[Depends(only_localhost())]
)
async def get_material_page(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    page_index: int = Query(0, description="页码"),
    page_size: int = Query(1000, description="每页数量"),
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_query(db_name=db_name, model_or_tablename="t_material", page_index=page_index, page_size=page_size)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取物料分页数据失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.get(
    "/t_material/{materialnos}",
    tags=["主数据 - 物料"],
    summary="根据料号获取物料信息",
    description="根据料号获取物料信息",
)
async def get_material(
    materialnos: str = Path(..., description="料号，多个用逗号隔开"),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套")
):
    db_name = db_name.replace(" ", "")
    try:
        if materialnos != "...":
            materialnos = ",".join([f"'{_}'" for _ in materialnos.split(",")])
            filter_string = f"`MaterialNo` IN ({materialnos})"
        else:
            filter_string = ""
        result = await db_query(db_name=db_name, model_or_tablename="t_material", filter_string=filter_string)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"根据料号获取物料信息失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )



@rt.post(
    "/t_material",
    tags=["主数据 - 物料"],
    summary="新增或修改物料",
    description="根据🗝️【料号】新增或修改物料"
)
async def post_material(
    data: List[AcceptMaterial] = Body(..., description="新增或修改的物料数据"),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
    ):
    db_name = db_name.replace(" ", "")

    if pdv.auto_matver:
        matver_data = [{
            "materialno": _.materialno,
            "matver": pdv.MATVER,
            "lotfrom": pdv.MATVER_LOTFROM,
            "lotto": pdv.MATVER_LOTTO,
            "priority": pdv.MATVER_PRIORITY,
        } for _ in data if _.type == "E"]
        
        async def run_matver_task():
            try:
                await post_mat_ver(data=matver_data, db_name=db_name, x_api_key=x_api_key)
            except Exception as e:
                logger.error(f"Error in post_mat_ver background task: {e}")
        
        asyncio.create_task(run_matver_task())

    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_material", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改物料失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        ) 



@rt.post(
    "/t_workcenter",
    tags=["主数据 - 工作中心"],
    summary="新增或修改工作中心",
    description="根据🗝️【工作中心编号】新增或修改工作中心"
)
async def post_workcenter(
    data: List[AcceptWorkcenter] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
    ):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_workcenter", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改工作中心失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )



@rt.post(
    "/t_mat_wc",
    tags=["主数据 - 工序"],
    summary="新增或修改工序",
    description="根据🗝️【料号+产线版本号+工序项目】形成的联合索引新增或修改工序记录"
)
async def post_mat_wc(
    data: List[AcceptMatWc] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    drop: Literal["all", "matched"] = Query(None, description="丢弃旧数据的方式"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_table = "t_mat_wc"
    db_name = db_name.replace(" ", "")
    try:
        if drop == "all":
            await db_delete(db_names=db_name, model_or_tablename=db_table)
        elif drop == "matched":
            await drop_matched_data(
                data=data,
                db_names=db_name,
                table_name=db_table,
                match_on=("materialno", "matver"),
                db_fields=("MaterialNo", "MatVer")
            )
        result = await db_bupsert(db_names=db_name, model_or_tablename=db_table, data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改工序失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.post(
    "/t_mat_ver",
    tags=["主数据 - 产线版本"],
    summary="新增或修改产线版本",
    description="根据🗝️【料号+产线版本号】形成的联合索引新增或修改产线版本记录"
)
async def post_mat_ver(
    data: List[AcceptMatVer] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_mat_ver", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改产线版本失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.post(
    "/t_mat_wc_bom",
    tags=["主数据 - BOM"],
    summary="新增或修改BOM",
    description="根据🗝️【产品料号+子件料号+产线版本号+工序项目】形成的联合索引新增或修改BOM记录"
)
async def post_mat_wc_bom(
    data: List[AcceptMatWcBom] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    drop: Literal["all", "matched"] = Query(None, description="丢弃旧数据的方式"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_table = "t_mat_wc_bom"
    db_name = db_name.replace(" ", "")
    try:
        if drop == "all":
            await db_delete(db_names=db_name, model_or_tablename=db_table)
        elif drop == "matched":
            await drop_matched_data(
                data=data,
                db_names=db_name,
                table_name=db_table,
                match_on=("productno", "matver"),
                db_fields=("ProductNo", "MatVer"),
            )
        result = await db_bupsert(db_names=db_name, model_or_tablename=db_table, data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改BOM失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.post(
    "/t_mold",
    tags=["主数据 - 模具"],
    summary="新增或修改模具",
    description="根据🗝️【模具编号】新增或修改模具"
)
async def post_mold(
    data: List[AcceptMold] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_mold", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改模具失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.post(
    "/t_mat_wc_mold",
    tags=["主数据 - 机台模具"],
    summary="新增或修改机台模具",
    description="根据🗝️【料号+工作中心+工序项目+模具编号】形成的联合索引新增或修改机台模具记录"
)
async def post_mat_wc_mold(
    data: List[AcceptMatWcMold] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    drop: Literal["all", "matched"] = Query(None, description="丢弃旧数据的方式"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    db_table = "t_mat_wc_mold"
    try:
        if drop == "all":
            await db_delete(db_names=db_name, model_or_tablename=db_table)

        elif drop == "matched":
            await drop_matched_data(
                data=data,
                db_names=db_name,
                table_name=db_table,
                match_on=("materialno", "itemno")
            ) 
        result = await db_bupsert(db_names=db_name, model_or_tablename=db_table, data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改机台模具失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


########################################################################
# 生产数据接口
########################################################################
# @rt.get(
#     "/v_supply/{supplyno}",
#     tags=["生产数据 - 供应"],
#     summary="获取供应记录",
#     description="获取供应记录"
# )
# async def get_supply(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     supplyno: str = Path(..., description="供应号"),
# ):
#     filter_string = f"`SupplyNo`='{supplyno}'"

#     supply_query_result = await db_query(db_name=db_name, model_or_tablename="v_supply", filter_string=filter_string)
#     supply_data = supply_query_result.data

#     return standard_response(data=supply_data)


@rt.post("/t_supply",
    tags=["生产数据 - 供应"],
    summary="新增或修改供应记录（供应来源包含：生产生产计划PL、生产工单MO、库存ST、采购订单PO）",
    description="根据🗝️【料号+供应号】新增或修改供应记录"
)
async def post_supply(
    data: List[AcceptSupply] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_supply", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改供应记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


# @rt.patch(
#     "/t_supply/{supplyno}/{materialno}",
#     tags=["生产数据 - 供应"],
#     summary="修改供应记录",
#     description="根据供应号、料号修改供应记录",
#     include_in_schema=False,
#     dependencies=[Depends(only_localhost())]
# )
# async def patch_supply_by_materialno(
#     supplyno: str = Path(..., description="要修改的供应记录的供应号"),
#     materialno: str = Path(..., description="料号"),
#     data: ModifySupply = Body(..., description="修改为这些信息"),
#     if_not_exist: Literal["skip", "insert"] = Query("skip", description="如果不存在如何处理"),
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     x_api_key: str = Header(None, description="API密钥")
# ):
#     db_name = db_name.replace(" ", "")
#     if isinstance(data, ModifySupply):
#         data = data.model_dump(exclude_unset=True)
#         # data = data.model_dump()
#     if "supplyno" in data:
#         data.pop("supplyno")    # 从data中移除supplyno，防止意外修改 供应号
#     index_dict = {"SupplyNo": supplyno}
#     if not materialno == "...":
#         index_dict["MaterialNo"] = materialno
#     return await db_update_by_index(
#         db_names=db_name,
#         model_or_tablename="t_supply",
#         index_dict=index_dict,
#         new_values_dict=data,
#         not_found_behavior=if_not_exist
#     )


# @rt.patch(
#     "/t_supply/{supplyno}",
#     tags=["生产数据 - 供应"],
#     summary="将 PL 转为 MO",
#     description="根据供应号更新 PL 记录 ，转化时允许修改供应号",
#     include_in_schema=False,
#     dependencies=[Depends(only_localhost())]
# )
# async def patch_supply(
#     supplyno: str = Path(..., description="要修改的供应记录的供应号"),
#     data: ModifySupply = Body(..., description="修改为这些信息"),
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     x_api_key: str = Header(None, description="API密钥")
# ):
#     db_name = db_name.replace(" ", "")
#     query_result = await db_query(db_name=db_name, model_or_tablename="t_supply", filter_string=f"`SupplyNo`='{supplyno}'")
#
#     query_data = query_result.data
#     if not query_data[0]["type"] == "PL":
#         return standard_response(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             success=0,
#             message=f"Supply {supplyno} is not a PL.")

#     if isinstance(data, ModifySupply):
#         # data = data.model_dump(exclude_unset=True, exclude_none=True)
#         data = data.model_dump(exclude_none=True)
#     data['materialno'] = query_data[0]['materialno']
#     # 如果未指定供应号，则延用
#     if not data.get('supplyno'):
#         data['supplyno'] = supplyno
#     # 调用存储过程SupplyConvertMOByE2A，将PL转为MO
#     params_list = [[supplyno, data['supplyno'], data['status'], data['apiex_id'], data['apiex_entryid'], data['memo']]]
#     result = await call_dbprocdure(db_names=db_name, procedure_name="SupplyConvertMOByE2A", params_list=params_list)
#     return result
    

@rt.put("/t_supply/type/{type_}",
    tags=["生产数据 - 供应"],
    summary="按类型替换供应记录",
    description="根据供应类型删除所有该类型的供应记录，然后新增这些供应记录。可用于库存、PO等单据刷新"
)
async def replace_supply(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    type_: str = Path(..., enum=['PL', 'MO', 'PR', 'PO', 'ST'], description="供应类型"),
    data: List[AcceptSupply] = Body(..., description="替换为这些供应记录"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    wrong_type_count = 0
    for item in data:
        if item.type != type_:
            wrong_type_count += 1
    if wrong_type_count > 0:
        return standard_response(
            status_code=status.HTTP_400_BAD_REQUEST,
            success=0,
            message=f"Supply type {type_} in data does not match.")
            
    db_name = db_name.replace(" ", "")
    try:
        delete_result = await db_delete(db_names=db_name, model_or_tablename="t_supply", filter_string=f"`Type`='{type_}'")
        if data:
            create_result = await db_bupsert(db_names=db_name, model_or_tablename="t_supply", data_list=data)
            return standard_response(
                status_code=200,
                success=create_result.success,
                message=create_result.message,
                data=create_result.data if return_data else None,
                meta=create_result.meta
            )
        else:
            return standard_response(
                status_code=200,
                success=delete_result.success,
                message=delete_result.message,
                data=delete_result.data if return_data else None,
                meta=delete_result.meta
            )
    except Exception as e:
        logger.error(f"按类型替换供应记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=None,
            meta={}
        )


@rt.delete(
    "/t_supply/{supplyno}",
    tags=["生产数据 - 供应"],
    summary="删除供应记录",
    description="根据供应号删除对应记录。也可用于完结工单。"
)
async def delete_supply(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    supplyno: str = Path(..., description="要删除的供应记录的供应号"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    try:
        result = await call_dbprocdure(db_names=db_name, procedure_name="SupplyDeleteAll", params_list=[[supplyno]])
        return standard_response(
            status_code=200,
            success=result.success,
            message="success",
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"删除供应记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )
    


# 需求接口
# @rt.get(
#     "/v_demand/page",
#     tags=["生产数据 - 需求"],
#     summary="获取需求报表",
#     description="根据需求类型查询需求记录",
#     include_in_schema=False,
#     dependencies=[Depends(only_localhost())]
# )
# async def get_demand_page(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     start_time: str = Query(None, description="需求开始时间"),
#     end_time: str = Query(None, description="需求截止时间"),
#     page_size: int = Query(1000, description="每页数量"),
#     page_index: int = Query(0, description="页码"),
# ):
#     db_name = db_name.replace(" ", "")
#     filter = []
#     if start_time:
#         filter.append(f"`Req_Date` >= '{start_time}'")
#     if end_time:
#         filter.append(f"`Req_Date` <= '{end_time}'")
#     filter_string = " AND ".join(filter)
#     return await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=filter_string, page_size=page_size, page_index=page_index)


# @rt.get(
#     "/v_demand/{demandno}",
#     tags=["生产数据 - 需求"],
#     summary="根据需求号获取物料需求详情",
#     description="根据 APS pegging 算法，需求号与供应号一致，所以该接口也即是：根据工单的 supplyno 获取原料需求"
# )
# async def get_demand(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     demandno: str = Path(..., description="需求号"),
#     # type_: str = Path(..., enum=["DM", "RS"], description="需求类型"),
# ):
#     query_result_demand = await db_query(db_name=db_name, model_or_tablename="v_demand", filter_string=f"`DemandNo`='{demandno}'")
#     if query_result_demand.success == 0:
#         return query_result_demand
#     query_result_supply = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=f"`SupplyNo`='{demandno}'")
#     if query_result_supply.success == 0:
#         return query_result_demand
#     if query_result_supply.data:
#         # 合并需求和供应数据
#         query_result_demand.meta["mo"] = query_result_supply.data[0]
#     return query_result_demand


@rt.post(
    "/t_demand",
    tags=["生产数据 - 需求"],
    summary="新增或修改需求记录（需求来源包含：销售订单SO、计划需求DM、工单预留RS、预测FC、安全库存SS）",
    description="根据🗝️【料号+需求号+项目号】新增或修改需求记录"
)
async def post_demand(
    data: List[AcceptDemand] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_demand", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增或修改需求记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


# @rt.patch(
#     "/t_demand/{demandno}/{materialno}/{itemno}",
#     tags=["生产数据 - 需求"],
#     summary="修改需求记录",
#     description="根据需求号修改记录"
# )
# async def patch_demand(
#     demandno: str = Path(..., description="需要修改的需求记录的需求号"),
#     materialno: str = Path(..., description="料号"),
#     itemno: str = Path(..., description="项目号"),
#     data: ModifyDemand = Body(..., description="修改为这些信息"),
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     if_not_exist: Literal["skip", "insert"] = Query("skip", description="如果不存在如何处理"),
#     x_api_key: str = Header(None, description="API密钥")
# ):
#     db_name = db_name.replace(" ", "")
#     index_dict = {"DemandNo": demandno}
#     if not materialno == "...":
#         index_dict["MaterialNo"] = materialno
#     if not itemno == "...":
#         index_dict["ItemNo"] = itemno

#     # new_values_dict = data.model_dump(exclude_unset=True, exclude_none=True)
#     new_values_dict = data.model_dump(exclude_none=True)
#     # new_values_dict['apiex_sn'] = demandno    # 已在MOA2E存储过程修改
#     response = await db_update_by_index(
#         db_names=db_name,
#         model_or_tablename="t_demand",
#         index_dict=index_dict,
#         new_values_dict=new_values_dict,
#         not_found_behavior=if_not_exist,
#     )

#     return response
########################################################################
# 报表接口
########################################################################

@rt.get(
    "/v_supply_mo/page",
    tags=["报表 - 工单报表"],
    summary="获取工单报表",
    description="按工单开完工时间获取工单报表",
    include_in_schema=False,
    dependencies=[Depends(only_localhost())]
)
async def get_mo_page(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    start_time: datetime = Query(None, description="工单开工时间"),
    end_time: datetime = Query(None, description="工单完工时间"),
    page_size: int = Query(1000, description="每页数量"),
    page_index: int = Query(0, description="页码"),
    # x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")

    filter = []
    if start_time:
        filter.append(f"`DT_OrdStart` >= '{start_time}'")
    if end_time:
        filter.append(f"`DT_OrdEnd` <= '{end_time}'")
    filter_string = " AND ".join(filter)
    try:
        result = await db_query(db_name=db_name, model_or_tablename="v_supply_mo", filter_string=filter_string, page_size=page_size, page_index=page_index)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取工单报表失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.get(
    "/v_supply_mo/{supplyno}",
    tags=["报表 - 工单报表"],
    summary="获取工单报表",
    description="按供应号获取工单信息。"
)
async def get_mo_by_supplyno(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    supplyno: str = Path(..., description="工单（供应）号"),
    prev_mo: bool = Query(False, description="是否查询前 前置 工单"),
    next_mo: bool = Query(False, description="是否查询后 后续 工单"),
    origin_so: bool = Query(False, description="是否查询销售订单SO"),
    # x_api_key: str = Header(None, description="API密钥")
):
    try:
        result = await ApsPayloadSponsor.get_mo_by_supplyno(db_name=db_name, supplyno=supplyno, prev_mo=prev_mo, next_mo=next_mo, origin_so=origin_so)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取工单报表失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )

# @rt.get(
#     "/v_supply_complete",
#     tags=["生产数据 - 报工"],
#     summary="查询工单完成情况",
#     description="以最后一步工序完成数量为依据，汇总工单完成情况"
# )
# async def query_workreport(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套")
# ):
#     """
#     查询报工记录
#     db_name: str，数据库名称，多个数据库名称用逗号分隔
#     """
#     db_name = db_name.replace(" ", "")
#     return await db_query(db_name=db_name, model_or_tablename="v_supply_complete")


@rt.get(
    "/v_orderwc/page",
    tags=["报表 - 工序报表"],
    summary="获取工序报表",
    description="按工序开完工时间获取工序报表，默认开工时间为今日，默认完工时间为一周后。"
)
async def get_orderwc_page(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    start_time: datetime = Query(None, description="工序开工时间"),
    end_time: datetime = Query(None, description="工序完工时间"),
    page_size: int = Query(1000, description="每页数量"),
    page_index: int = Query(0, description="页码"),
    # x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    filter = []
    if start_time:
        filter.append(f"`DT_Start` >= '{start_time}'")
    if end_time:
        filter.append(f"`DT_End` <= '{end_time}'")
    filter_string = " AND ".join(filter)
    try:
        result = await db_query(db_name=db_name, model_or_tablename="v_orderwc", filter_string=filter_string, page_size=page_size, page_index=page_index)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取工序报表失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        ) 


@rt.get(
    "/v_orderwc/{supplyno}",
    tags=["报表 - 工序报表"],
    summary="获取工序报表",
    description="按编号（供应号）获取工序报表"
)
async def get_orderwc(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    supplyno: str = Path(..., description="工单（供应）号"),
    # x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo` = '{supplyno}'"
    try:
        result = await db_query(db_name=db_name, model_or_tablename="v_orderwc", filter_string=filter_string)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取工序报表失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


@rt.get(
    "/v_peg/page",
    include_in_schema=False,
    dependencies=[Depends(only_localhost())]
)
async def get_peg_page(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    page_size: int = Query(1000, description="每页数量"),
    page_index: int = Query(0, description="页码"),
):
    db_name = db_name.replace(" ", "")
    try:
        result = await db_query(db_name=db_name, model_or_tablename="v_peg", page_size=page_size, page_index=page_index)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"获取匹配关系报表失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )  


# @rt.get(
#     "/v_peg/mini",
#     tags=["报表 - 匹配关系"],
#     summary="获取匹配关系",
#     description="获取需求与供应的匹配关系，极简版本，仅体现对应关系",
#     include_in_schema=False,
#     dependencies=[Depends(only_localhost())]
# )
# async def get_peg_relation(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     page_size: int = Query(10000, description="每页数量"),
#     page_index: int = Query(0, description="页码"),
# ):
#     db_name = db_name.replace(" ", "")
#     return await db_query(db_name=db_name, model_or_tablename="v_peg", page_size=page_size, page_index=page_index)


@rt.get(
    "/v_matdailyqtyreport",
    tags=["报表 - 库存动态"],
    summary="获取按日期分组的库存动态报表",
    description="获取按日期分组的库存动态报表"
)
async def get_matdailyqtyreport(
        db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
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
    from apps.data_opt.components import ApsPayloadSponsor
    
    try:
        result = await ApsPayloadSponsor.get_date_grouped_mat_daily_qty(
            db_name=db_name,
            period=period,
            groupdates=groupdates,
            materialno=materialno
        )
    except ValueError as e:
        return standard_response(status_code=status.HTTP_400_BAD_REQUEST, success=0, message=str(e))
    
    if not result:
        return standard_response(status_code=status.HTTP_204_NO_CONTENT, message="No data available", meta={'total': 0}, data=result)
    
    return standard_response(status_code=status.HTTP_200_OK, meta={'total': len(result)}, data=result)


@rt.post(
    "/t_confirm",
    tags=["生产数据 - 报工"],
    summary="新增报工记录",
    description="新增报工记录"
)
async def create_workreport(
    data: List[AcceptConfirm] = Body(...),
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    return_data: bool = Query(False, description="是否返回数据"),
    x_api_key: str = Header(None, description="API密钥")
):
    """
    新增报工记录
    db_name: str，数据库名称，多个数据库名称用逗号分隔
    """
    db_name = db_name.replace(" ", "")
    try:
        # await db_query(db_name=db_name, model_or_tablename="t_orderwc", filter_string=f"`SupplyNo`='{supplyno}' AND `ItemNo`='{itemno}'")
        result = await db_bupsert(db_names=db_name, model_or_tablename="t_confirm", data_list=data)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data if return_data else None,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"新增报工记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )



@rt.delete(
    "/t_confirm/{supplyno}/{itemno}",
    tags=["生产数据 - 报工"],
    summary="删除报工记录",
    description="删除报工记录"
)
async def delete_workreport(
    db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
    supplyno: str = Path(..., description="工单号"),
    itemno: str = Path(..., description="工序项目"),
    x_api_key: str = Header(None, description="API密钥")
):
    db_name = db_name.replace(" ", "")
    filter_string = f"`SupplyNo`='{supplyno}'"
    if not itemno == "...":
        filter_string += f" AND `ItemNo`='{itemno}'"
    try:
        result = await db_delete(db_names=db_name, model_or_tablename="t_confirm", filter_string=filter_string)
        return standard_response(
            status_code=200,
            success=result.success,
            message=result.message,
            data=result.data,
            meta=result.meta
        )
    except Exception as e:
        logger.error(f"删除报工记录失败: {str(e)}")
        return standard_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=0,
            message=f"操作失败：{str(e)}",
            data=[],
            meta={}
        )


# @rt.patch(
#     "/t_confirm",
#     tags=["生产数据 - 报工"],
#     summary="确认报工记录",
#     description="确认报工记录",
#     include_in_schema=False,
#     dependencies=[Depends(only_localhost())]
# )
# async def confirm_workreport(
#     db_name: str = Query(MYAPS_MAIN_DB, examples={"default": {"value": MYAPS_MAIN_DB}}, description="账套"),
#     x_api_key: str = Header(None, description="API密钥")
# ):
#     """
#     确认报工记录
#     db_name: str，数据库名称，多个数据库名称用逗号分隔
#     """
#     db_name = db_name.replace(" ", "")
#     result = await call_dbprocdure(db_names=db_name, procedure_name="UpdateConfirmQtyToOrderWC")
#     return result

