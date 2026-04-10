"""江阴海达橡塑"""

import requests, uuid, asyncio#, logging#, os, atexit
import pandas as pd
from datetime import datetime
from typing import List

from fastapi import status
from dateutil.relativedelta import relativedelta


from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR
from .._base import (
    get_scheduler_minute,
    ApsHelpers, CLIENT_LOGGER, standard_response, get_session,
    cron_task, add_basic_auth_requests, db_delete, db_bupsert, db_query, PROJECT_JSON_FILE, pdv
)


#################################################################################
# ⬇️对象及项目参数
#################################################################################
erp = PROJECT_JSON_FILE.get("erp", {})
sap_url1 = erp.get("base_url", "") + '/zrestful_test2?sap-client=800'  # 库存
sap_url2 = erp.get("base_url", "") + '/zrestful_plan?sap-client=' + erp.get("sap-client")  # 计划
werks = erp.get("werks", "")
sap_username = erp.get("username", "")
sap_password = erp.get("password", "")
# 创建requests会话
sap_session = get_session(allowed_methods=["GET", "POST"])
# 添加Basic认证
add_basic_auth_requests(sap_session, sap_username, sap_password)

mes = PROJECT_JSON_FILE.get("mes", {})
mes_url = mes.get("base_url", "")


srm = PROJECT_JSON_FILE.get("srm", {})
srm_url = srm.get("base_url", "")
srm_headers = {
    "Authorization": srm.get("Authorization", ""),
    "Content-Type": "application/json",
}
srm_session = get_session()
srm_session.headers.update(srm_headers)
srm_field_map = {
    "materialno": "material_no", "description": "description", "size": "size",
    "type": "type", "abc": "abc", "planner": "planner", "datestr": "datestr",
    "物料来源": "name", "首期库存": "stock_qty", "累计盈余": "cumulative_balance",
    "期间合计需求": "total_demand", "期间合计供应": "total_supply", "期间盈余": "daily_balance",
    "期间": "original_datestr", "期间要货数": "current_order_quantity",
    "期初盈余": "initial_surplus", "期末盈余": "last_surplus", "要求交期": "datestr",
}

#################################################################################
# ⬇️项目可复用逻辑
#################################################################################

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
    }, timeout=(15, 60))

    response_json = {}
    if response.status_code == status.HTTP_200_OK:
        try:
            response_json = response.json()
            CLIENT_LOGGER.success("POST请求", f"状态码{response.status_code}", f"响应{response_json}")
        except Exception as e:
            CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"解析JSON失败: {str(e)}")
            CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"响应文本: {response.text}")
    else:
        CLIENT_LOGGER.fail("POST请求", f"状态码{response.status_code}", f"响应{response.text}")
    return {
        'status_code': response.status_code,
        'response_text': response.text,
        'response_json': response_json
    }


