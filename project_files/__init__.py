"""
加载当前项目文件（项目py）
"""

import os, importlib, json, requests, time
from datetime import datetime
from typing import List, Dict, Optional, Callable, Any
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

# 加载环境变量
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_file = os.path.join(BASE_DIR, '.env')
load_dotenv(env_file)

# 导入模块
from core.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET, MYAPS_DBSET_LIST, PROJECT_DIR
from globalobjects.globalconst import OrderStatusEnum
from apps.io_api.utils.common import dict_to_lower_keys
from globalobjects import logger as log_config
from apps.data_opt.utils.scheduler import cron_task
from apps.data_opt.components._base import ApsHelper
from apps.data_opt.utils.common import get_optimized_session
from apps.common.utils.redis_pool_manager import get_redis_pool_manager


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
if not PROJECT_DIR:
    raise ValueError("PROJECT_DIR环境变量未设置")

project_client = importlib.import_module(f'project_files.{PROJECT_DIR}.client')



try:
    hap_conn = project_client.hap_conn
except:
    hap_conn = None



#################################################################################
# ⬇️MYAPS数据库事件HOOK
#################################################################################
from enum import Enum
from apps.data_opt.utils.binlog_listener import binlog_listener
from globalobjects import EVENT_AGGREGATOR


class DbEventType(Enum):
    """数据库事件类型"""
    PL_STATUS_A2E = "pl_status_a2e"  # PL状态变为 A2E
    PL_TYPETO_MO = "pl_to_mo"  # PL类型变为 MO
    PR_CREATED = "pr_created"  # PR 新增
    PR_DELETED = "pr_deleted"  # PR 删除


# 模块级变量，用于跟踪事件是否已经注册
_events_registered = False

# 共享线程池
_shared_executor = ThreadPoolExecutor(max_workers=10)

