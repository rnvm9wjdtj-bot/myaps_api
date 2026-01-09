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

from ._base import (
    ProjectParamBase, DefaultValueBase, ApsBaseAction,
    file_log, console_log, standard_response, get_session, HapConnection
    )

from ..components.yonyou_tplus import TplusConnection
#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
hap_conn = None

hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='...',
    sign='...'
)

class ProjectParam(ProjectParamBase):
    pass


class DefaultValue(DefaultValueBase):
    MAT_PLANT = "..."   # 默认工厂
    MAT_PLANNER = "..."   # 默认计划员
    MAT_LOCATION = "..."  # 默认车间

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