"""
引用包和常量，供各项目文件使用
定义基类，需要在各项目文件中实现具体方法
"""

# import threading
import os
import logging
from typing import Literal
from abc import ABC#, abstractmethod

# from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, THIS_SERVER_PORT, THIS_PROTOCOL#, MYAPS_BASE_URL
from apps.data_opt.utils.common import get_session

# ❗⬇️不要删掉，便于各项目文件引用
from globalobjects import file_timed_logger
from apps.io_api.common import standard_response
from apps.data_opt.components.hap import HapConnection



# 配置日志
file_log = file_timed_logger.setup_logging(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)



class ScheduleTasksAbc(ABC):
    this_base_url = f'{THIS_PROTOCOL}localhost:{THIS_SERVER_PORT}'
    scheduled_dbs = os.getenv('SCHEDULED_DBS').split(',')
    _session = get_session()
    
    @classmethod
    async def get_material(cls, *args, **kwargs):
        pass

    @classmethod
    async def get_workcenter(cls, *args, **kwargs):
        pass
    
    @classmethod
    async def get_bom(cls, *args, **kwargs):
        pass

    @classmethod
    async def get_matver(cls, *args, **kwargs):
        pass

    @classmethod
    async def get_matwc(cls, *args, **kwargs):
        pass
    
    @classmethod
    async def refresh_stock(cls, *args, **kwargs):
        pass



class MyapsDbActionsAbc(ABC):

    this_base_url = f'{THIS_PROTOCOL}localhost:{THIS_SERVER_PORT}'
    main_db = MYAPS_MAIN_DB
    _session = get_session()
    
    @classmethod
    async def confirm_pl(cls, pl_data: dict):
        """
        确认PL计划单，将其转为MO
        
        当监听到PL的Status变为'A2E'时，该方法将被自动调用
        - 对于需要根据APS的PL在ERP中创建MO的实施场景，子类需要通过覆写该方法以实现推送PL至ERP的逻辑
            - 对于同步返回创建结果的，需在覆写的最后一步调用 def pl_to_mo() 或执行 "super().confirm_pl()"，将ERP返回的工单号等信息改写至原PL
            - 对于异步返回创建结果的，则无需调用 def pl_to_mo() 或执行 "super().confirm_pl()"，因为路由函数已封装 pl_to_mo() ，供ERP异步调用
        - 对于无需根据APS的PL在ERP中创建MO（或无需与ERP对接）的实施场景，则直接调用 def pl_to_mo()将Type设为'MO'、Status设为'CRE'，子类无需覆写此方法
        """
        await cls.pl_to_mo(plno=pl_data['supplyno'], mono=pl_data['mono'], to_status=pl_data['status'], memo=pl_data['memo'], is_execute_updates=pl_data['is_execute_updates'])

    @classmethod
    async def pl_to_mo(cls, plno: str, mono: str=None, to_status: Literal['CRE', 'REL']='E2A', memo: str=None, is_execute_updates: bool=True):
        """
        将PL转为MO
        🅰️supplyno: PL计划单编号
        🅰️mono: MO号，可选，若非None则更改PL的SupplyNo为mono
        🅰️to_status: 转化成MO后，Status设为哪个状态，默认'CRE'
        🅰️memo: 写入t_supplymemo注字段的内容
        🅰️is_execute_updates: 是否执行更新，默认True
        
        该方法有以下几种使用渠道：
        - 在 def confirm_pl() 被直接调用，适用于:
            - ERP同步返回MO信息的实施场景
            - 无需根据APS的PL在ERP中创建MO（或无需与ERP对接）的实施场景
        - 在路由函数中调用，适用于ERP异步返回MO信息的实施场景
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



class DefaultParamsAbc:
    SCHEDULE_TASK_HOUR="6,8,10,12,14,16"
    SCHEDULE_TASK_MINUTE="55"



class DefaultValueAbc:
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