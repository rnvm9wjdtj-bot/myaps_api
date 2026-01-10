"""
引用包和常量，供各项目文件使用
"""

# import threading
# import os
import logging, json, requests, pandas as pd
from socket import MsgFlag
from typing import Literal, List, Dict, Any, Optional
from abc import ABC#, abstractmethod
from datetime import datetime, timedelta

# from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, THIS_BASE_URL, MYAPS_DB_SET
from apps.data_opt.utils.common import get_session


# ❗❗❗❗❗❗❗❗❗❗❗❗⬇️不要删掉，便于各项目文件引用 ❗❗❗❗❗❗❗❗❗❗❗❗
from globalobjects import file_timed_logger
from apps.io_api.common import standard_response
from apps.data_opt.components.hap import HapConnection
from ..utils.scheduler import cron_task
from ..utils.common import add_basic_auth_requests


# 配置日志
file_log = file_timed_logger.setup_logging(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)


class ProjectParamBase:
    """
    项目文件中使用的参数值
    """
    # 连接器中（拉取外部系统数据）定时任务生效的账套数据库，建议与 MYAPS_DB_SET 保持一致
    SCHEDULED_DBS = MYAPS_DB_SET


class DefaultValueBase:
    myaps_is_pro = 1 # 1 / 0 MyAPS是否专业版

    auto_matver = 1  # 1 / 0 是否自动生成物料版本号，为True时，会在 material save时自动生成产线版本
    matver_prefix = "V" # 产线版本前缀字母
    matver_width = 1    # 产线版本号宽度

    itemno_prefix = "A" # 工序项目前缀字母
    itemno_width = 3    # 工序项目号宽度
    
    MAT_PLANT = None   # 默认工厂
    MAT_PLANNER = None   # 默认计划员
    MAT_LOCATION = None  # 默认车间
    MAT_FIFO = 1   # 默认FIFO原则
    MAT_LEADDAY_E = 10  # 自制件默认提前期
    MAT_LEADDAY_F = 1  # 采购件默认提前期
    MAT_EXPDAY = 365  # 默认保质期
    # MAT_PRICE = 0  # 默认价格
    MAT_GRDAY_E = 0
    MAT_GRDAY_F = 0
    MAT_PHANTOM = 'N'  # 是否虚拟件
    MAT_PHANTOMMIN = 0
    MAT_FIRMDAY = 0
    MAT_DAYGAP = 1  # 默认计划间隔
    MAT_CANDELAY = 'Y'  # 是否允许延迟计划
    MAT_LOTSIZE = 'EX'  # 默认批次大小
    MAT_LOTFIX = 0  # 默认固定批
    MAT_LOTMIN = 0  # 默认最小批
    MAT_LOTMAX = 0  # 默认最大批
    MAT_LOTROUND = 0  # 默认取整
    MAT_LOTSS = 0  # 默认安全库存
    MAT_LOTPOINT = 0  # 默认重订货点
    MAT_LOTTOP = 0  # 默认最大库存点
    MAT_PREDAY = 999  # 默认向前冲销(天)
    MAT_SUBDAY = 999  # 默认向后冲销(天)

    MATVER = f"{matver_prefix}{1:0{matver_width}d}"  # 示例 / 默认物料版本号
    MATVER_LOTFROM = 0  # 默认最小批
    MATVER_LOTTO = 9999999  # 默认最大批
    MATVER_PRIORITY = 0  # 默认优先级

    WC_WORKER = 1  # 默认工人数
    WC_PRIORITY = 0  # 默认优先级

    ITEMNO = f"{itemno_prefix}{1:0{itemno_width}d}" # 示例 / 默认工序项目


    @classmethod
    def to_dict(cls):
        cls_dict = cls.__dict__
        return {k: v for k, v in cls_dict.items() if not k.startswith("__")}


class ApsBaseAction(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()
    
    @classmethod
    async def press_release_button(cls, pl_data: dict, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        - 各项目文件须声明子类并覆写该方法，注意要包含实现推送 PL 至 ERP 的逻辑：
            - 若 ERP 同步返回创建结果，则覆写方法需还需将 ERP 返回信息更新至原PL
            - 若异步，则由 ERP 调用 api convert_pl_to_mo_by_dbprocdure() 更新 PL
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
    async def _pl_release_success(cls, plno: str, mono: str=None, to_status: Literal['E2A', 'REL']='E2A', msg: str=None, msg_from: str=None):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段，作为私有方法在 def press_release_button() 中被直接调用
        🅰 supplyno: PL计划单编号
        🅰 mono: MO号，可选，若非None则更改PL的SupplyNo
        🅰 to_status: 转化成MO后，Status设为哪个状态，默认'REL'
        🅰 msg: 外部系统返回信息
        🅰 msg_from: 外部系统名称
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"✅推送计划任务执行成功，账套：{cls.main_db}，PL单号：{plno}，MO单号：{mono or plno}"
        console_log.info(log_msg)
        file_log.info(log_msg)
        response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/pl?db_name={cls.main_db}', json=[{
            'type': 'MO',
            'plno': plno,
            'status': to_status,
            'mono': mono,
            'memo': json.dumps({"msg": f"✅{msg}", "from": msg_from, "success": True, "datetime": now, "plno": plno}, ensure_ascii=False),
            'is_execute_updates': True,
            }])
        return response

    @classmethod
    async def _pl_release_failed(cls, plno: str, to_status: Literal['NEW', 'CRE']='CRE', msg: str=None, msg_from: str=None):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"🚫 推送计划任务执行失败，账套：{cls.main_db}，PL单号：{plno}"
        console_log.error(log_msg)
        file_log.error(log_msg)
        response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/pl?db_name={cls.main_db}', json=[{
            'type': 'PL',
            'plno': plno,
            'status': to_status,    # ❗❗失败情况下，状态务必回撤为 CRE 或 NEW ，否则后续无法再次下达
            'mono': None,
            'memo': json.dumps({"msg": f"🚫{msg}", "from": msg_from, "success": False, "datetime": now}, ensure_ascii=False),
            'is_execute_updates': False,
            }])
        return response

    @classmethod
    def _fetch_data(cls, url: str) -> List[Dict]:
        # 调用自身 API GET 数据
        response = cls._session.get(url, timeout=30)
        response.raise_for_status()
        return response.json().get('data', [])

    @classmethod
    async def get_dategrouped_pr(cls, period: int=30, groupdates: str=None, field_mapper: dict=None):
        response = await cls._session.get(f"{cls.this_base_url}/api/v_matdailyqtyreport?db_name={cls.main_db}&period={period}&groupdates={groupdates}")
        data = response['data']
        if not data:
            return []
        if field_mapper:
            return [{field_mapper.get(k, k): v for k, v in item.items()} for item in data]
        return data