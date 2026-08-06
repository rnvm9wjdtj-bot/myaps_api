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

from apps.data_opt.components.mino import MinoConnection, MinoMo, MinoOperation, MinoRoute

#################################################################################
# ⬇️ 连接组件
#################################################################################
mino_conn = MinoConnection()
mino_conn.register_source([MinoMo, MinoOperation])



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




#################################################################################
# ⬇️ 数据库事件
#################################################################################
@event_batch_handler(reminder=None)
@batch_service_operation(module="事件处理")
async def batch_handle_pl_status_a2e(event_data_list: list[dict], _erp: EventResultPoster, description="下达工序任务单"):
    await MinoMo.create_batch(
        event_data_list=event_data_list,
        _erp=_erp,
        production_cache_items=[CacheItem.SUPPLY_MO, CacheItem.BOM],
        # pydantic_model=create_custom_mo_push_model,
    )


@event_batch_handler(reminder=None)
@batch_service_operation(module="事件处理")
async def batch_handle_mat_wc_insert(event_data_list: list[dict], _erp: EventResultPoster, description="工艺路线新增"):
    await MinoRoute.create(data=event_data_list)
    involved_itemnos = list({row['itemno'] for row in event_data_list if row['itemno']})
    operation_details = await ApsPayloadSponsor.extract_unique_matwcitem(itemnos=involved_itemnos)
    await MinoOperation.create_or_update(operation_details)



