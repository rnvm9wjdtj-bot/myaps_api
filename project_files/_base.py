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

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, SCHEDULER_MINUTE
from globalobjects.globalconst import OrderStatusEnum
from apps.data_opt.utils.common import get_session


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from globalobjects import logger as log_config, CACHE_JSON, ProjectDefaultValues as pdv
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_supsert, db_update_by_index
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.utils.common import add_basic_auth_requests
from apps.data_opt.utils.data_processor import DataProcessor
from apps.data_opt.components._base import BaseConnection, ApsHelpers


# 配置日志
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')


# 获取统一日志器
console_log = log_config.get_logger(__name__)


def get_scheduler_minute(offset: int=0):

    minutes = []
    for m in SCHEDULER_MINUTE.split(','):
        minute = int(m) + offset
        minutes.append(str(minute % 60))
    return ','.join(minutes)


######### HAP MODEL #########
# from apps.data_opt.utils.hap import Model as HapModel, StrField, NumField, RelationField, SubtableField, ChoiceField


# class Material(HapModel):   
#     materialno = StrField(pk=True)
#     description = StrField()
#     size = StrField()
#     plant = StrField()
#     planner = StrField()
#     fifo = NumField()
#     leadday = NumField()
#     expday = NumField()
#     grday = NumField()
#     abc = StrField()
#     unit = StrField()
#     price = NumField()
#     groupno = StrField()
#     type_ = StrField(field_name="type")
#     phantom = StrField()
#     phantommin = NumField()
#     firmday = NumField()
#     daygap = NumField()
#     candelay = StrField()
#     lotsize = StrField()
#     lotfix = NumField()
#     lotmin = NumField()
#     lotmax = NumField()
#     lotround = NumField()
#     lotss = NumField()
#     lotpoint = NumField()
#     lottop = NumField()
#     planitem = StrField()
#     preday = NumField()
#     subday = NumField()
#     free1 = StrField()
#     free2 = StrField()
#     free3 = StrField()
#     memo = StrField()

#     class Meta:
#         table_name = "t_material"
