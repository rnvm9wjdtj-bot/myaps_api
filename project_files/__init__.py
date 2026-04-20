"""
加载当前项目文件（项目py）
"""

import os, importlib, json, requests, time
from datetime import datetime
from typing import List, Dict, Optional, Callable
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from threading import Semaphore, Lock

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
from apps.data_opt.utils.mysqlmonitor import mysql_monitor
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

    _MAX_CONCURRENT = 4
    _POST_DELAY = 0.2

    def __init__(self, event_type: DbEventType, description: str, batch_size: int=10000, flush_interval: int=5):
        self.event_type = event_type
        self.description = description
        self.warning_msg = ""
        self._session = get_optimized_session(retries=0)
        self._semaphore = Semaphore(self._MAX_CONCURRENT)
        self._event_lock = Lock()
        self._last_request_time = 0.0
        EVENT_AGGREGATOR.register(event_type=self.event_type, handler=self.db_event_distributor, batch_size=batch_size, flush_interval=flush_interval, description=self.description)


    def _send_request_with_control(self, event_type: DbEventType, event_data: List[Dict]):
        with self._semaphore:
            try:
                current_time = time.time()
                elapsed = current_time - self._last_request_time
                if elapsed < self._POST_DELAY:
                    time.sleep(self._POST_DELAY - elapsed)
                
                with self._event_lock:
                    self._last_request_time = time.time()
                
                self._session.post(url=f"{THIS_BASE_URL}/project/db_event/{event_type.value}", json=event_data, timeout=(10.0, 120.0))
                logger.debug(f"✅ 事件发送成功: {event_type.value}")
            except Exception as e:
                logger.fail(f"发送事件失败", event_type.value, str(e))


    def db_event_distributor(self, event_data: List[Dict]):
        """事件数据转发器（异步发送，支持并发控制）"""
        global _shared_executor
        _shared_executor.submit(self._send_request_with_control, self.event_type, event_data)


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
    aps_pl_status_a2e_event = ApsEvent(event_type=DbEventType.PL_STATUS_A2E, description="PL 单据下达")
    aps_pr_created_event = ApsEvent(event_type=DbEventType.PR_CREATED, description="PR 单据 创建")
    aps_pl_typeto_mo_event = ApsEvent(event_type=DbEventType.PL_TYPETO_MO, description="PL 变更为 MO")
    aps_pr_deleted_event = ApsEvent(event_type=DbEventType.PR_DELETED, description="PR 单据 删除")
    _events_registered = True
    logger.success("数据库事件注册", "", "所有事件已成功注册")
else:
    logger.debug("数据库事件注册", "", "事件已经注册，跳过重复注册")



#################################################################################
# ⬇️事件处理函数
#################################################################################
@mysql_monitor.on_update_for_table("t_supply", database=MYAPS_MAIN_DB)
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


@mysql_monitor.on_insert_for_table("t_supply", database=MYAPS_MAIN_DB)
def handle_insert_supply(database: str, table: str, data: dict):
    """处理t_supply表的插入事件"""
    try:
        from apps.data_opt.components._base import ApsHelpers

        new_data = dict_to_lower_keys(data['new'])
        type_ = new_data['type']
        # status_now = new_data['status']

        if type_ == 'PR':
            aps_pr_created_event.add_event(new_data)
    except Exception as e:
        logger.fail("处理t_supply插入事件", "", str(e))
   


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



#################################################################################
# 项目路由
#################################################################################
from fastapi import APIRouter, Query, Body, Header, Request, HTTPException, Depends

# 创建路由器实例
rt = APIRouter()


def get_client_ip(request: Request):
    """获取客户端IP地址"""
    client_ip = request.client.host
    return client_ip


def only_localhost():
    """仅允许本地主机访问的依赖项"""
    async def dependency(request: Request):
        client_ip = get_client_ip(request)
        if client_ip not in ["127.0.0.1", "localhost", "::1"]:
            raise HTTPException(status_code=403, detail="Access denied: Only localhost access allowed")
    return dependency


@rt.post("/db_event/{event_type}", dependencies=[Depends(only_localhost())])
async def handle_event(
    event_type: str,
    event_data: Optional[List[Dict]] = Body(None, description="事件数据")
):
    if not event_data:
        return

    async def process_event():
        try:
            event_handler_name = f"batch_handle_{event_type}"
            event_handler = getattr(project_client, event_handler_name)
            if event_handler:
                # 在后台线程中执行，避免阻塞事件循环
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, event_handler, event_data)
        except Exception as e:
            logger.warning(f"{project_client.__name__} 未能处理 {event_type} 事件: {str(e)}")

    import asyncio
    asyncio.create_task(process_event())
    return {"status": "success"}