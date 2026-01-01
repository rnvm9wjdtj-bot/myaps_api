"""
引用包和常量，供各项目文件使用
"""

# import threading
# import os
import logging
from typing import Literal
from abc import ABC#, abstractmethod

# from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, THIS_SERVER_PORT, THIS_PROTOCOL, SCHEDULED_DBS, MYAPS_BASE_URL
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


class ParamValueBase:
    """
    项目文件中使用的参数值
    """


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


class DbEventAbc(ABC):

    this_base_url = MYAPS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()
    
    @classmethod
    def press_release_button(cls, pl_data: dict, *args, **kwargs):
        """
        当按下工单管理的下达按钮（PL的Status变为'A2E'）时该方法将被自动调用
        - 各项目文件须声明子类并覆写该方法以实现推送PL至ERP的逻辑
            - 若 ERP 异步返回创建结果，则由 ERP 异步调用路由函数 convert_pl_to_mo_by_dbprocdure() 改写 APS 的 PL 信息
            - 若同步返回创建结果，则覆写最后一步执行 super().press_release_button()，将ERP返回的工单号等信息改写至原PL
        """
        cls._convert_pl_to_mo(plno=pl_data['supplyno'], mono=pl_data['mono'], to_status=pl_data['status'], memo=pl_data['memo'], is_execute_updates=pl_data['is_execute_updates'])

    @classmethod
    def _get_supplymo_detaildata(cls, supplyno: str):
        supply_response = cls._session.get(f"{MYAPS_BASE_URL}/api/v_supply_mo?db_name={MYAPS_MAIN_DB}&supplyno={supplyno}")
        supply_response_json = supply_response.json()
        supplymo_detaildata = supply_response_json['data'][0]
        return supplymo_detaildata

    @classmethod
    def _convert_pl_to_mo(cls, plno: str, mono: str=None, to_status: Literal['CRE', 'REL']='E2A', memo: str=None, is_execute_updates: bool=True):
        """
        通过调用自路由修改PL的Type、Status、SupplyNo、Memo等字段
        🅰️supplyno: PL计划单编号
        🅰️mono: MO号，可选，若非None则更改PL的SupplyNo为mono
        🅰️to_status: 转化成MO后，Status设为哪个状态，默认'CRE'
        🅰️memo: 写入t_supplymemo注字段的内容
        🅰️is_execute_updates: 是否执行更新，默认True

        - 在 def press_release_button() 中被直接调用，适用于:
            - ERP接到PL后同步返回MO信息
        - 无需根据APS的PL在ERP中创建MO（或无需与ERP对接）的实施场景，则直接调用
        """
        response = cls._session.patch(f'{cls.this_base_url}/api/t_supply/pl?db_name={cls.main_db}', json=[{
            'type': 'MO',   # 将类型改为MO（原本为PL）
            'plno': plno,
            'status': to_status,
            'mono': mono,
            'memo': memo,
            'is_execute_updates': is_execute_updates,
            }])
        return response


