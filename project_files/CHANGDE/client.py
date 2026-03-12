from datetime import datetime, timedelta
import json

from .._base import cron_task, get_scheduler_minute, console_log, CACHE_JSON


from apps.data_opt.components.ecerp_jky import (
    HapConnection, 
    JkyConnection, register_hap_models
    )


_TASK_MINUTE = 0

schedule_tasks = {
    (0, ): ['$Company', '$Department', '$Staff', '$BankAccounts', '$Channel', '$GoodsCate', '$Warehouse', '$Logistic'],
    (0, ): ['~BusinessOrder', '~Trade', '~Order'],
    (0, ): ['^Customer', '^Sku', '^BusinessOrder', '^Trade'],
}


source_codes = {source_code for source_codes in schedule_tasks.values() for source_code in source_codes}

_HAP_CONN = HapConnection()
_SORTED_MODELS = register_hap_models(_HAP_CONN, source_codes)
_ASYNC_HAP = _HAP_CONN.async_connection()
_JKY_CONN = JkyConnection()

@cron_task(minute=_TASK_MINUTE)
async def exec_schedule():
    now = datetime.now()
    hour = now.hour
    this_slice_end = f"{now.strftime('%Y-%m-%d')} {hour:02d}:{_TASK_MINUTE:02d}:00"
    for task_hour, src_codes in schedule_tasks.items():
        if not hour in task_hour:
            continue
        sorted_src_codes = JkyConnection.sort_tasks(src_codes)
        for src_code in sorted_src_codes:
            if src_code.startswith('$'):
                # 如果是全量数据
                await _JKY_CONN.data_to_hap(_ASYNC_HAP, src_code)
            else:
                # 如果是增量数据
                last_slice_end = CACHE_JSON.get(f"last_slice_end / {src_code}", None)
                if last_slice_end:
                    slice_timerange = (last_slice_end, this_slice_end)
                    await _JKY_CONN.data_to_hap(_ASYNC_HAP, src_code, slice_timerange)
                CACHE_JSON.set(f"last_slice_end / {src_code}", this_slice_end)

# for task_time, src_codes in schedule_tasks.items():
#     hour, minute = task_time
#     _JKY_CONN.create_cron_task(
#         hour=hour,
#         minute=minute,
#         task_name=f"sync_changde_jky_data",
#         source_codes=src_codes,
#         async_hap=_ASYNC_HAP,
#     )

# @cron_task(hour='0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23', minute=46)
# @cron_task(hour=22, minute=42)
# async def sync_incremental_data():
#     slice_timerange = ("2026-03-11 00:00:00", "2026-03-12 00:00:00")
#     for source_code, model in _SORTED_MODELS.items():
#         await _JKY_CONN.data_to_hap(_ASYNC_HAP, source_code, slice_timerange)
