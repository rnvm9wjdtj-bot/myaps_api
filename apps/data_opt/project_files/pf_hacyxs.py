"""
淮安超越橡塑项目文件
"""
"""
项目文件要声明 ApsBaseAction 子类，并根据项目实际情况继承或覆写其中的方法

class ApsAction(ApsBaseAction):
    def press_release_button(self, pl_data: dict) -> None:
        pass
"""

import requests, logging#, os, atexit
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
    base_url='https://api.mingdao.com',
    app_key='601ae007d84ca95a',
    sign='ODVlMzNjYzA1ZTg1Yzg3YjI0NmQ5NTFmZGQ3OTk1MWYzMjE4M2JiMzYyNDEzMGU3NTY5YzI0YzEzYTYyYTExZA=='
)

tp_conn = yonyou_tplus.TplusConnection()


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