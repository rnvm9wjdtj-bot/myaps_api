"""
导入包和常量，供各项目文件使用
"""

# import threading
import os, asyncio
import logging, json, requests, pandas as pd
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise

from globalobjects.globalconst import OrderStatusEnum


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, SCHEDULER_MINUTE
from globalobjects import logger as log_config, PROJECT_JSON_FILE, ProjectDefaultValues as pdv
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_supsert, db_update_by_index
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests, get_session
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components._base import ApsHelpers
from apps.data_opt.components.simple_hap import HapConnection


CLIENT_LOGGER = log_config.get_logger(__name__)

CLIENT_SESSION = get_session()

def get_scheduler_minute(offset: int=0):

    minutes = []
    for m in SCHEDULER_MINUTE.split(','):
        minute = int(m) + offset
        minutes.append(str(minute % 60))
    return ','.join(minutes)



from collections import namedtuple
# 定义任务执行结果的具名元组
TaskResult = namedtuple('TaskResult', ['status', 'error'])