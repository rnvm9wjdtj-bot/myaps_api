"""
定义了项目连接器的基础基类，项目需要在各自的py文件中实现该类的方法
"""
# import threading
import os, requests
from typing import Literal
from abc import ABC, abstractmethod

from tortoise import Tortoise

from config.settings import MYAPS_MAIN_DB, MYAPS_BASE_URL, THIS_SERVER_HOST, THIS_SERVER_PORT
# from apps.io_api.models import TSupply, TOrderwc
# from apps.io_api.common import common_write, common_read_by_orm


this_base_url = f'http://{THIS_SERVER_HOST}:{THIS_SERVER_PORT}'
myaps_base_url = MYAPS_BASE_URL

this_session = requests.Session()


class ScheduleTasksAbc(ABC):
    scheduled_dbs = os.getenv('SCHEDULED_DBS').split(',')
    
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

    this_base_url = f'http://{THIS_SERVER_HOST}:{THIS_SERVER_PORT}'
    main_db = MYAPS_MAIN_DB

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
        await cls.pl_to_mo(plno=pl_data['SupplyNo'], mono=pl_data['MoNo'], to_status='CRE', memo=pl_data['Memo'])

    @classmethod
    async def pl_to_mo(cls, plno: str, mono: str=None, to_status: Literal['CRE', 'REL']='E2A', memo: str=None):
        """
        将PL转为MO
        🅰️supplyno: PL计划单编号
        🅰️mono: MO号，可选，若非None则更改PL的SupplyNo为mono
        🅰️to_status: 转化成MO后，Status设为哪个状态，默认'CRE'

        该方法有以下几种使用渠道：
        - 在 def confirm_pl() 被直接调用，适用于:
            - ERP同步返回MO信息的实施场景
            - 无需根据APS的PL在ERP中创建MO（或无需与ERP对接）的实施场景
        - 在路由函数中调用，适用于ERP异步返回MO信息的实施场景
        """
        response = this_session.patch(f'{this_base_url}/api/t_supply/pl?db_name={cls.main_db}', json=[{
            'type': 'MO',   # 将类型改为MO（原本为PL）
            'plno': plno,
            'status': to_status,
            'mono': mono,
            'memo': memo,
            }])
        return response