"""
江阴海达橡塑的连接器
"""

import requests, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status

from globalobjects import filer_timed_logger


from apps.io_api.common import standard_response
from . import ScheduleTasksAbc, MyapsDbActionsAbc, DefaultValueTplt, this_session#, myaps_base_url


#################################################################################
# ⬇️项目常量
#################################################################################
class DefaultValue(DefaultValueTplt):

    MAT_PLANT = "1600"   # 默认工厂
    MAT_PLANNER = "haida"   # 默认计划员
    MAT_LOCATION = "1600"  # 默认车间
 

#################################################################################
# ⬇️模块变量
#################################################################################

main_db = MyapsDbActionsAbc.main_db

werks = "1600"

file_logger = filer_timed_logger.setup_logging(__name__)
# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


#################################################################################
# SAP 数据交互
#################################################################################
from apps.data_opt.utils.common import add_basic_auth_requests

sap_url1 = 'http://192.168.201.2:8000/zrestful_test2?sap-client=800'  # 库存
sap_url2 = 'http://192.168.201.2:8000/zrestful_plan?sap-client=800'  # 计划

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
# from typing import Dict, Any, Optional


async def sap_post(url: str, session: requests.Session, interface_id: str, data: dict):
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
# ⬇️定时任务设置
#################################################################################
class ScheduleTasks(ScheduleTasksAbc):
    @classmethod
    async def refresh_stock(cls, db_name: str | None = None): 
        """
        刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
        db_name: 账套名称，默认刷新所有账套
        """
        logger.info("开始执行刷新库存任务")
        response = None
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
            stock['priority'] = 0
            stock['avail_date'] = now
            stock['dt_req'] = now
            stock['status'] = 'NEW'
            stock['category'] = ''
            stock['create_date'] = now
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

            dbs = db_name or ','.join(cls.scheduled_dbs)
            this_session.delete(f"{cls.this_base_url}/api/t_supply?db_name={dbs}&type=ST")
            this_session.post(f"{cls.this_base_url}/api/t_supply?db_name={dbs}", json=stock_data)
            logger.info(f"刷新库存任务执行完成，账套：{dbs}")
            response = standard_response(message=f"刷新库存任务执行完成，账套：{dbs}")
            
        except Exception as e:
            logger.error(f"刷新库存任务执行失败: {str(e)}")
            response = standard_response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, success=0, message=f"刷新库存任务执行失败: {str(e)}")
        return response


#################################################################################
# ⬇️数据库事件处理
#################################################################################
class MyapsDbActions(MyapsDbActionsAbc):

    @classmethod
    async def confirm_pl(cls, pl_data: dict):
        """
        确认计划任务，将主账套中需要转MO的PL推送到SAP，将计划任务状态更新为已确认
        """
        try:
            supply_response = this_session.get(f"{cls.this_base_url}/api/v_supply_mo?db_name={main_db}&supplyno={pl_data['supplyno']}")
            supply_response_json = supply_response.json()
            supply_data = supply_response_json['data'][0]
            start_datetime = supply_data['dt_ordstart']#.strftime('%Y%m%d %H:%M:%S')
            end_datetime = supply_data['dt_ordend']#.strftime('%Y%m%d %H:%M:%S')
            orderwc = supply_data['orderwc']
            data = {
                # "CY_SEQNR": supply_data['supplyno'],  # APS单号
                "WERKS": werks,  # 工厂
                "MATNR": supply_data['materialno'],
                "AUART": "ZP01",  # 订单类型
                "VERID": "SAP",    # 生产版本
                "GSTRP": start_datetime.split('T')[0],  # 基本开始日期
                "GLTRP": end_datetime.split('T')[0],  # 基本完成日期
                "GAMNG": supply_data['avail_qty'],  # 总订单数量
                # "FEVOR": "SAP",  # 生产主管
                "WEMPF": "SAP",  # 产线代码
                "BACKUP1": ','.join([i['workcenter'] for i in orderwc])
            }

            sap_response = await sap_post(url=sap_url2, session=sap_session2, interface_id="ZPP_PLAN_ORD_CREATE", data=data)
            sap_response_json = sap_response['response_json']
            sap_mo_data = sap_response_json['BODY'][0]
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
             
            if sap_mo_data['STATUS'] == 'S':
                log_msg = f"✅推送计划任务执行成功，账套：{main_db}，MO单号：{sap_mo_data['AUFNR']}"
                logger.info(log_msg)
                file_logger.info(log_msg)
                pl_data['mono'] = sap_mo_data['AUFNR']
                pl_data['status'] = 'E2A'
                pl_data['memo'] = f'✅{now} @ERP【{sap_mo_data['MESSAGE']}】'
                pl_data['is_execute_updates'] = True
            else:
                log_msg = f"🚫推送计划任务执行失败，账套：{main_db}，错误信息：{sap_mo_data['MESSAGE']}"
                logger.error(log_msg)
                file_logger.error(log_msg)
                pl_data['mono'] = ''
                pl_data['status'] = 'CRE'   # ❗❗失败情况下，状态务必回撤为 CRE ，否则后续无法再次下达
                pl_data['memo'] = f'🚫{now} @ERP【{sap_mo_data['MESSAGE']}】'
                pl_data['is_execute_updates'] = False
        except Exception as e:
            log_msg = f"🚫推送计划任务执行失败: {str(e)}"
            logger.error(log_msg)
            file_logger.error(log_msg)
            pl_data['mono'] = ''
            pl_data['status'] = 'CRE'
            pl_data['memo'] = f'🚫{now} @APS【{str(e)}】'
            pl_data['is_execute_updates'] = False

        await super().confirm_pl(pl_data)


