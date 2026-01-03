"""
项目文件模板
"""

import requests, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

from ._base import (
    ProjectParamsBase, DefaultValueBase, DbEventBase,
    file_log, console_log, standard_response, get_session, HapConnection
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

class ProjectParams(ProjectParamsBase):
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
class DbEvent(DbEventBase):
    pass