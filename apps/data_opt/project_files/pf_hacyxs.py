"""
淮安超越橡塑项目文件
"""

import requests, logging, os#, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

# from globalobjects._defaults import ProjectDefaultValues as pdv
from ._base import (
    cron_task,
    ApsBaseAction, JSONManager, DataProcessor,
    file_log, console_log, standard_response, get_session, 
    )

from globalobjects import file_timed_logger
from ..components import yonyou_tplus, hap



#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
file_logger = file_timed_logger.setup_logging(__name__, log_filename='project.log')


hap_conn = None

hap_conn = hap.HapConnection(
    app_key='601ae007d84ca95a',
    sign='ODVlMzNjYzA1ZTg1Yzg3YjI0NmQ5NTFmZGQ3OTk1MWYzMjE4M2JiMzYyNDEzMGU3NTY5YzI0YzEzYTYyYTExZA=='
)
hap_conn.regist_worksheet(hap.get_maindata_worksheetinfo())


tplus_conn = yonyou_tplus.TplusConnection()
tplus_conn.auth()


#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################
def get_maindata_from_erp_to_hap():
    if not hap_conn:
        return
    material = tplus_conn.pull_from_source(source_name='material')
    hap_conn.worksheet('t_material').upsert(material)

    workcenter = tplus_conn.pull_from_source(source_name='workcenter')
    hap_conn.worksheet('t_workcenter').upsert(workcenter)

    route = tplus_conn.pull_from_source(source_name='route')
    hap_conn.worksheet('t_mat_wc').upsert(route)

    bom = tplus_conn.pull_from_source(source_name='bom')
    hap_conn.worksheet('t_mat_wc_bom').upsert(bom)


def push_pl_into_tplus_as_mo(pl_data: dict):
    supplymo_detaildata = ApsBaseAction._get_supplymo_detaildata(pl_data['supplyno'])
    response = tplus_conn.push_into_target(target_name='mo', data_list=[supplymo_detaildata])
    return response


#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour="8,10,12,14,16",minute="55")
def get_maindata_from_erp_to_hap_task(*args, **kwargs):
    console_log.info("⏰ 开始执行定时任务")
    get_maindata_from_erp_to_hap()
    console_log.info("⏰ 定时任务执行完成")


#################################################################################
# ⬇️ 数据库事件
#################################################################################
class ApsAction(ApsBaseAction):

    @classmethod
    async def click_release_button(cls, pl_data: dict, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        🅰 supplyno: PL计划单编号
        🅰 mono: MO号，可选，若非None则更改PL的SupplyNo
        """
        # try:
        return push_pl_into_tplus_as_mo(pl_data)


    @classmethod
    async def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当工单管理的状态变为'CMP'（完成）时该方法将被自动调用
        🅰 mono: MO号
        """
        pass