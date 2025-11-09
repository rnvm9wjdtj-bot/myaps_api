import os, requests, logging, atexit, datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from config import uservar as uv


effective_db = ['hdso', 'hdfc'] # 主账套放第一位
main_db = effective_db[0]
sap_url = 'http://192.168.201.2:8000'
this_url = 'http://localhost:8000'
werks = '1600'

# 创建requests会话
erp_session = requests.Session()
this_api_session = requests.Session()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

#################################################################################
# 定义需要用到的逻辑

async def refresh_stock(db_name: str | None = None): 
    """
    刷新库存，先清空supply中类型为ST的数据，再从ERP同步1600厂全部库存数据
    db_name: 账套名称，默认刷新所有账套
    """
    logger.info("开始执行刷新库存任务")
    try:
        response = erp_session.get(url=f"{sap_url}/zrestful_test2?sap-client=800", headers={'interface': 'stock', 'werks': werks})
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
        stock['supplyno'] = stock['werks'] + '-' + stock['matnr']
        stock['type'] = 'ST'
        stock['priority'] = uv.default_priority
        stock['avail_date'] = datetime.datetime.now().strftime('%Y-%m-%d')
        stock['dt_req'] = datetime.datetime.now().strftime('%Y-%m-%d')
        stock = (stock
                        .groupby(['supplyno'], as_index=False)
                        .agg({
                            'matnr': 'first',
                            'avail_qty': 'sum',
                            'type': 'first',
                            'avail_date': 'first',
                            'dt_req': 'first',
                            'priority': 'first',
                        })) 
        stock = stock.rename(columns={
            'matnr': 'materialno',
        })
        stock_data = stock.to_dict(orient='records')
        if db_name is None:
            for db in effective_db:
                await this_api_session.delete(f"{this_url}/api/t_supply?db_name={db}", data='ST')
                await this_api_session.post(f"{this_url}/api/t_supply?db_name={db}", json=stock_data)
                logger.info(f"刷新库存任务执行完成，账套：{db}")
        else:
            await this_api_session.delete(f"{this_url}/api/t_supply?db_name={db_name}", data='ST')
            await this_api_session.post(f"{this_url}/api/t_supply?db_name={db_name}", json=stock_data)
            logger.info(f"刷新库存任务执行完成，账套：{db_name}")
    except Exception as e:
        logger.error(f"刷新库存任务执行失败: {str(e)}")


async def push_pl_to_sap(pl_data: dict):
    """
    以数据库binlog为触发条件，将主账套中需要转MO的PL推送到SAP
    """
    try:
        headers = {
            "DEST_SYSTEM": "SAP",
            "INTF_ID": "ZPP_PLAN_ORD_CREATE",
            "SRC_SYSTEM": "APS",
            "SRC_SYSTEM": "APS",
        }
        data = {
            "CY_SEQNR": pl_data['SupplyNo'],  # APS单号
            "WERKS": werks,  # 工厂
            "MATNR": pl_data['MaterialNo'],
            "AUART": "PL",  # 订单类型
            "VERID": "",    # 生产版本
            "GSTRP": pl_data['dt_req'],  # 基本开始日期
            "GLTRP": pl_data['Avail_Date'],  # 基本完成日期
            "GAMNG": pl_data['Avail_Qty'],  # 总订单数量
            "FEVOR": "",  # 生产主管
            "WEMPF": ""  # 产线代码
        }
        erp_session.post(url=f"{sap_url}/zrestful_plan?sap-client=500", json=pl_data, headers=headers)

        logger.info(f"推送计划任务执行完成，账套：{main_db}")
    except Exception as e:
        logger.error(f"推送计划任务执行失败: {str(e)}")
#################################################################################

# 配置APScheduler的执行器
executors = {
    'default': ThreadPoolExecutor(10)
}

# 创建后台调度器实例
scheduler = BackgroundScheduler(executors=executors, timezone='Asia/Shanghai')

def init_scheduler():
    """初始化调度器并添加定时任务"""
    try:
        # 添加库存获取定时任务 - 每天的奇数整点执行(1,3,5,7,9,11,13,15,17,19,21,23点)
        scheduler.add_job(
            func=refresh_stock,
            trigger='cron',
            minute=0,
            hour='1,3,5,7,9,11,13,15,17,19,21,23',
            id='refresh_stock',
            replace_existing=True
        )
        logger.info("调度器初始化完成，已添加定时任务")
    except Exception as e:
        logger.error(f"调度器初始化失败: {str(e)}")


def start_scheduler():
    """启动调度器"""
    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("调度器已启动")
        else:
            logger.info("调度器已经在运行中")
    except Exception as e:
        logger.error(f"调度器启动失败: {str(e)}")


def shutdown_scheduler():
    """关闭调度器"""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("调度器已关闭")
        else:
            logger.info("调度器已经关闭")
    except Exception as e:
        logger.error(f"调度器关闭失败: {str(e)}")

# 在模块加载时初始化并启动调度器
def initialize_and_start_scheduler():
    """初始化并启动调度器，这是模块的主要入口点"""
    init_scheduler()
    start_scheduler()
    # 注册退出处理函数，确保程序退出时调度器被正确关闭
    atexit.register(shutdown_scheduler)

# 开启定时任务
if os.getenv("TURN_ON_SCHEDULE_TASK") == "True":
    initialize_and_start_scheduler()


#################################################################################
# 数据库事件处理器
from apps.data_opt.utils.mysqlmonitor import monitor

@monitor.on_update_for_table("t_supply")
async def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    if database == main_db:
        supply_old_type = data['old']['Type']
        supply_new_type = data['new']['Type']
        if supply_old_type == 'PL' and supply_new_type == 'MO':
            await push_pl_to_sap(data['old'])
    print(f"更新到 {database}.{table}: {data}")
    print(f"数据变更: {data_diff}")
