"""测试"""

from re import A
import requests, uuid, asyncio, json#, logging#, os, atexit
import pandas as pd
from datetime import datetime
from typing import List, Dict, Union

from contextlib import asynccontextmanager
from fastapi import status
from dateutil.relativedelta import relativedelta

from core.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR
from .._base import (
    get_scheduler_minute, async_rate_limit, CacheItem,
    ApsPayloadSponsor, EventResultPoster, CLIENT_LOGGER, standard_response, get_session, event_batch_handler,
    cron_task, add_basic_auth_requests, db_delete, db_bupsert, db_query, PROJECT_JSON_FILE, pdv,
)


#################################################################################
# ⬇️定时任务设置
#################################################################################

@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(), description="刷新库存数据")
async def task_test():
    CLIENT_LOGGER.info("测试任务")



#################################################################################
# ⬇️APS事件
#################################################################################
from .remind import ops_reminder, bus_reminder


@event_batch_handler(reminder=bus_reminder)
async def batch_handle_pl_status_a2e(event_data_list: List[Dict], _erp: EventResultPoster, description="PL 单据下达"):
    CLIENT_LOGGER.info(f"PL 单据下达事件: {event_data_list}")