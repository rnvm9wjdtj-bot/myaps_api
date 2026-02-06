"""
淮安超越橡塑项目文件
"""
import requests, logging, os, asyncio
import pandas as pd
from datetime import datetime
from typing import Callable
from fastapi import status


from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, get_scheduler_minute,
    cron_task, filelog_normal, filelog_error, CACHE_JSON,
    ApsBaseAction, DataProcessor,
    filelog_normal, console_log, standard_response, get_session, 
    db_delete, db_bupsert, db_query
)

# 导入统一日志配置（用于直接使用）
from globalobjects import logger as log_config

from apps.data_opt.components import yonyou_tplus, hap


# 将 APS 原生的 supplyno 、demandno 等字段，直接推送到 T+ 中，作为单据编号
_USE_NATIVENO = True

#################################################################################
# ⬇️ 项目对象及参数
#################################################################################

session = get_session()
hap_conn = None

# hap_conn = hap.HapConnection()
# hap_conn.regist_worksheet(hap.get_maindata_worksheetinfo())


tplus_conn = yonyou_tplus.TplusConnection()
tplus_conn.auth()


#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################
def get_maindata_from_erp_to_hap():
    if not hap_conn:
        return
    # material = tplus_conn.pull_from_source(source_name='material')
    # hap_conn.worksheet('t_material').upsert(material)

    # workcenter = tplus_conn.pull_from_source(source_name='workcenter')
    # hap_conn.worksheet('t_workcenter').upsert(workcenter)

    bom = tplus_conn.pull_from_source(source_name='bom')      # 先拉BOM，顺便获取BOM CODES，以便后续获取工艺路线
    # hap_conn.worksheet('t_mat_wc_bom').upsert(bom)

    route = tplus_conn.pull_from_source(source_name='route')
    hap_conn.worksheet('t_mat_wc').upsert(route)


def refresh_stock():
    import pandas as pd
    from datetime import datetime
    
    # 获取当前时间并格式化为ddhhmm
    current_time = datetime.now()
    timestamp = current_time.strftime('%d%H%M')
    
    # 获取原始库存数据
    stock = tplus_conn.pull_from_source(source_name='stock')
    
    # 使用pandas进行数据汇总
    if stock:
        df = pd.DataFrame(stock)
        # 按materialno分组，avail_qty求和，其他字段取first
        grouped = df.groupby('materialno').agg(
            avail_qty=('avail_qty', 'sum'),
            matver=('matver', 'first'),
            itemno=('itemno', 'first'),
            type=('type', 'first'),
            category=('category', 'first'),
            priority=('priority', 'first'),
            status=('status', 'first'),
            create_date=('create_date', 'first'),
            avail_date=('avail_date', 'first'),
            dt_req=('dt_req', 'first'),
            avail_end_date=('avail_end_date', 'first'),
            batchno=('batchno', 'first'),
            vendorno=('vendorno', 'first'),
            partnerno=('partnerno', 'first'),
            partnername=('partnername', 'first'),
            free1=('free1', 'first'),
            free2=('free2', 'first'),
            free3=('free3', 'first'),
            memo=('memo', 'first')
        ).reset_index()
        # 生成supplyno字段为materialno@timestamp
        grouped['supplyno'] = grouped['materialno'] + '@' + timestamp
        # 转换为字典列表
        aggregated_stock = grouped.to_dict('records')
    else:
        aggregated_stock = []

    global session
    # 删除旧库存数据
    # delete_result = asyncio.run(db_delete(db_names=MYAPS_DB_SET, model_or_tablename='t_supply', filter_string=f"`Type`='ST'"))
    session.delete(url=f"{THIS_BASE_URL}/api/t_supply?db_name={MYAPS_DB_SET}&type=ST")
    # 插入汇总后的数据
    # bupsurt_result = asyncio.run(db_bupsert(db_names=MYAPS_DB_SET, model_or_tablename='t_supply', data_list=aggregated_stock))
    session.post(url=f"{THIS_BASE_URL}/api/t_supply?db_name={MYAPS_DB_SET}", json=aggregated_stock)

    return aggregated_stock


def push_pr():
    pr_query = db_query(db_name=MYAPS_MAIN_DB, model_or_tablename='t_supply', filter_string=f"`Type`='PR' AND `Status` IN ('NEW','CRE')")
    if pr_query['success']:
        pr_list = pr_query['data']
        tplus_conn.push_into_target(target_name='pr', push_data=pr_list, use_nativeno=_USE_NATIVENO)
#################################################################################
# ⬇️ 定时任务
#################################################################################
# @cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(-1))
def get_maindata_from_erp_to_hap_task(*args, **kwargs):
    console_log.info("⏰ 开始执行获取主数据定时任务")
    maindata = get_maindata_from_erp_to_hap()
    console_log.info("⏰ 获取主数据定时任务执行完成")


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def refresh_stock_task(*args, **kwargs):
    console_log.info("⏰ 开始执行刷新库存定时任务")
    stock = refresh_stock()
    console_log.info("⏰ 刷新库存定时任务执行完成")


