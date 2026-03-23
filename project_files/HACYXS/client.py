"""
淮安超越橡塑项目文件
需要 ERP 推送的数据：
- 各种主数据
- 销售订单SO 
- 审批好的新 PO 及后续执行情况
- 报工数据
"""
from config.settings import MYAPS_DB_SET, MYAPS_MAIN_DB, THIS_BASE_URL, SCHEDULER_HOUR, SCHEDULER_MINUTE
from .._base import (
    get_scheduler_minute, cron_task, filelog_normal, filelog_error, console_log, CACHE_JSON,
    ApsHelpers, get_session, db_delete, db_bupsert, db_query
)

# 导入统一日志配置（用于直接使用）
# from globalobjects import logger as log_config

from apps.data_opt.components.yonyou_tplus import TplusConnection, BaseConnection, MoPushModel

#################################################################################
# ⬇️ 项目对象及参数
#################################################################################
REMAIN_NATIVE_SUPPLYNO = True   # 本项目需要推送 MO 前后关系，所以必须保留原生供应号，否则会导致关系断开

SESSION = get_session()

tplus_conn = TplusConnection()
# tplus_conn.auth()

#################################################################################
# ⬇️ 项目可复用逻辑
#################################################################################

def refresh_stock():
    stock_data = tplus_conn.pull_stock()
    if stock_data:
        ApsHelpers.refresh_stock(stock_data)


# def push_pr(supplyno: str):
#     pr_query = db_query(db_name=MYAPS_MAIN_DB, model_or_tablename='t_supply', filter_string=f"`Type`='PR' AND `Status` IN ('NEW','CRE')")
#     if pr_query['success']:
#         pr_list = pr_query['data']
#         tplus_conn.push_into_target(target_name='pr', push_data=pr_list)
#################################################################################
# ⬇️ 定时任务
#################################################################################
@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute())
def task_refresh_stock():
    refresh_stock()


@cron_task(hour=SCHEDULER_HOUR, minute=get_scheduler_minute(1))
def task_confirm_workreport():
    ApsHelpers.confirm_workreport()

#################################################################################
# ⬇️ 数据库事件
#################################################################################

def on_pl_status_a2e(supplyno_or_data: str | dict):
    if isinstance(supplyno_or_data, str):
        supplyno = supplyno_or_data
    elif isinstance(supplyno_or_data, dict):
        supplyno = supplyno_or_data['supplyno']
    tplus_conn.create_mo(supplyno=supplyno, remain_native_supplyno=REMAIN_NATIVE_SUPPLYNO)


def on_pr_created(pr_data_list: list[dict]):

    # if isinstance(supplyno_or_data, str):
    #     supplyno = supplyno_or_data
    # elif isinstance(supplyno_or_data, dict):
    #     supplyno = supplyno_or_data['supplyno']
    # tplus_conn.create_pr(supplyno=supplyno)
    pass
