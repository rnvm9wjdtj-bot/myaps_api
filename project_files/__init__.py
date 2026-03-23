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
from globalobjects import EVENT_AGGREGATOR


def batch_process_pr_events(pr_data_list: list[dict]):
    """批量处理PR状态变更事件"""
    try:
        for pr_data in pr_data_list:
            try:
                project_client.on_pr_created(pr_data)
            except Exception as e:
                pass
    except Exception as e:
        pass


# 注册PR事件处理
EVENT_AGGREGATOR.register(
    event_type="|pr_created|",
    handler=batch_process_pr_events,
    # dedup_key=lambda x: x,
    # batch_size=50,
    # flush_interval=5
)



@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    from apps.data_opt.components._base import ApsHelpers

    data_before = dict_to_lower_keys(data['old'])
    status_before = data_before['status']

    data_now = dict_to_lower_keys(data['new'])
    type_now = data_now['type']
    status_now = data_now['status']
    # no_now = data_now['supplyno']

    # 确认/下达生产计划单PL (当PL状态从NEW或CRE变为A2E时)
    if type_now == 'PL' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
        try:
            project_client.on_pl_status_a2e(data_now)
        except Exception as e:
            pass

    
    # 推送采购申请PR - 使用事件聚合器
    # if type_now == 'PR' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
    #     EVENT_AGGREGATOR.add("|pr_created|", data_now)


@mysql_monitor.on_insert_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_insert_supply(database: str, table: str, data: dict):
    """处理t_supply表的插入事件"""
    # from apps.data_opt.components._base import ApsHelpers

    # data_now = dict_to_lower_keys(data)
    # type_now = data_now['type']
    # status_now = data_now['status']
    # # no_now = data_now['supplyno']

    # # 确认/下达生产计划单PL (当PL状态从NEW或CRE变为A2E时)
    # if type_now == 'PL' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
    #     try:
    #         project_client.on_pl_status_a2e(data_now)
    #     except Exception as e:
    #         pass

    
    # 推送采购申请PR - 使用事件聚合器
    # if type_now == 'PR' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
    #     EVENT_AGGREGATOR.add("|pr_created|", data_now)
   