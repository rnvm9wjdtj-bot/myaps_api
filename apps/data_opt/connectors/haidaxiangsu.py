import os, requests, logging, atexit, datetime
import pandas as pd
from datetime import datetime

from fastapi import status
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from config import uservar as uv
from config.settings import MYAPS_MAIN_DB, MYAPS_ORIGIN_URL
from apps.data_opt.utils.scheduler import daily_task, hourly_task, interval_task, cron_task
from apps.io_api.common import standard_response


scheduled_dbs = os.getenv('SCHEDULED_DBS').split(',')
main_db = MYAPS_MAIN_DB

werks = '1600'

this_base_url = 'http://localhost:8000'
this_session = requests.Session()

myaps_origin_url = MYAPS_ORIGIN_URL

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


#################################################################################
#
# SAP 数据交互通用组件
#
#################################################################################
from apps.data_opt.utils.common import add_basic_auth_requests

sap_url1 = 'http://192.168.201.2:8000/zrestful_test2?sap-client=800'  # 库存
sap_url2 = 'http://192.168.1.170:8001/zrestful_plan?sap-client=500'  # 计划

sap_username = 'T058'
sap_password = '123456'
# 创建requests会话
sap_session1 = requests.Session()
sap_session2 = requests.Session()

# 添加Basic认证
add_basic_auth_requests(sap_session1, sap_username, sap_password)
add_basic_auth_requests(sap_session2, sap_username, sap_password)

# import json
import uuid
import requests
from datetime import datetime
# from typing import Dict, Any, Optional


def sap_post(url: str, session: requests.Session, interface_id: str, data: dict):
    """
    向SAP系统发送POST请求
    url: 请求URL
    session: requests会话
    data: 请求数据
    """
    headers = {
            "INTF_ID": interface_id,
            "SRC_SYSTEM": "APS", 
            "DEST_SYSTEM": "SAP",
            "SRC_MSGID": str(uuid.uuid4()).replace("-", ""),
            "BACKUP1": "",
            "BACKUP2": ""
    }
    response: requests.Response = session.post(url, headers=headers, json={
        "HEAD": headers,
        "BODY": [data]
    })

    response_json = {}
    if response.status_code == status.HTTP_200_OK:
        response_json = response.json()
        logger.info(f"POST请求成功，状态码：{response.status_code}，响应内容：{response_json}")
    else:
        logger.error(f"POST请求失败，状态码：{response.status_code}，响应内容：{response.text}")
    return {
        'status_code': response.status_code,
        'response_text': response.text,
        'response_json': response_json
    }

#################################################################################
# 定义可复用的逻辑
#################################################################################

schedule_task_hour = os.getenv('SCHEDULE_TASK_HOUR', '9,12,15')
schedule_task_minute = os.getenv('SCHEDULE_TASK_MINUTE', 0)

