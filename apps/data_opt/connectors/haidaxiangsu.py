import requests, logging, atexit, datetime
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor



# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建requests会话
session = requests.Session()

db_set = ['hdfc', 'hdso']


def get_stock():    # 获取库存
    logger.info("执行获取库存定时任务")
    now = datetime.datetime.now()
    try:
        response = session.get('http://192.168.201.2:8000/zrestful_test2?sap-client=800', headers={'interface': 'stock', 'werks': '1600'})
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
                        })) 
        stock = stock.rename(columns={
            'matnr': 'materialno',
        })
        stock_data = stock.to_dict(orient='records')
        for db in db_set:
            session.post(f"http://172.16.101.209:8000/api/t_supply?db_name={db}", json=stock_data)
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
        # 添加示例定时任务 - 每小时执行一次
        scheduler.add_job(
            func=get_stock,
            trigger='interval',
            hours=1,
            id='get_stock',
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


if __name__ == "__main__":
# 当模块被导入时自动初始化和启动调度器
    initialize_and_start_scheduler()

