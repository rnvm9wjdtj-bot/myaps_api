import os

# db_set_str = os.getenv("MYAPS_DB_SET")
# if 'haida' in db_set_str or 'hdfc' in db_set_str or 'hdso' in db_set_str:
    

import requests, logging, atexit, datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor

from config import uservar as uv
from ..common import monitor


@monitor.on_update_for_table('t_supply')
async def my_update_handler(database, table, data):
    print(f"自定义UPDATE: {table} -> {data}")


# 创建异步初始化函数，确保在正确的异步上下文中启动监控
async def init_binlog_monitor():
    print("正在启动Binlog监控...")
    await monitor.start_monitoring()
    print("Binlog监控已启动")

# 在应用启动时调用的函数
def start_monitoring_sync():
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(init_binlog_monitor())
    finally:
        # 注意：这里不关闭事件循环，因为监控需要持续运行
        pass



sap_url = 'http://192.168.201.2:8000/zrestful_test2?sap-client=800'

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建requests会话
session = requests.Session()

db_set = ['hdfc', 'hdso']


async def refresh_stock():    # 刷新库存
    logger.info("执行获取库存定时任务")
    try:
        response = session.get(url=sap_url, headers={'interface': 'stock', 'werks': '1600'})
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
        for db in db_set:
            await session.delete(f"http://localhost:8000/api/t_supply?db_name={db}", data='ST')
            await session.post(f"http://localhost:8000/api/t_supply?db_name={db}", json=stock_data)
        logger.info("获取库存定时任务执行完成")
    except Exception as e:
        logger.error(f"获取库存定时任务执行失败: {str(e)}")



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
    # 启动binlog监控
    start_monitoring_sync()
    # 注册退出处理函数，确保程序退出时调度器被正确关闭
    atexit.register(shutdown_scheduler)

initialize_and_start_scheduler()

