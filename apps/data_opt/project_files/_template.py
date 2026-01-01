"""
项目文件模板
"""

import requests, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

from ._base import (
    ParamValueBase, DefaultValueBase, DbEventAbc,
    file_log, console_log, standard_response, get_session, HapConnection
    )

#################################################################################
# ⬇️对象及项目参数
#################################################################################

hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='...',
    sign='...'
)

class ParamValue(ParamValueBase):
    pass



class DefaultValue(DefaultValueBase):
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
...


#################################################################################
# ⬇️数据库事件处理
#################################################################################
class DbEvent(DbEventAbc):
    pass