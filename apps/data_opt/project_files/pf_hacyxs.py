"""
淮安超越橡塑项目文件
"""

import requests, logging, os#, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

from globalobjects._defaults import ProjectDefaultValues as pdv
from ._base import (
    ApsBaseAction,
    file_log, console_log, standard_response, get_session, HapConnection
    )

from ..components import yonyou_tplus


#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
hap_conn = None

hap_conn = HapConnection(
    app_key='601ae007d84ca95a',
    sign='ODVlMzNjYzA1ZTg1Yzg3YjI0NmQ5NTFmZGQ3OTk1MWYzMjE4M2JiMzYyNDEzMGU3NTY5YzI0YzEzYTYyYTExZA=='
)

tplus_conn = yonyou_tplus.TplusConnection()


#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################
...



#################################################################################
# ⬇️ 定时任务
#################################################################################
...


#################################################################################
# ⬇️ 数据库事件
#################################################################################
class ApsAction(ApsBaseAction):
    pass

    @classmethod
    async def click_release_button(cls, pl_data: dict, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        🅰 supplyno: PL计划单编号
        🅰 mono: MO号，可选，若非None则更改PL的SupplyNo
        """
        pass

    @classmethod
    async def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当工单管理的状态变为'CMP'（完成）时该方法将被自动调用
        🅰 mono: MO号
        """
        pass