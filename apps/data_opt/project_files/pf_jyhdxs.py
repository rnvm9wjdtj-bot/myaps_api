"""江阴海达橡塑"""

import requests, uuid#, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status
from dateutil.relativedelta import relativedelta


from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL
from ._base import (
    ProjectParamBase, DefaultValueBase, ApsBaseAction, 
    file_log, console_log, standard_response, get_session, HapConnection,
    cron_task, add_basic_auth_requests, db_delete, db_write
    )

#################################################################################
# ⬇️对象及项目参数
#################################################################################
hap_conn = HapConnection(
    base_url='https://api.mingdao.com',
    app_key='d519a8ea60f9efa6',
    sign='NjAwYzI5OWJlMTNhNTcwODM5ZTEwOWE2YjE3ZDZiNWRmYzk4NTJjNTZmODQ4N2EzNGNjNWM2ZGMzNTBlYjY0Ng=='
)


class ProjectParam(ProjectParamBase):
    pass


class DefaultValue(DefaultValueBase):
    MAT_PLANT = "1600"   # 默认工厂
    MAT_PLANNER = "haida"   # 默认计划员
    MAT_LOCATION = "1600"  # 默认车间
 
#################################################################################
# ⬇️项目可复用逻辑
#################################################################################
sap_url1 = 'http://192.168.201.2:8000/zrestful_test2?sap-client=800'  # 库存
sap_url2 = 'http://192.168.201.2:8000/zrestful_plan?sap-client=800'  # 计划
werks = "1600"
sap_username = 'T058'
sap_password = '123456'
# 创建requests会话
sap_session = get_session(allowed_methods=["GET", "POST"])
# 添加Basic认证
add_basic_auth_requests(sap_session, sap_username, sap_password)


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
        console_log.info(f"POST请求成功，状态码：{response.status_code}，响应内容：{response_json}")
    else:
        console_log.error(f"POST请求失败，状态码：{response.status_code}，响应内容：{response.text}")
    return {
        'status_code': response.status_code,
        'response_text': response.text,
        'response_json': response_json
    }


#################################################################################
# ⬇️定时任务设置
#################################################################################
schedule_task_hour = '13,14,15,16,17,18,19,20,21,22,23'#'6,8,10,12,14,16'
schedule_task_minute = '0,5,10,15,20,25,30,35,40,45,50,55'#'55'


@cron_task(hour=schedule_task_hour, minute=f"{schedule_task_minute}")
async def refresh_stock(dbs: str = None):
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    db: 对哪些账套生效，多个账套用逗号分隔
    """
    console_log.info("开始执行刷新库存任务")
    dbs = dbs or ProjectParam.SCHEDULED_DBS
    response = None
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        response = sap_session.get(url=f"{sap_url1}", headers={'interface': 'stock', 'werks': werks})
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
        stock['itemno'] = DefaultValue.ITEMNO
        stock_data = stock.to_dict(orient='records')

        delete_result = await db_delete(db_names=dbs, model_or_tablename='t_supply', filter_string=f"`Type`='ST'")
        write_result = await db_write(db_names=dbs, model_or_tablename='t_supply', data_list=stock_data)
        console_log.info(f"刷新库存任务执行完成，账套：{dbs}")
        response = standard_response(message=f"刷新库存任务执行完成，账套：{dbs}")
        
    except Exception as e:
        console_log.error(f"刷新库存任务执行失败: {str(e)}")
        response = standard_response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, success=0, message=f"刷新库存任务执行失败: {str(e)}")
    return response


@cron_task(hour=23, minute=50)
async def push_weekpr_to_srm():
    # 推送周要货计划到SRM
    pr_data = await ApsBaseAction.get_dategrouped_pr()
    file_log.info(f"从账套{MYAPS_MAIN_DB}获取到周要货计划：\n{pr_data}")


@cron_task(day=1, hour=0, minute=5)
async def push_seasonpr_to_srm():
    # 每月初推送季度要货计划到SRM
    # 生成下三个月的月底日期列表
    date_list = [
        (datetime.now().replace(day=1) + relativedelta(months=i + 1) - relativedelta(days=1)).strftime('%Y-%m-%d')
        for i in range(3)
    ]
    pr_data = await ApsBaseAction.get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=90, groupdates=','.join(date_list))
    file_log.info(f"从账套{MYAPS_MAIN_DB}获取到季度要货计划：\n{pr_data}")

  
#################################################################################
# ⬇️数据库事件处理
#################################################################################

class ApsAction(ApsBaseAction):

    @classmethod
    async def press_release_button(cls, pl_data: dict):
        try:
            supplymo_detaildata = cls._get_supplymo_detaildata(pl_data['supplyno'])
            start_datetime: str = supplymo_detaildata['dt_ordstart'].split('T')[0]
            end_datetime: str = supplymo_detaildata['dt_ordend'].split('T')[0]
            orderwc: list = supplymo_detaildata['orderwc']

            data = {
                "WERKS": werks,  # 工厂
                "MATNR": pl_data['materialno'],
                "AUART": "ZP01",  # 订单类型
                "VERID": "SAP",    # 生产版本
                "GSTRP": start_datetime,  # 基本开始日期
                "GLTRP": end_datetime,  # 基本完成日期
                "GAMNG": pl_data['avail_qty'],  # 总订单数量
                "WEMPF": "SAP",  # 产线代码
                "BACKUP1": ','.join([i['workcenter'] for i in orderwc])
            }

            sap_response = await sap_post(url=sap_url2, session=sap_session, interface_id="ZPP_PLAN_ORD_CREATE", data=data)
            sap_response_json = sap_response['response_json']
            sap_mo_data = sap_response_json['BODY'][0]
            
            if sap_mo_data['STATUS'] == 'S':
                cls._pl_release_success(plno=pl_data['supplyno'], mono=sap_mo_data['AUFNR'], msg=sap_mo_data['MESSAGE'], msg_from='ERP')
            else:
                cls._pl_release_failed(plno=pl_data['supplyno'], to_status=pl_data.get('status', 'CRE'), msg=sap_mo_data['MESSAGE'], msg_from='ERP')
        except Exception as e:
            cls._pl_release_failed(plno=pl_data['supplyno'], to_status=pl_data.get('status', 'CRE'), msg=str(e), msg_from='API')

