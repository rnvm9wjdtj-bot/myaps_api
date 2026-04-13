"""
加载当前项目文件（项目py）
"""

import os, importlib, json, requests
from typing import NamedTuple
from dotenv import load_dotenv

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_file = os.path.join(BASE_DIR, '.env')
load_dotenv(env_file)

# 导入模块
from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, MYAPS_DBSET_LIST
from globalobjects.globalconst import OrderStatusEnum
from apps.io_api.utils.common import dict_to_lower_keys
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.components._base import ApsHelpers
from apps.data_opt.utils.common import get_optimized_session


logger = log_config.get_logger(__name__)

# 创建HTTP会话，供本模块使用（使用连接池优化）
_HTTP_SESSION = get_optimized_session(
    retries=3,
    pool_connections=50,
    pool_maxsize=50,
    connect_timeout=10.0,
    read_timeout=30.0
)


# 确保环境变量正确设置
project_dir = os.getenv("PROJECT_DIR")
if not project_dir:
    raise ValueError("PROJECT_DIR环境变量未设置")

project_client = importlib.import_module(f'project_files.{project_dir}.client')



try:
    hap_conn = project_client.hap_conn
except:
    hap_conn = None



#################################################################################
# ⬇️MYAPS数据库事件HOOK
#################################################################################
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
from globalobjects import EVENT_AGGREGATOR



# 模块级变量，用于跟踪事件是否已经注册
_events_registered = False

class ApsEvent:
    def __init__(self, event_type: str, description: str, batch_handler: str=None, single_handler:str=None, batch_size: int=10000, flush_interval: int=5):
        self.event_type = event_type
        self.description = description
        self.batch_handle_func = None
        self.single_handle_func = None
        self.warning_msg = ""

        try:
            self.batch_handle_func = getattr(project_client, batch_handler)
        except AttributeError:
            try:
                self.single_handle_func = getattr(project_client, single_handler)
            except AttributeError:
                self.warning_msg = f"模块【{project_client.__name__}】未实现【{event_type}】处理逻辑"
        
        if self.single_handle_func or self.batch_handle_func:
            EVENT_AGGREGATOR.register(event_type=self.event_type, handler=self.handle_func, batch_size=batch_size, flush_interval=flush_interval, description=self.description)


    def handle_func(self, events_data_list: list[dict]):
        if self.batch_handle_func is not None:
            self.batch_handle_func(events_data_list)
        elif self.single_handle_func is not None:
            from concurrent.futures import ThreadPoolExecutor
            import threading
            import time

            # 信号量配置：限制最大并发数和事件间延迟
            MAX_CONCURRENT = 3      # 最大并发处理数
            POST_DELAY = 0.2        # 每个事件处理完后延迟（秒）
            MAX_WORKERS = 10        # 线程池大小

            semaphore = threading.Semaphore(MAX_CONCURRENT)

            def safe_handle(event_data):
                with semaphore:
                    try:
                        self.single_handle_func(event_data)
                        time.sleep(POST_DELAY)  # 处理完后延迟，减轻下游压力
                    except Exception as e:
                        logger.fail(f"处理单个事件失败", "", str(e))

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                executor.map(safe_handle, events_data_list)
        else:
            log_msg = f"⚠️ {self.warning_msg}数据：\n{json.dumps(events_data_list, ensure_ascii=False)}"
            logger.debug(log_msg)

    
    def add_event(self, event_data: dict):
        EVENT_AGGREGATOR.add(event_type=self.event_type, event=event_data)



# 只在第一次导入时注册事件
if not _events_registered:
    aps_pl_status_a2e_event = ApsEvent(event_type="|pl_status_a2e|", single_handler="handle_pl_status_a2e", batch_handler="batch_handle_pl_status_a2e", description="PL 单据下达")
    aps_pr_created_event = ApsEvent(event_type="|pr_created|", single_handler="handle_pr_created", batch_handler="batch_handle_pr_created", description="PR 单据 创建")
    aps_pl_typeto_mo_event = ApsEvent(event_type="|pl_typeto_mo|", single_handler="handle_pl_typeto_mo", batch_handler="batch_handle_pl_typeto_mo", description="PL 变更为 MO")
    aps_pr_deleted_event = ApsEvent(event_type="|pr_deleted|", single_handler="handle_pr_deleted", batch_handler="batch_handle_pr_deleted", description="PR 单据 删除")
    _events_registered = True
    logger.success("数据库事件注册", "", "所有事件已成功注册")
else:
    logger.debug("数据库事件注册", "", "事件已经注册，跳过重复注册")


@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    from apps.data_opt.components._base import ApsHelpers

    data_before = dict_to_lower_keys(data['old'])
    type_before = data_before['type']
    status_before = data_before['status']

    data_now = dict_to_lower_keys(data['new'])
    type_now = data_now['type']
    status_now = data_now['status']

    if type_now == 'PL' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
        plno = data_now['supplyno']
        # 工单管理界面中，通过点击按钮下达生产计划单PL
        # ApsHelpers._modify_supply(supplyno=plno, memo=f"下达MO: {plno}")
        try:
            _HTTP_SESSION.patch(f'{THIS_BASE_URL}/api/t_supply/{plno}/...?db_name={MYAPS_MAIN_DB}', json={
                'memo': f"📤 trying to push PL{plno}",
            })
        except Exception as e:
            logger.error(f"更新memo失败: {e}")
        aps_pl_status_a2e_event.add_event(data_now)
    elif type_before == 'PL' and type_now == 'MO':
        # 当 PL下达成功后，推送领料申请（RS）
        aps_pl_typeto_mo_event.add_event(data_now)
    
    

@mysql_monitor.on_insert_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_insert_supply(database: str, table: str, data: dict):
    """处理t_supply表的插入事件"""
    from apps.data_opt.components._base import ApsHelpers

    new_data = dict_to_lower_keys(data['new'])
    type_ = new_data['type']
    # status_now = new_data['status']

    if type_ == 'PR':
        aps_pr_created_event.add_event(new_data)
   


# @mysql_monitor.on_delete_for_table("t_supply", database=MYAPS_MAIN_DB)
# def handle_delete_supply(database: str, table: str, data: dict):
#     """处理t_supply表的删除事件"""
#     from apps.data_opt.components._base import ApsHelpers

#     deleted_data = dict_to_lower_keys(data)
#     type_ = deleted_data['type']
#     status_now = deleted_data['status']

    # if type_ == 'PR':
    #     # TODO 当 PR 单据被删除时，删除 ERP 中的采购申请单据
    #     aps_pr_deleted_event.add_event(deleted_data)
   
