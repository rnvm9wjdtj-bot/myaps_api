"""
淮安超越橡塑项目文件
需要 ERP 推送的数据：
- 各种主数据
- 销售订单SO 
- 审批好的新 PO 及后续执行情况
- 报工数据

其他：
- 物料主数据
    - free1 是否倒冲料，Y 表示倒冲料，N 表示普通物料
"""
import asyncio
from typing import Dict, Any, Union

from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, CLIENT_LOGGER, CLIENT_SESSION, PROJECT_JSON_FILE,
    ApsPayloadSponsor, EventResultPoster, get_session, CacheItem,
    RemindType, async_rate_limit, event_batch_handler,
    TSupply, async_service_operation, batch_service_operation
)


from apps.data_opt.components.yonyou_tplus import (
    YonyouTplusConnection, TplusStock, TplusMo, TplusRs, TplusPr,
    RsPushModel, MoPushModel, model_validator
)

#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
_REMAIN_NATIVE_SUPPLYNO = True   # 本项目需要推送 MO 前后关系，所以必须保留原生供应号，否则会导致关系断开
_AUTO_APPROVE_MO = True   # 自动审批 MO
_AUTO_APPROVE_PR = True   # 自动审批请购单


hacyxs_tplus_conn = YonyouTplusConnection()
hacyxs_tplus_conn.register_source([TplusStock, TplusMo, TplusRs, TplusPr])

#################################################################################
# ⬇️ 通知相关
#################################################################################

# 从 send_alert.py 导入业务告警专用提示器
from .remind import bus_reminder, ops_reminder


# ⬇️binlog监听告警注册（统一使用全局AlertManager）
from apps.data_opt.utils.binlog_listener import binlog_listener as bl

bl.regist_reminder(ops_reminder)
CLIENT_LOGGER.info("binlog监听提示提醒器已注册到全局RemindManager")


#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
@async_service_operation(module="定时任务")
async def task_refresh_stock(description="刷新库存数据"):
    stock_data = await TplusStock.query_batch()
    await ApsPayloadSponsor.refresh_stock(stock_data, dbs=MYAPS_DB_SET)


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(1))
@async_service_operation(module="定时任务")
async def task_confirm_workreport(description="确认报工"):
    await ApsPayloadSponsor.confirm_workreport()

#################################################################################
# ⬇️ 数据库事件
#################################################################################

back_flush_warehouse = 'ck06'


async def mo_data_preprocessor(data: dict, _aps: ApsPayloadSponsor) -> dict:
    """MO 推送数据预处理器：补充物料信息映射和后续工单关系"""
    demand_list = data.get('demand_list', [])
    if demand_list:
        materialnos = [d['materialno'] for d in demand_list if d.get('materialno')]
        if materialnos:
            materials = await _aps.query_material(materialnos)
            data['materials_map'] = {item['materialno']: item for item in materials}

    supplyno = data.get('supplyno', '')
    next_mos = _aps._production_cache.get_peg_by_supply(supplyno)
    if next_mos:
        data['next_mos'] = next_mos

    return data


async def rs_data_preprocessor(data: dict, _aps: ApsPayloadSponsor) -> dict:
    """RS 推送数据预处理器：补充物料 free1 映射，供倒冲料过滤使用"""
    mo_material_details = data.get('mo_material_details', [])
    materialnos = [md['Inventory']['Code'] for md in mo_material_details if md.get('Inventory', {}).get('Code')]
    if materialnos:
        materials = await _aps.query_material(materialnos)
        data['materials_map'] = {item['materialno']: item for item in materials}
    return data


class CustomMoPushModel(MoPushModel):
    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = super().model_valid(values)

        workcenter = None
        try:
            first_orderwc = values["orderwc"][0]
            workcenter = first_orderwc.get("workcenter", "")
        except:
            workcenter = ""
        cleaned_values['Department'] = {'Code': workcenter}

        mo_details = cleaned_values['ManufactureOrderDetails'][0]
        mo_material_details: list[dict] = mo_details['ManufactureOrderMaterialDetails']

        materials_map: dict = values.get('materials_map', {})
        for md in mo_material_details:
            materialno = md['Inventory']['Code']
            free1 = materials_map.get(materialno, {}).get('free1', "")
            if True:    # free1.upper().strip() == 'Y':    # 为 倒冲料
                md['Warehouse'] = {'Code': back_flush_warehouse}
                md.pop('IsMaterialRequest', None)

        mo_details['DynamicPropertyKeys'] = []
        mo_details['DynamicPropertyValues'] = []
        next_mos: list[str] = values.get('next_mos', [])
        if next_mos:
            next_mo_sn = ','.join(next_mos)
            if next_mo_sn:
                mo_details['DynamicPropertyKeys'].append('priuserdefnvc1')
                mo_details['DynamicPropertyValues'].append(next_mo_sn)

        so = values.get('so')
        if so:
            mo_details['DynamicPropertyKeys'].append('priuserdefnvc4')
            mo_details['DynamicPropertyValues'].append(so.get('demandno', ""))
        return cleaned_values


class CustomRsPushModel(RsPushModel):
    class Config:
        extra = 'allow'

    @model_validator(mode="before")
    @classmethod
    def model_valid(cls, values: Dict[str, Any]):
        cleaned_values = super().model_valid(values)

        mr_details: list[dict] = cleaned_values['MaterialRequestDetails']
        materials_map: dict = values.get('materials_map', {})

        mr_details2 = []
        for md in mr_details:
            materialno = md['Inventory']['Code']
            free1 = materials_map.get(materialno, {}).get('free1', "")
            if free1.upper().strip() != 'Y':    # 非 倒冲料
                mr_details2.append(md)

        cleaned_values['MaterialRequestDetails'] = mr_details2
        return cleaned_values


@event_batch_handler(reminder=bus_reminder)
@batch_service_operation(module="事件处理")
async def batch_handle_pl_status_a2e(event_data_list: list[dict], _erp: EventResultPoster, description="下达生产加工单至 T+"):
    await TplusMo.create_batch(
        event_data_list=event_data_list,
        _erp=_erp,
        production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL],
        pydantic_model=CustomMoPushModel,
        remain_native_supplyno=_REMAIN_NATIVE_SUPPLYNO,
        data_preprocessor=mo_data_preprocessor,
        auto_approve=_AUTO_APPROVE_MO,
    )


# @event_batch_handler(reminder=bus_reminder, remind_start=False)
# @batch_service_operation(module="事件处理")
# async def batch_handle_pl_to_mo(event_data_list: list[dict], _erp: EventResultPoster, description="推送领料申请至 T+"):
#     await TplusRs.create_batch(
#         event_data_list=event_data_list,
#         _erp=_erp,
#         production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.DEMAND, CacheItem.MATERIAL],
#         pydantic_model=CustomRsPushModel,
#         data_preprocessor=rs_data_preprocessor,
#     )


@event_batch_handler(reminder=bus_reminder)
@batch_service_operation(module="事件处理")
async def batch_handle_pr_status_a2e(pr_data_list: list[dict], _erp: EventResultPoster, description="推送请购单至 T+"):
    await TplusPr.create(
        event_data_list=pr_data_list,
        _erp=_erp,
        auto_approve=_AUTO_APPROVE_PR,
    )

