"""
XXXX的连接器
"""

import os, logging, requests

# from config.settings import MYAPS_MAIN_DB, MYAPS_BASE_URL, THIS_SERVER_HOST, THIS_SERVER_PORT
from . import ScheduleTasksAbc, MyapsDbActionsAbc, this_base_url, myaps_base_url, this_session
from apps.data_opt.utils.common import add_basic_auth_requests


#################################################################################
# ⬇️模块变量
#################################################################################
scheduled_dbs = ScheduleTasksAbc.scheduled_dbs
main_db = MyapsDbActionsAbc.main_db



# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

#################################################################################
# ⬇️本文件内可复用的逻辑
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