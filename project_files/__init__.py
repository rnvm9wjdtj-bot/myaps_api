"""
加载当前项目文件（项目py）
"""

import os, importlib, json, requests
from typing import NamedTuple

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, console_log
from globalobjects.globalconst import OrderStatusEnum
from apps.io_api.utils.common import dict_to_lower_keys
from globalobjects import logger as log_config


console_log = log_config.get_logger(__name__)
file_log = log_config.get_file_logger(__name__)


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



class ApsEvent:
    def __init__(self, event_type: str, description: str, batch_handler: str=None, single_handler:str=None, batch_size: int=10000, flush_interval: int=5):
        self.event_type = event_type
        self.description = description
        self.batch_handle_func = None
        self.single_handle_func = None
        self.warning_msg = ""

        try:
            self.batch_handle_func = getattr(project_client, batch_handler)
        except AttributeError:
            try:
                self.single_handle_func = getattr(project_client, single_handler)
            except AttributeError:
                self.warning_msg = f"模块【{project_client.__name__}】未实现【{event_type}】处理逻辑"
        
        if self.single_handle_func or self.batch_handle_func:
            EVENT_AGGREGATOR.register(event_type=self.event_type, handler=self.handle_func, batch_size=batch_size, flush_interval=flush_interval)


    def handle_func(self, events_data_list: list[dict]):
        if self.batch_handle_func is not None:
            self.batch_handle_func(events_data_list)
        elif self.single_handle_func is not None:
            for event_data in events_data_list:
                self.single_handle_func(event_data)
        else:
            log_msg = f"{self.warning_msg}数据：\n{json.dumps(events_data_list, ensure_ascii=False)}"
            console_log.warning(log_msg)
            file_log.warning(log_msg)

    
    def add_event(self, event_data: dict):
        EVENT_AGGREGATOR.add(event_type=self.event_type, event=event_data)



aps_pl_status_a2e_event = ApsEvent(event_type="|pl_status_a2e|", single_handler="handle_pl_status_a2e", batch_handler="batch_handle_pl_status_a2e", description="PL 单据下达")
aps_pr_created_event = ApsEvent(event_type="|pr_created|", single_handler="handle_pr_created", batch_handler="batch_handle_pr_created", description="PR 单据 创建")
# aps_dm_typeto_rs_event = ApsEvent(event_type="|dm_typeto_rs|", single_handler="handle_dm_typeto_rs", batch_handler="batch_handle_dm_typeto_rs", description="DM 变更为 RS")



@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    from apps.data_opt.components._base import ApsHelpers

    data_before = dict_to_lower_keys(data['old'])
    status_before = data_before['status']

    data_now = dict_to_lower_keys(data['new'])
    type_now = data_now['type']
    status_now = data_now['status']

    # 工单管理界面中，通过点击按钮下达生产计划单PL
    if type_now == 'PL' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
        aps_pl_status_a2e_event.add_event(data_now)



@mysql_monitor.on_insert_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_insert_supply(database: str, table: str, data: dict):
    """处理t_supply表的插入事件"""
    from apps.data_opt.components._base import ApsHelpers

    new_data = dict_to_lower_keys(data['new'])
    type_ = new_data['type']
    # status_now = new_data['status']

    if type_ == 'PR':
        aps_pr_created_event.add_event(new_data)
   


# @mysql_monitor.on_update_for_table("t_demand", database=MYAPS_MAIN_DB)
# def handle_update_demand(database: str, table: str, data: dict, data_diff: dict):
#     """处理t_demand表的更新事件"""
#     from apps.data_opt.components._base import ApsHelpers
#     data_before = dict_to_lower_keys(data['old'])
#     type_before = data_before['type']

#     data_now = dict_to_lower_keys(data['new'])
#     type_now = data_now['type']

#     if type_now == 'RS' and type_before == 'DM':
