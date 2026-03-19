"""
加载当前项目文件（项目py）
"""

import os, importlib, requests

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL
from globalobjects.globalconst import OrderStatusEnum
from apps.io_api.utils.common import dict_to_lower_keys



project_dir = os.getenv("PROJECT_DIR")
project_client = importlib.import_module(f'project_files.{project_dir}.client')


try:
    hap_conn = project_client.hap_conn
except:
    hap_conn = None



#################################################################################
# ⬇️MYAPS数据库事件HOOK
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor


@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    data_before = dict_to_lower_keys(data['old'])
    status_before = data_before['status']

    data_now = dict_to_lower_keys(data['new'])
    type_now = data_now['type']
    status_now = data_now['status']
    no_now = data_now['supplyno']

    # 确认/下达生产计划单PL (当PL状态从NEW或CRE变为A2E时)
    if type_now == 'PL' and status_now == OrderStatusEnum.A2E.value and status_before in ["NEW", "CRE"]:
        project_client.onclick_release_button(no_now)


    # # 工单关闭
    # if type_now == 'MO' and status_now == OrderStatusEnum.CMP.value:
    #     project_client.ApsAction.when_mo_close(data_now)

