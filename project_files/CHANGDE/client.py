from datetime import datetime, timedelta
import json

from .._base import cron_task, get_scheduler_minute, console_log


from apps.data_opt.components.ecerp_jky import (
    HapConnection, 
    JkyConnection, register_hap_models
    )


# source_codes = (
#     '$Company', '$Department', '$Staff', '$BankAccounts', '$Channel', '$GoodsCate', '$Warehouse', '$Logistic',
#     '&Customer', '&Sku', '&Trade', '&BusinessOrder', '&Order'
# )

source_codes = ('&Trade', )

_HAP_CONN = HapConnection()
_SORTED_MODELS = register_hap_models(_HAP_CONN, source_codes)
_ASYNC_HAP = _HAP_CONN.async_connection()
_JKY_CONN = JkyConnection()


# @cron_task(hour='0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23', minute=46)
@cron_task(hour=19, minute=0)
async def sync_incremental_data():
    slice_timerange = ("2026-03-11 03:00:00", "2026-03-11 04:00:00")
    for source_code, model in _SORTED_MODELS.items():
        await _JKY_CONN.data_to_hap(_ASYNC_HAP, source_code, slice_timerange)
