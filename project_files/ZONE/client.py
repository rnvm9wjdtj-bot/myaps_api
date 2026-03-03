"""
项目文件要声明 ApsBaseAction 子类，并根据项目实际情况继承或覆写其中的方法

class ApsAction(ApsBaseAction):
    def click_release_button(self, supplyno: str):
        pass
"""

import requests, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

from .._base import (
    filelog_normal, filelog_error, console_log, standard_response, get_session, HapConnection, ApsBaseAction,
    )


#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
hap_conn = None

hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='...',
    sign='...'
)

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
    def click_release_button(cls, supplyno: str, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        🅰 supplyno: PL计划单编号
        """
        pass

    # @classmethod
    # def when_mo_close(cls, mo_data: dict, *args, **kwargs):
    #     """
    #     当MO关闭时该方法将被自动调用
    #     🅰 mo_data: MO数据
    #     """
    #     pass