"""江阴海达橡塑"""

import requests, uuid, asyncio#, logging#, os, atexit
import pandas as pd
from datetime import datetime

from fastapi import status
from dateutil.relativedelta import relativedelta


from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR
from .._base import (
    get_scheduler_minute,
    ApsStaticFunctions, filelog_error, filelog_normal, console_log, standard_response, get_session,
    cron_task, add_basic_auth_requests, db_delete, db_bupsert, db_query, CACHE_JSON, pdv
)


#################################################################################
# ⬇️对象及项目参数
#################################################################################
hap_conn = None

erp = CACHE_JSON.get("erp", {})
sap_url1 = erp.get("base_url", "") + '/zrestful_test2?sap-client=800'  # 库存
sap_url2 = erp.get("base_url", "") + '/zrestful_plan?sap-client=' + erp.get("sap-client")  # 计划
werks = erp.get("werks", "")
sap_username = erp.get("username", "")
sap_password = erp.get("password", "")
# 创建requests会话
sap_session = get_session(allowed_methods=["GET", "POST"])
# 添加Basic认证
add_basic_auth_requests(sap_session, sap_username, sap_password)

mes = CACHE_JSON.get("mes", {})
mes_url = mes.get("base_url", "")


srm = CACHE_JSON.get("srm", {})
srm_url = srm.get("base_url", "")
srm_headers = {
    "Authorization": srm.get("Authorization", ""),
    "Content-Type": "application/json",
}
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
    })

    response_json = {}
    if response.status_code == status.HTTP_200_OK:
        response_json = response.json()
        filelog_normal.info(f"✅ POST请求成功，状态码：{response.status_code}，响应内容：{response_json}")
    else:
        filelog_error.error(f"🚫 POST请求失败，状态码：{response.status_code}，响应内容：{response.text}")
    return {
        'status_code': response.status_code,
        'response_text': response.text,
        'response_json': response_json
    }


