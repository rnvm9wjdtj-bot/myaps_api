"""
淮安超越橡塑项目文件
"""
# import requests, logging, os, asyncio
# import pandas as pd
# from datetime import datetime
# from typing import Callable
# from fastapi import status


from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, filelog_normal, filelog_error, console_log, CACHE_JSON,
    ApsHelpers, get_session, db_delete, db_bupsert, db_query
)

# 导入统一日志配置（用于直接使用）
from globalobjects import logger as log_config

from apps.data_opt.components.yonyou_tplus import TplusConnection, BaseConnection


#################################################################################
# ⬇️ 项目对象及参数
#################################################################################

SESSION = get_session()

tplus_conn = TplusConnection()
tplus_conn.auth()


#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################


def refresh_stock():
    import pandas as pd
    from datetime import datetime
    
    # 获取当前时间并格式化为ddhhmm
    current_time = datetime.now()
    timestamp = current_time.strftime('%d%H%M')
    
    # 获取原始库存数据
    stock = tplus_conn.pull_stock()
    
    # 使用pandas进行数据汇总
    if stock:
        df = pd.DataFrame(stock)
        # 按materialno分组，avail_qty求和，其他字段取first
        grouped = df.groupby('materialno').agg(
            avail_qty=('avail_qty', 'sum'), matver=('matver', 'first'), itemno=('itemno', 'first'),
            type=('type', 'first'), category=('category', 'first'), priority=('priority', 'first'),
            status=('status', 'first'), create_date=('create_date', 'first'), avail_date=('avail_date', 'first'),
            dt_req=('dt_req', 'first'), avail_end_date=('avail_end_date', 'first'), batchno=('batchno', 'first'),
            vendorno=('vendorno', 'first'), partnerno=('partnerno', 'first'), partnername=('partnername', 'first'),
            free1=('free1', 'first'), free2=('free2', 'first'), free3=('free3', 'first'), memo=('memo', 'first')
        ).reset_index()
        # 生成supplyno字段为materialno@timestamp
        grouped['supplyno'] = grouped['materialno'] + '@' + timestamp
        # 转换为字典列表
        aggregated_stock = grouped.to_dict('records')
    else:
        aggregated_stock = []

    ApsHelpers.refresh_stock(aggregated_stock)



def push_pr():
    pr_query = db_query(db_name=MYAPS_MAIN_DB, model_or_tablename='t_supply', filter_string=f"`Type`='PR' AND `Status` IN ('NEW','CRE')")
    if pr_query['success']:
        pr_list = pr_query['data']
        tplus_conn.push_into_target(target_name='pr', push_data=pr_list)
#################################################################################
# ⬇️ 定时任务
#################################################################################

@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def task_refresh_stock(*args, **kwargs):
    console_log.info("⏰ 开始执行刷新库存定时任务")
    stock = refresh_stock()
    console_log.info("⏰ 刷新库存定时任务执行完成")



@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(2))
def task_confirm_workreport():
    """
    确认报工记录
    """
    console_log.info("⏰ 开始执行确认报工记录任务")
    ApsHelpers.confirm_workreport()
    console_log.info("⏰ 确认报工记录任务执行完成")
#################################################################################
# ⬇️ 数据库事件
#################################################################################

def onclick_mo_release_button(supplyno: str):
    tplus_conn.create_mo(supplyno=supplyno)

