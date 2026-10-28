"""
正杰机械
"""

import asyncio
from typing import Dict, Any, Union, Tuple

from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, CLIENT_LOGGER, CLIENT_SESSION, PROJECT_JSON_FILE,
    ApsPayloadSponsor, EventResultPoster, get_session, CacheItem,
    RemindType, async_rate_limit, event_batch_handler,
    TSupply, async_service_operation, batch_service_operation
)

from apps.data_opt.components.mino_ime import ImeConnection, ImeMo, ImeOperation, ImeRoute, ImeWorkUnitType
# from apps.data_opt.components.mino_ime import ImeMaterial  # 物料推送已注释，需启用时取消注释

#################################################################################
# ⬇️ 连接组件
#################################################################################
ime_conn = ImeConnection()
ime_conn.register_source(ImeMo, ImeOperation, ImeRoute, ImeWorkUnitType)



#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
_REMAIN_NATIVE_SUPPLYNO = False





##################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################





#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(2), description="确认报工")
async def task_confirm_workreport():
    await ApsPayloadSponsor.confirm_workreport()



#################################################################################
# ⬇️ 数据库事件
#################################################################################
@event_batch_handler(reminder=None)
@batch_service_operation(module="事件处理")
async def batch_handle_pl_status_a2e(event_data_list: list[dict], _erp: EventResultPoster, description="下达工序任务单"):
    await ImeMo.create_batch(
        event_data_list=event_data_list,
        _erp=_erp,
        production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.BOM],
        # pydantic_model=create_custom_mo_push_model,
    )


@event_batch_handler(reminder=None)
@batch_service_operation(module="事件处理")
async def batch_handle_mat_wc_insert(event_data_list: list[dict], _erp: EventResultPoster, description="工艺路线新增"):
    involved_itemnos = list({row['itemno'] for row in event_data_list if row['itemno']})
    operation_details = await ApsPayloadSponsor.extract_unique_matwcitem(itemnos=involved_itemnos)
    await ImeOperation.create_or_update(operation_details)
    await ImeRoute.create(data=event_data_list)


@event_batch_handler(reminder=None)
@batch_service_operation(module="事件处理")
async def batch_handle_workcenter_insert(event_data_list: list[dict], _erp: EventResultPoster, description="工作中心新增"):
    await ImeWorkUnitType.create_batch(data=event_data_list)


#################################################################################
# ⬇️ 辅助推送（不在对接合同范围内，需手动调用）
#################################################################################
# async def push_materials(data: list[dict]):
#     """
#     手动推送物料主数据到明珞 MES

#     注意：物料推送不在双方对接合同范围内，仅用于辅助推送工序任务单所依赖的缺失物料。

#     Args:
#         data: 物料数据列表，每个元素至少包含 materialno 和 materialname

#     Usage:
#         await push_materials([
#             {"materialno": "2100-011-300", "materialname": "成品物料"},
#             {"materialno": "ZA", "materialname": "ZA"},
#         ])
#     """
#     return await ImeMaterial.create_or_update(data)



