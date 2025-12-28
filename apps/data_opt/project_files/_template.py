"""
项目文件模板
"""

import os, logging, requests


from . import ScheduleTasksAbc, MyapsDbActionsAbc, DefaultValueAbc, DefaultParamsAbc, request_session
from apps.data_opt.utils.common import add_basic_auth_requests
from apps.data_opt.components.hap import HapConnection

#################################################################################
# ⬇️对象及项目参数
#################################################################################

hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='...',
    sign='...'
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
    pass

    



#################################################################################
# ⬇️数据库事件处理
#################################################################################
class MyapsDbActions(MyapsDbActionsAbc):
    pass