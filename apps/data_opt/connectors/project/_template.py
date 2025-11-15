"""
XXXX的连接器
"""

import os, logging

from config.settings import MYAPS_MAIN_DB, MYAPS_BASE_URL, THIS_SERVER_HOST, THIS_SERVER_PORT
from . import ScheduleTasksAbc, MyapsDbActionAbc
from apps.data_opt.utils.common import add_basic_auth_requests


#################################################################################
# ⬇️局部变量
#################################################################################
scheduled_dbs = os.getenv('SCHEDULED_DBS').split(',')
main_db = MYAPS_MAIN_DB

this_base_url = f'http://{THIS_SERVER_HOST}:{THIS_SERVER_PORT}'
myaps_base_url = MYAPS_BASE_URL

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
class ScheduleTaskAbc(ScheduleTasksAbc):
    def __init__(self, scheduled_dbs: list[str], *args, **kwargs):
        super().__init__(scheduled_dbs, *args, **kwargs)

    



#################################################################################
# ⬇️数据库事件处理
#################################################################################
class MyapsDbAction(MyapsDbActionAbc):
    def __init__(self, monitored_db: str, *args, **kwargs):
        super().__init__(monitored_db, *args, **kwargs)