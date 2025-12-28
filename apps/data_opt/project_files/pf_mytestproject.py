"""
我的测试项目
"""

import os, logging, requests


import requests, logging
import pandas as pd
from datetime import datetime

from fastapi import status

from ._base import (
    ScheduleTasksAbc, MyapsDbActionsAbc, DefaultValueAbc, DefaultParamsAbc,
    file_log, console_log, standard_response, get_session, HapConnection
    )

#################################################################################
# ⬇️对象及项目参数
#################################################################################

hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='d519a8ea60f9efa6',
    sign='NjAwYzI5OWJlMTNhNTcwODM5ZTEwOWE2YjE3ZDZiNWRmYzk4NTJjNTZmODQ4N2EzNGNjNWM2ZGMzNTBlYjY0Ng=='
)

class DefaultParams(DefaultParamsAbc):
    pass

class DefaultValue(DefaultValueAbc):
    
    MAT_PLANT = "..."   # 默认工厂
    MAT_PLANNER = "..."   # 默认计划员
    MAT_LOCATION = "..."  # 默认车间

#################################################################################
# ⬇️项目可复用逻辑
#################################################################################
...



#################################################################################
# ⬇️定时任务设置
#################################################################################
class ScheduleTasks(ScheduleTasksAbc):
    @classmethod
    async def get_bom(cls, *args, **kwargs):
        pass

    



#################################################################################
# ⬇️数据库事件处理
#################################################################################
class MyapsDbActions(MyapsDbActionsAbc):
    pass