def refresh_stock(dbs: str = None):
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    db: 对哪些账套生效，多个账套用逗号分隔
    """
    filelog_normal.info("⏰ 开始执行刷新库存任务")
    dbs = dbs or MYAPS_DB_SET
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mo_complete_data = requests.get(url=f"{THIS_BASE_URL}/api/v_supply_complete?db_name=hdtest").json().get('data')
    mto_vir_st = None
    if mo_complete_data:
        df_mo_complete = pd.DataFrame(mo_complete_data)
        mto_vir_st = (df_mo_complete[df_mo_complete['category'] == 'MTO']
                [['materialno', 'vendorno', 'finalopqty', 'category', 'avail_date']]
                .groupby('vendorno', as_index=False)
                .agg({
                    'finalopqty': 'sum',
                    'materialno': 'first',
                    'category': 'first',
                    'avail_date': 'first',
                }))
        mto_vir_st['supplyno'] = mto_vir_st['materialno'] + '-' + mto_vir_st['vendorno']
        mto_vir_st['type'] = 'ST'
        mto_vir_st['priority'] = 0
        mto_vir_st['status'] = 'NEW'
        mto_vir_st['dt_req'] = mto_vir_st['avail_date']
        mto_vir_st['create_date'] = now
        mto_vir_st['itemno'] = pdv.ITEMNO
        mto_vir_st.rename(columns={'finalopqty': 'avail_qty'}, inplace=True)

    try:
        sap_stock_response = sap_session.get(url=f"{sap_url1}", headers={'interface': 'stock', 'werks': werks})
        sap_st_data = sap_stock_response.json().get('data', [])
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

        if mto_vir_st is not None:
            stock_data_total = pd.concat([df_sap_st, mto_vir_st], axis=0, ignore_index=True)
        else:
            stock_data_total = df_sap_st
        stock_data_total.fillna('', inplace=True)

        refresh_result = requests.put(url=f"{THIS_BASE_URL}/api/t_supply/type/ST?db_name={dbs}", json=stock_data_total.to_dict(orient='records'))
        if refresh_result.json()['success']:
            filelog_normal.info(f"✅ 刷新库存任务执行完成，账套：{dbs}")
        else:
            filelog_error.error(f"🚫 刷新库存任务执行失败: {refresh_result.json()['message']}")
        sap_stock_response = standard_response(message=f"刷新库存任务执行完成，账套：{dbs}")
    except Exception as e:
        filelog_error.error(f"🚫 刷新库存任务执行失败: {str(e)}")
        sap_stock_response = standard_response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, success=0, message=f"刷新库存任务执行失败: {str(e)}")
    return sap_stock_response


def push_pr(period: int = 30, groupdates: List[str] | str = None):
    if groupdates:
        if isinstance(groupdates, list):
            groupdates = ','.join(groupdates)

    pr_data = ApsStaticFunctions._get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=period, field_map=srm_field_map, groupdates=groupdates)
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for item in pr_data:
        item["plant"] = "1000"
        item["bu_code"] = werks
        item["version"] = timestamp
    filelog_normal.info(f"推送要货计划到SRM：\n{pr_data}")
    response = requests.post(
        url=f"{srm_url}/jbl/service/execute/SRM_RECEIVE_PUSHED_DEMAND_PLAN_SERVICE",
        headers=srm_headers, json={"demand_plan": pr_data})
    if response.json().get("body", {}).get("status", "").lower() == "success":
        filelog_normal.info(f"推送要货计划到SRM成功")
    else:
        filelog_error.error(f"推送要货计划到SRM失败：\n{response.json()}")


#################################################################################
# ⬇️定时任务设置
#################################################################################

@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def refresh_stock_task():
    console_log.info(f"⏰ 开始执行刷新库存任务")
    refresh_stock()
    console_log.info(f"✅ 刷新库存任务执行完成")


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(2))
def confirm_workreport():
    """
    确认报工记录
    """
    filelog_normal.info("⏰ 开始执行确认报工记录任务")
    ApsStaticFunctions.confirm_workreport()
    console_log.info(f"✅ 确认报工记录任务执行完成")



@cron_task(hour=23, minute=50)
# @cron_task(hour="8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23", minute="0,5,10,15,20,25,30,35,40,45,50,55")
# @cron_task(hour="8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23", minute="0,10,20,30,40,50")
def push_weekpr_to_srm():
    # 推送周要货计划到SRM
    # pr_data = ApsStaticFunctions.get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=30, field_map=srm_field_map)
    # timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # for item in pr_data:
    #     item["plant"] = "1000"
    #     item["bu_code"] = werks
    #     item["version"] = timestamp
    # filelog_normal.info(f"推送周要货计划到SRM：\n{pr_data}")
    # response = requests.post(
    #     url=f"{srm_url}/jbl/service/execute/SRM_RECEIVE_PUSHED_DEMAND_PLAN_SERVICE",
    #     headers=srm_headers, json={"demand_plan": pr_data})
    # if response.json().get("body", {}).get("status", "").lower() == "success":
    #     filelog_normal.info(f"推送周要货计划到SRM：\n{pr_data}")
    # else:
    #     filelog_error.error(f"推送周要货计划到SRM失败：\n{response.json()}")
    console_log.info(f"⏰ 开始执行推送周要货计划到SRM任务")
    push_pr(period=30)



@cron_task(day=1, hour=0, minute=5)
def push_seasonpr_to_srm():
    # 每月初推送季度要货计划到SRM
    # 生成下三个月的月底日期列表
    console_log.info(f"⏰ 开始执行推送季度要货计划到SRM任务")
    date_list = [
        (datetime.now().replace(day=1) + relativedelta(months=i + 1) - relativedelta(days=1)).strftime('%Y-%m-%d')
        for i in range(3)
    ]
    push_pr(period=90, groupdates=date_list)
    # pr_data = ApsStaticFunctions.get_dategrouped_pr(db_name=MYAPS_MAIN_DB, period=90, groupdates=','.join(date_list), field_map=srm_field_map)
    # timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # for item in pr_data:
    #     item["plant"] = "1000"
    #     item["bu_code"] = werks
    #     item["version"] = timestamp
    # response = requests.post(
    #     url=f"{srm_url}/jbl/service/execute/SRM_RECEIVE_PUSHED_DEMAND_PLAN_SERVICE",
    #     headers=srm_headers, json={"demand_plan": pr_data})
    # if response.json().get("body", {}).get("status", "").lower() == "success":
    #     filelog_normal.info(f"推送季度要货计划到SRM：\n{pr_data}")
    # else:
    #     filelog_error.error(f"推送季度要货计划到SRM失败：\n{response.json()}  ")



#################################################################################
# ⬇️APS事件
#################################################################################

def onclick_release_button(supplyno: str):
    supplymo_detaildata = ApsStaticFunctions._get_supplymo_detaildata(supplyno=supplyno)
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
        sap_mo_data = sap_response_json['BODY'][0]
        
        if sap_mo_data['STATUS'] == 'S':
            ApsStaticFunctions._pl_release_success(plno=supplyno, mono=sap_mo_data['AUFNR'], msg=sap_mo_data['MESSAGE'], msg_from='ERP')
        else:
            ApsStaticFunctions._pl_release_failed(plno=supplyno, msg=sap_mo_data['MESSAGE'], msg_from='ERP')
    except Exception as e:
        ApsStaticFunctions._pl_release_failed(plno=supplyno, msg=str(e), msg_from='API')