# @cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(1))
def push_pr_task(*args, **kwargs):
    console_log.info("⏰ 开始执行推送请购单定时任务")
    pr = push_pr()
    console_log.info("⏰ 推送请购单定时任务执行完成")

#################################################################################
# ⬇️ 数据库事件
#################################################################################


class ApsAction(ApsBaseAction):

    @classmethod
    def click_release_button(cls, supplyno: str):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        🅰 supplyno: PL计划单编号
        """
        # 材料需求
        demand_list = ApsBaseAction._get_demand_datalist(demandno=supplyno)
        # PL及工序详情
        supplymo_detaildata = ApsBaseAction._get_supplymo_detaildata(supplyno=supplyno)
        supplymo_detaildata['demand_list'] = demand_list

        mo_push_response = tplus_conn.push_into_target(target_name='mo_single', push_data=supplymo_detaildata, use_nativeno=_USE_NATIVENO)
        mo_push_response_json = mo_push_response.json()

        if str(mo_push_response_json['code']) == '0': # 响应错误码为0，MO 创建成功
            # 从响应中提取 data
            response_data = mo_push_response_json['data']
            # 查询一下刚刚推送成功的 MO 在 T+ 中详情， 这是查询单个mo的接口
            tplus_mo_id = response_data['ID']
            
            try:
                mo_in_tplus = (tplus_conn.pull_from_source(source_name='mo_single', filter={"voucherID": tplus_mo_id}))[0]
                tplus_mo_code = mo_in_tplus['Code']
                # 从 T+ 中提取 MO 详情中的第一个详情记录的 ID 作为 _entryid
                tplus_mo_entryid = mo_in_tplus['ManufactureOrderDetails'][0]['ID'] 
                # 最后再更改工单信息，一定放在最后一步，否则如果变更工单号变更太早，前面若有用原生供应号查询都会失败
                a = cls._pl_release_success(plno=supplyno, msg=mo_push_response_json['message'], change_supplyno=not _USE_NATIVENO, msg_from='T+', mono=tplus_mo_code, _id=tplus_mo_id, _entryid=tplus_mo_entryid)

                # 审批接口，要在领料申请前批准
                b = tplus_conn.push_into_target(target_name='mo_approve', push_data={'voucherID': tplus_mo_id})
                # 推送领料申请
                c = cls.push_rs(mdlist_or_supplyno=demand_list, tplus_mo_id=tplus_mo_id, tplus_mo_entryid=tplus_mo_entryid)

            except Exception as e:
                tplus_mo_entryid = None
                filelog_error.error(f"Error extracting entry ID from T+ MO: {e}")

        else:
            a = cls._pl_release_failed(plno=supplyno, msg=mo_push_response_json['message'], msg_from='T+')
            

    @classmethod
    def push_rs(cls, mdlist_or_supplyno: str | list[dict], tplus_mo_id: str, tplus_mo_entryid: str):
        """
        推送领料申请到T+
        🅰 mdlist_or_supplyno: 材料需求列表或工单号
        🅰 tplus_mo_id: T+ 中 MO id
        🅰 tplus_mo_entryid: T+ 中 MO 详情记录id
        """
        if isinstance(mdlist_or_supplyno, str):
            rs_data = ApsBaseAction._get_demand_datalist(demandno=mdlist_or_supplyno)     # 从 APS 查询 RS 领料数据，以工单号 related_supplyno 为依据查找
            demandno = mdlist_or_supplyno
        else:
            rs_data = mdlist_or_supplyno
            demandno = rs_data[0]['demandno']
        rs_push_response = tplus_conn.push_into_target(target_name='rs', push_data=rs_data, tplus_mo_id=tplus_mo_id, tplus_mo_entryid=tplus_mo_entryid, use_nativeno=_USE_NATIVENO)
        rs_push_response_json = rs_push_response.json()
        if str(rs_push_response_json['code']) == '0': # 创建成功
            a = cls._rs_push_success(rsno=demandno, msg=rs_push_response_json['message'], msg_from='T+', _code=rs_push_response_json['data'].get('Code'), _id=rs_push_response_json['data'].get('ID'))
        else:
            filelog_error.error(f"❌ 领料申请推送失败，对应工单：{demandno}，错误信息：{rs_push_response_json['message']}")
            a = cls._rs_push_failed(rsno=demandno, msg=rs_push_response_json['message'], msg_from='T+')


    @classmethod
    def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当工单管理的状态变为'CMP'（完成）时该方法将被自动调用
        🅰 mono: MO号
        """
        pass