class ApsEvent:

    def __init__(self, event_type: DbEventType, description: str, batch_size: int=10000, flush_interval: int=5, error_handler: Optional[Callable]=None, error_handler_kwargs: Optional[Dict[str, Any]]=None):
        self.event_type = event_type
        self.description = description
        self.error_handler = error_handler  # 错误处理函数
        self.error_handler_kwargs = error_handler_kwargs or {}  # 错误处理函数参数
        self.warning_msg = ""
        self._session = get_optimized_session(retries=0)
        self._event_lock = Lock()
        self._last_request_time = 0.0
        EVENT_AGGREGATOR.register(event_type=self.event_type, handler=self.db_event_distributor, batch_size=batch_size, flush_interval=flush_interval, description=self.description)


    def _send_request_with_control(self, event_type: DbEventType, event_data: List[Dict]):
        try:
            log_config.info(f"准备发送事件到消息队列: {event_type.value}")
            event_message = {
                'event_type': event_type.value,
                'data': event_data,
                'timestamp': time.time()
            }
            message_json = json.dumps(event_message)
            pool_manager = get_redis_pool_manager()
            success = pool_manager.lpush_safe('db_events', message_json)
            if success:
                log_config.info(f"事件已发送到消息队列: {event_type.value}")
            else:
                log_config.warning(f"事件已写入本地缓冲: {event_type.value}")
        except Exception as e:
            log_config.error(f"发送事件到消息队列失败: {e}")


    def db_event_distributor(self, event_data: List[Dict]):
        """事件数据转发器（直接发送到 Redis，避免线程池）"""
        try:
            self._send_request_with_control(self.event_type, event_data)
        except Exception as e:
            log_config.error(f"事件分发失败: {e}")
            # 执行错误处理函数
            if self.error_handler:
                try:
                    self.error_handler(
                        event_type=self.event_type, 
                        event_data=event_data, 
                        msg=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 🚫 {str(e)}", 
                        **self.error_handler_kwargs
                    )
                except Exception as handler_error:
                    log_config.error(f"错误处理函数执行: {handler_error}")


    def add_event(self, event_data: dict):
        def convert_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetime(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [convert_datetime(item) for item in obj]
            return obj
        
        cleaned_data = convert_datetime(event_data)
        EVENT_AGGREGATOR.add(event_type=self.event_type, event=cleaned_data)


# 只在第一次导入时注册事件
if not _events_registered:
    async def error_handler(native_plno: str, msg: str, msg_from: str = None, **kwargs):
        await ApsHelper().pl_release_failed_async(native_plno=native_plno, msg=msg, msg_from=msg_from or "API", **kwargs)

    aps_pl_status_a2e_event = ApsEvent(
        event_type=DbEventType.PL_STATUS_A2E, 
        description="PL 单据下达",
        error_handler=error_handler,
        error_handler_kwargs={"msg_from": "API"}
    )
    aps_pr_created_event = ApsEvent(
        event_type=DbEventType.PR_CREATED, 
        description="PR 单据 创建",
    )
    aps_pl_typeto_mo_event = ApsEvent(
        event_type=DbEventType.PL_TYPETO_MO, 
        description="PL 变更为 MO",
    )
    aps_pr_deleted_event = ApsEvent(
        event_type=DbEventType.PR_DELETED, 
        description="PR 单据 删除",
    )
    _events_registered = True
    logger.success("数据库事件注册", "", "所有事件已成功注册")
else:
    logger.debug("数据库事件注册", "", "事件已经注册，跳过重复注册")



#################################################################################
# ⬇️事件处理函数
#################################################################################
@binlog_listener.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_update_supply(database: str, table: str, data: dict, data_diff: dict):
    """处理t_supply表的更新事件"""
    try:
        data_before = dict_to_lower_keys(data['old'])
        type_before = data_before['type']
        status_before = data_before['status']
        
        data_now = dict_to_lower_keys(data['new'])
        type_now = data_now['type']
        status_now = data_now['status']
        
        if type_now == 'PL' and status_now == "A2E" and status_before in ["NEW", "CRE"]:
            plno = data_now['supplyno']        
            aps_pl_status_a2e_event.add_event(data_now)
        elif type_before == 'PL' and type_now == 'MO':
            # 当 PL下达成功后，推送领料申请（RS）
            aps_pl_typeto_mo_event.add_event(data_now)
    except Exception as e:
        logger.fail("处理t_supply更新事件", "", str(e))


@binlog_listener.on_insert_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_insert_supply(database: str, table: str, data: dict):
    """处理t_supply表的插入事件"""
    try:
        from apps.data_opt.components._base import ApsHelper

        new_data = dict_to_lower_keys(data['new'])
        type_ = new_data['type']
        # status_now = new_data['status']

        if type_ == 'PR':
            aps_pr_created_event.add_event(new_data)
    except Exception as e:
        logger.fail("处理t_supply插入事件", "", str(e))
   


# @binlog_listener.on_delete_for_table("t_supply", database=MYAPS_MAIN_DB)
# def handle_delete_supply(database: str, table: str, data: dict):
#     """处理t_supply表的删除事件"""
#     from apps.data_opt.components._base import ApsHelpers

#     deleted_data = dict_to_lower_keys(data)
#     type_ = deleted_data['type']
#     status_now = deleted_data['status']

    # if type_ == 'PR':
    #     # TODO 当 PR 单据被删除时，删除 ERP 中的采购申请单据
    #     aps_pr_deleted_event.add_event(deleted_data)



#################################################################################
# 项目事件处理发送
#################################################################################

async def handle_event(event_type: str, event_data: Optional[List[Dict]]):
    if not event_data:
        return

    async def process_event():
        try:
            event_handler_name = f"batch_handle_{event_type}"
            event_handler = getattr(project_client, event_handler_name)
            if event_handler:
                await event_handler(event_data)
        except Exception as e:
            logger.warning(f"{project_client.__name__} 未能处理 {event_type} 事件: {str(e)}")

    import asyncio
    asyncio.create_task(process_event())
    return {"status": "success"}