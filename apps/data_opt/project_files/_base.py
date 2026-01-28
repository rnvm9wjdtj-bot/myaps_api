"""
引用包和常量，供各项目文件使用
"""

# import threading
import os
import logging, json, requests, pandas as pd
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET
from globalobjects.globalconst import OrderStatusEnum
from apps.data_opt.utils.common import get_session


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from globalobjects import file_timed_logger
from apps.io_api.utils.common import standard_response
from apps.io_api.utils.db_operation import db_delete, db_bupsert, call_dbprocdure, db_query, db_bupsert, db_supsert
from apps.data_opt.components.hap import HapConnection
from ..utils.scheduler import cron_task
from ..utils.common import add_basic_auth_requests
from ..utils.json_manager import JSONManager
from ..utils.data_processor import DataProcessor
from apps.io_api.utils.db_operation import db_delete, db_bupsert


# 配置日志
filelog_normal = file_timed_logger.setup_logging(__name__, log_filename='normal.log')
filelog_error = file_timed_logger.setup_logging(__name__, log_filename='error.log')



logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)



# class ProjectBaseConfig:
#     pass




class ApsBaseAction(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()
    

    @classmethod
    @abstractmethod
    async def click_release_button(cls, pl_data: dict, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        - 各项目文件须声明子类并覆写该方法，注意要包含实现推送 PL 至 ERP 的逻辑：
            - 若 ERP 同步返回创建结果，则覆写方法需还需将 ERP 返回信息更新至原PL
            - 若异步，则由 ERP 调用 api patch("/t_supply/{path_targetsupply}") 更新 PL
        - 若无需对接ERP，则无需覆写此方法
        """
        await cls._pl_release_success(plno=pl_data['supplyno'], to_status='REL')


    @classmethod
    def _get_supplymo_detaildata(cls, supplyno: str):
        supply_response = cls._session.get(f"{cls.this_base_url}/api/v_supply_mo?db_name={cls.main_db}&supplyno={supplyno}")
        supply_response_json = supply_response.json()
        supplymo_detaildata = supply_response_json['data'][0]
        return supplymo_detaildata


    @classmethod
    async def _pl_release_success(cls, plno: str, mono: str=None, to_status: Literal[OrderStatusEnum.E2A, OrderStatusEnum.REL]='E2A', msg: str=None, msg_from: str=None):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段，作为私有方法在 def click_release_button() 中被直接调用
        🅰 supplyno: PL计划单编号
        🅰 mono: MO号，可选，若非None则更改PL的SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"✅推送计划任务执行成功，账套：{cls.main_db}，PL单号：{plno}，MO单号：{mono or plno}"
        console_log.info(log_msg)
        filelog_normal.info(log_msg)
        response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{plno}/pltomo?db_name={cls.main_db}', json={
            'status': to_status,
            'supplyno': mono,
            'memo': json.dumps({"msg": f"✅{msg}", "from": msg_from, "success": True, "datetime": now, "plno": plno}, ensure_ascii=False),
        })
        return response


    @classmethod
    async def _pl_release_failed(cls, plno: str, to_status: Literal[OrderStatusEnum.NEW, OrderStatusEnum.CRE]='CRE', msg: str=None, msg_from: str=None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"🚫 推送计划任务执行失败，账套：{cls.main_db}，PL单号：{plno}"
        console_log.error(log_msg)
        filelog_normal.error(log_msg)
        response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/{plno}/edit?db_name={cls.main_db}', json={
            'status': to_status,    # ❗❗失败情况下，状态务必回撤为 CRE 或 NEW ，否则后续无法再次下达
            'memo': json.dumps({"msg": f"🚫{msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False),
        })
        return response


    @classmethod
    def _fetch_data(cls, url: str) -> List[Dict]:
        # 调用自身 API GET 数据
        response = cls._session.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('data', [])


    @classmethod
    async def get_dategrouped_pr(cls, db_name: str=None, period: int|str=30, groupdates: str=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认cls.main_db
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        from apps.io_api.routers import get_matdailyqtyreport
        from datetime import date, datetime
        db_name = db_name or cls.main_db
        response = await get_matdailyqtyreport(db_name=db_name, period=period, groupdates=groupdates, materialno=None)
        data = response.get('data', [])
        # response = cls._session.get(f"{cls.this_base_url}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}")
        # response.raise_for_status()
        # data = response.json().get('data', [])
        field_map = field_map or {
            'materialno': '料号',
            'datestr': '交期',
            'groupdate': '日期',
            'qty': '数量',
        }
        if not field_map:
            return data
        # 转换数据，确保所有日期对象都被转换为字符串
        result = []
        for item in data:
            mapped_item = {}
            for k, v in item.items():
                # 转换日期对象为字符串
                if isinstance(v, (date, datetime)):
                    v = str(v)
                mapped_item[field_map.get(k, k)] = v
            result.append(mapped_item)
        return result


    @classmethod
    @abstractmethod
    async def when_mo_close(cls, mo_data: dict, *args, **kwargs):
        """
        当MO关闭时该方法将被自动调用
        🅰 mo_data: MO数据
        """
        pass