def refresh_stock(dbs: str=MYAPS_DB_SET):
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    db: 对哪些账套生效，多个账套用逗号分隔
    """
    def get_sap_stock_data():
        """
        从SAP系统获取1600厂全部库存数据
        """
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            sap_stock_response = sap_session.get(url=f"{sap_url1}", headers={'interface': 'stock', 'werks': werks}, timeout=(15, 60)).json()
            sap_st_data = sap_stock_response.get('data', [])
            df_sap_st = pd.DataFrame(sap_st_data)
            df_sap_st = df_sap_st.astype({
                'werks': 'str',
                'matnr': 'str',
                'lgort': 'str',
                'labst': 'int32',
                'labst2': 'int32',
                'charg': 'str'
            })
            df_sap_st['avail_qty'] = df_sap_st['labst'] + df_sap_st['labst2']
            df_sap_st['supplyno'] = df_sap_st['matnr'] + '-' + df_sap_st['werks'] # 注意不要用f string，否则supplyno会变成所有料号的超长字符串
            df_sap_st['type'] = 'ST'
            df_sap_st['priority'] = 0
            df_sap_st['avail_date'] = now
            df_sap_st['dt_req'] = now
            df_sap_st['status'] = 'NEW'
            df_sap_st['category'] = ''
            df_sap_st['create_date'] = now
            df_sap_st = (df_sap_st
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
            df_sap_st = df_sap_st.rename(columns={
                'matnr': 'materialno',
            })
            df_sap_st['itemno'] = pdv.ITEMNO
        except Exception as e:
            CLIENT_LOGGER.fail("SAP库存获取", "", str(e))
            df_sap_st = None
        return df_sap_st

    CLIENT_LOGGER.start("刷新库存任务")
    mto_vir_st = ApsHelpers.mto_workreport_to_virtual_stock()
    df_sap_st = get_sap_stock_data()

    if mto_vir_st is not None:
        stock_data_total = pd.concat([df_sap_st, mto_vir_st], axis=0, ignore_index=True)
    else:
        stock_data_total = df_sap_st
    
    # if stock_data_total is not None:
    stock_data_total.fillna('', inplace=True)
    ApsHelpers.refresh_supply(stock_data_total.to_dict(orient='records'), dbs=dbs)



def push_pr(period: int = 30, groupdates: List[str] | str = None):
    if groupdates:
        if isinstance(groupdates, list):
            groupdates = ','.join(groupdates)

    pr_data = ApsHelpers.get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=period, field_map=srm_field_map, groupdates=groupdates)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for item in pr_data:
        item["plant"] = "1000"
        item["bu_code"] = werks
        item["version"] = timestamp
    CLIENT_LOGGER.start(f"推送要货计划到SRM：{pr_data}")
    response = srm_session.post(
        url=f"{srm_url}/jbl/service/execute/SRM_RECEIVE_PUSHED_DEMAND_PLAN_SERVICE",
        json={"demand_plan": pr_data})
    if response.json().get("body", {}).get("status", "").lower() == "success":
        CLIENT_LOGGER.success(f"推送要货计划到SRM")
    else:
        CLIENT_LOGGER.fail(f"推送要货计划到SRM", response.text)


def push_weekpr_to_srm():
    CLIENT_LOGGER.start("推送周要货计划到SRM任务")
    push_pr(period=30)
    CLIENT_LOGGER.success("推送周要货计划到SRM任务", "", "执行完成")


def push_monthpr_to_srm():
    CLIENT_LOGGER.start("推送月度要货计划到SRM任务")
    date_list = [
        (datetime.now().replace(day=1) + relativedelta(months=i + 1) - relativedelta(days=1)).strftime('%Y-%m-%d')
        for i in range(3)
    ]
    push_pr(period=90, groupdates=date_list)
    CLIENT_LOGGER.success("推送月度要货计划到SRM任务", "", "执行完成")
#################################################################################
# ⬇️定时任务设置
#################################################################################

@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def task_refresh_stock():
    refresh_stock()


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(2))
def task_confirm_workreport():
    ApsHelpers.confirm_workreport()


@cron_task(hour=23, minute=59)  # 每天23:59执行一次，需须在23:55拉取库存和确认报工之后
# @cron_task(hour="8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23", minute="0,5,10,15,20,25,30,35,40,45,50,55")
def task_push_weekpr_to_srm():
    push_weekpr_to_srm()


@cron_task(day=1, hour=0, minute=5)
def task_push_seasonpr_to_srm():
    push_monthpr_to_srm()


#################################################################################
# ⬇️APS事件
#################################################################################

def handle_pl_status_a2e(supplyno_or_data: str | dict):
    if isinstance(supplyno_or_data, str):
        supplyno = supplyno_or_data
    else:
        supplyno = supplyno_or_data['supplyno']

    supplymo_detaildata = ApsHelpers.get_supplymo_detaildata(supplyno=supplyno)
    try:
        start_datetime: str = supplymo_detaildata['dt_ordstart'].split(" ")[0]
        end_datetime: str = supplymo_detaildata['dt_ordend'].split(" ")[0]
        orderwc: list = supplymo_detaildata['orderwc']

        data = {
            "WERKS": werks,  # 工厂
            "MATNR": supplymo_detaildata['materialno'],
            "AUART": "ZP01",  # 订单类型
            "VERID": "SAP",    # 生产版本
            "GSTRP": start_datetime,  # 基本开始日期
            "GLTRP": end_datetime,  # 基本完成日期
            "GAMNG": supplymo_detaildata['avail_qty'],  # 总订单数量
            "WEMPF": "SAP",  # 产线代码
            "BACKUP1": ','.join([i['workcenter'] for i in orderwc])
        }

        sap_response = sap_post(url=sap_url2, session=sap_session, interface_id="ZPP_PLAN_ORD_CREATE", data=data)
        sap_response_json = sap_response['response_json']
        
        try:
            if 'BODY' in sap_response_json and len(sap_response_json['BODY']) > 0:
                sap_mo_data = sap_response_json['BODY'][0]
                
                if sap_mo_data.get('STATUS') == 'S':
                    ApsHelpers.pl_release_success(native_plno=supplyno, mono=sap_mo_data.get('AUFNR'), msg=sap_mo_data.get('MESSAGE'), msg_from='ERP')
                else:
                    ApsHelpers.pl_release_failed(native_plno=supplyno, msg=sap_mo_data.get('MESSAGE', '未知错误'), push_data=data, msg_from='ERP')
            else:
                # 处理响应格式不正确的情况
                ApsHelpers.pl_release_failed(native_plno=supplyno, msg=f"响应格式不正确: {sap_response['response_text']}", push_data=data, msg_from='ERP')
        except Exception as e:
            # 处理其他异常
            ApsHelpers.pl_release_failed(native_plno=supplyno, msg=f"处理响应失败: {str(e)}", push_data=data, msg_from='ERP')
    except requests.exceptions.Timeout as e:
        # 处理请求超时，按推送失败处理
        ApsHelpers.pl_release_failed(native_plno=supplyno, msg=f"请求超时: {str(e)}", push_data=data, msg_from='ERP')
    except Exception as e:
        ApsHelpers.pl_release_failed(native_plno=supplyno, msg=str(e), push_data=data, msg_from='API')