@cron_task(hour=schedule_task_hour, minute=schedule_task_minute)
async def refresh_stock(db_name: str | None = None): 
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    db_name: 账套名称，默认刷新所有账套
    """
    logger.info("开始执行刷新库存任务")
    response = None
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        response = sap_session1.get(url=f"{sap_url1}", headers={'interface': 'stock', 'werks': werks})
        data = response.json()['data']
        stock = pd.DataFrame(data)
        stock = stock.astype({
            'werks': 'str',
            'matnr': 'str',
            'lgort': 'str',
            'labst': 'int32',
            'labst2': 'int32',
            'charg': 'str'
        })
        stock['avail_qty'] = stock['labst'] + stock['labst2']
        stock['supplyno'] = stock['werks'] + '-' + stock['matnr'] # 注意不要用f string，否则supplyno会变成所有料号的超长字符串
        stock['type'] = 'ST'
        stock['priority'] = uv.default_priority
        stock['avail_date'] = today
        stock['dt_req'] = today
        stock['status'] = 'NEW'
        stock['category'] = ''
        stock['create_date'] = today
        stock = (stock
                        .groupby(['supplyno'], as_index=False)
                        .agg({
                            'matnr': 'first',
                            'avail_qty': 'sum',
                            'type': 'first',
                            'avail_date': 'first',
                            'dt_req': 'first',
                            'priority': 'first',
                            'status': 'first',
                            'category': 'first',
                            'create_date': 'first',
                        })) 
        stock = stock.rename(columns={
            'matnr': 'materialno',
        })
        stock_data = stock.to_dict(orient='records')
        if not db_name:
            for db in scheduled_dbs:
                this_session.delete(f"{this_base_url}/api/t_supply?db_name={db}&type=ST")
                this_session.post(f"{this_base_url}/api/t_supply?db_name={db}", json=stock_data)
                logger.info(f"刷新库存任务执行完成，账套：{db}")
                response = standard_response(status_code=status.HTTP_200_OK, success=1, message=f"刷新库存任务执行完成，账套：{db}")
        else:
            this_session.delete(f"{this_base_url}/api/t_supply?db_name={db_name}&type=ST")
            this_session.post(f"{this_base_url}/api/t_supply?db_name={db_name}", json=stock_data)
            logger.info(f"刷新库存任务执行完成，账套：{db_name}")
            response = standard_response(status_code=status.HTTP_200_OK, success=1, message=f"刷新库存任务执行完成，账套：{db_name}")
    except Exception as e:
        logger.error(f"刷新库存任务执行失败: {str(e)}")
        response = standard_response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, success=0, message=f"刷新库存任务执行失败: {str(e)}")
    return response


async def insert_pl_to_sap(pl_data: dict):
    """
    以数据库binlog为触发条件，将主账套中需要转MO的PL推送到SAP
    """
    try:
        supply_response = this_session.get(f"{this_base_url}/api/v_supply_mo?db_name={main_db}&supplyno={pl_data['SupplyNo']}")
        supply_response_json = supply_response.json()
        supply_data = supply_response_json['data'][0]
        start_datetime = supply_data[uv.v_supply_mo['DT_OrdStart']].strftime('%Y%m%d %H:%M:%S')
        end_datetime = supply_data[uv.v_supply_mo['DT_OrdEnd']].strftime('%Y%m%d %H:%M:%S')
        orderwc = supply_data['orderwc']
        data = {
            # "CY_SEQNR": supply_data['supplyno'],  # APS单号
            "WERKS": werks,  # 工厂
            "MATNR": supply_data[uv.v_supply_mo['MaterialNo']],
            "AUART": "ZP01",  # 订单类型
            "VERID": "SAP",    # 生产版本
            "GSTRP": start_datetime.split(' ')[0],  # 基本开始日期
            "GLTRP": end_datetime.split(' ')[0],  # 基本完成日期
            "GAMNG": supply_data[uv.v_supply_mo['Avail_Qty']],  # 总订单数量
            # "FEVOR": "SAP",  # 生产主管
            "WEMPF": "SAP",  # 产线代码
            "BACKUP1": ','.join([i[uv.v_orderwc['WorkCenter']] for i in orderwc])
        }

        sap_response = await sap_post(url=sap_url2, session=sap_session2, interface_id="ZPP_PLAN_ORD_CREATE", data=data)
        sap_response_json = sap_response['response_json']
        sap_mo_data = sap_response_json['BODY'][0]
        if sap_mo_data['STATUS'] == 'S':
            logger.info(f"推送计划任务执行成功，账套：{main_db}，MO单号：{sap_mo_data['AUFNR']}")

            # TODO 调用myaps接口，更新pl号为sap工单号

        else:
            logger.error(f"推送计划任务执行失败，账套：{main_db}，错误信息：{sap_mo_data['MESSAGE']}")
    except Exception as e:
        logger.error(f"推送计划任务执行失败: {str(e)}")

#################################################################################
# 数据库事件处理器
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor

@mysql_monitor.on_update_for_table("t_supply", database=main_db)
async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    print(f"更新到 {database}.{table}: {data}")
    print(f"数据变更: {data_diff}")
    # if database != main_db:
    #     return
    supply_old_type = data['old']['Type']
    supply_new_type = data['new']['Type']
    if supply_old_type == 'PL' and supply_new_type == 'MO':
        return await insert_pl_to_sap(data['new'])

