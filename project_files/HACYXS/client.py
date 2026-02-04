"""
淮安超越橡塑项目文件
"""

import requests, logging, os#, atexit
import pandas as pd
from datetime import datetime
from typing import Callable
from fastapi import status



from .._base import (
    MYAPS_DB_SET, MYAPS_MAIN_DB,
    cron_task, filelog_normal, filelog_error, CACHE_JSON,
    ApsBaseAction, DataProcessor,
    filelog_normal, console_log, standard_response, get_session, 
    db_delete, db_bupsert, db_query
)

from apps.data_opt.components import yonyou_tplus, hap



#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
# file_logger = file_timed_logger.setup_logging(__name__, log_filename='project.log')


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
async def get_maindata_from_erp_to_hap():
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

    pass


async def refresh_stock():
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
    # 删除旧库存数据
    delete_result = await db_delete(db_names=MYAPS_DB_SET, model_or_tablename='t_supply', filter_string=f"`Type`='ST'")
    # 插入汇总后的数据
    bupsurt_result = await db_bupsert(db_names=MYAPS_DB_SET, model_or_tablename='t_supply', data_list=aggregated_stock)
    return aggregated_stock

#################################################################################
# ⬇️ 定时任务
#################################################################################
# @cron_task(hour="8,9,10,11,12,13,14,15,16,17,18,19,20,21,22",minute="0,5,10,15,20,25,30,35,40,45,50,55")
# @cron_task(hour="8,10,12,14,16",minute="55")
async def get_maindata_from_erp_to_hap_task(*args, **kwargs):
    console_log.info("⏰ 开始执行获取主数据定时任务")
    await get_maindata_from_erp_to_hap()
    console_log.info("⏰ 获取主数据定时任务执行完成")


# @cron_task(hour="8,9,10,11,12,13,14,15,16,17,18,19,20,21,22",minute="0,5,10,15,20,25,30,35,40,45,50,55")
@cron_task(hour="8,10,12,14,16",minute="55")
async def refresh_stock_task(*args, **kwargs):
    console_log.info("⏰ 开始执行刷新库存定时任务")
    stock = await refresh_stock()
    console_log.info("⏰ 刷新库存定时任务执行完成")


#################################################################################
# ⬇️ 数据库事件
#################################################################################


_REMAIN_SUPPLYNO = True

class ApsAction(ApsBaseAction):

    @classmethod
    def click_release_button(cls, supplyno: str):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        🅰 supplyno: PL计划单编号
        """
        supplymo_detaildata = ApsBaseAction._get_supplymo_detaildata(supplyno=supplyno)

        mo_push_response = tplus_conn.push_into_target(target_name='mo_single', push_data=supplymo_detaildata, mo_remain_supplyno=_REMAIN_SUPPLYNO)
        mo_push_response_json = mo_push_response.json()

        if mo_push_response_json['code'] == 0: # 响应错误码为0，MO 创建成功
            # 从响应中提取 data
            response_data = mo_push_response_json['data']
            # 查询一下刚刚推送成功的 MO 在 T+ 中详情， 这是查询单个mo的接口
            tplus_mo_id = response_data['ID']
            
            try:
                mo_in_tplus = (tplus_conn.pull_from_source(source_name='mo_single', filter={"voucherID": tplus_mo_id}))[0]
                tplus_mo_code = mo_in_tplus['Code']
                # 从 T+ 中提取 MO 详情中的第一个详情记录的 ID 作为 _entryid
                tplus_mo_entryid = mo_in_tplus['ManufactureOrderDetails'][0]['ID']
            except Exception as e:
                tplus_mo_entryid = None
                filelog_error.error(f"Error extracting entry ID from T+ MO: {e}") 
               
            # 推送 领料申请 到 T+
            rs_data = ApsBaseAction._get_demand_datalist(demandno=supplyno)     # 从 APS 查询 RS 领料数据，以工单号 supplyno 为依据查找
            rs_push_response = tplus_conn.push_into_target(target_name='rs', push_data=rs_data, tplus_mo_id=tplus_mo_id, tplus_mo_entryid=tplus_mo_entryid)
            rs_push_response_json = rs_push_response.json()
            if str(rs_push_response_json['code']) == '0': # 创建成功
                # 同步调用 _rs_push_success 方法
                import asyncio
                asyncio.run(cls._rs_push_success(rsno=supplyno, msg=rs_push_response_json['message'], msg_from='T+', _code=rs_push_response_json['data'].get('Code'), _id=rs_push_response_json['data'].get('ID')))
            else:
                filelog_error.error(f"❌ 领料申请推送失败，对应工单：{supplyno}，错误信息：{rs_push_response_json['message']}")
                # 同步调用 _rs_push_failed 方法
                import asyncio
                a = asyncio.run(cls._rs_push_failed(rsno=supplyno, msg=rs_push_response_json['message'], msg_from='T+'))

            # 最后再更改工单信息，一定放在最后一步，否则如果变更工单号变更太早，前面所有相关查询都会失败
            # 同步调用 _pl_release_success 方法
            import asyncio
            a = asyncio.run(cls._pl_release_success(plno=supplyno, msg=mo_push_response_json['message'], change_supplyno=not _REMAIN_SUPPLYNO, msg_from='T+', mono=tplus_mo_code, _id=tplus_mo_id, _entryid=tplus_mo_entryid))
            # 审批工单
            a = tplus_conn.push_into_target(target_name='mo_approve', push_data={'voucherID': tplus_mo_id})
        else:
            # 同步调用 _pl_release_failed 方法
            a = cls._pl_release_failed(plno=supplyno, msg=mo_push_response_json['message'], msg_from='T+')
            

    @classmethod
    def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当工单管理的状态变为'CMP'（完成）时该方法将被自动调用
        🅰 mono: MO号
        """
        pass