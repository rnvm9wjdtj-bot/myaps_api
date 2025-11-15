"""
定义了项目连接器的基础基类，项目需要在各自的py文件中实现该类的方法
"""
# import threading
import os
from abc import ABC, abstractmethod

from config.settings import MYAPS_MAIN_DB, MYAPS_BASE_URL, THIS_SERVER_HOST, THIS_SERVER_PORT
from apps.io_api.models import TSupply, TOrderwc
from apps.io_api.common import common_post, common_get_by_orm


this_base_url = f'http://{THIS_SERVER_HOST}:{THIS_SERVER_PORT}'
myaps_base_url = MYAPS_BASE_URL


class ScheduleTasksAbc(ABC):
    scheduled_dbs = os.getenv('SCHEDULED_DBS').split(',')
    
    @abstractmethod
    async def get_material(self, *args, **kwargs):
        pass

    @abstractmethod
    async def get_workcenter(self, *args, **kwargs):
        pass
    
    @abstractmethod
    async def get_bom(self, *args, **kwargs):
        pass

    @abstractmethod
    async def get_matver(self, *args, **kwargs):
        pass

    @abstractmethod
    async def get_matwc(self, *args, **kwargs):
        pass
    
    @abstractmethod
    async def refresh_stock(cls, *args, **kwargs):
        pass



class MyapsDbActionAbc(ABC):

    this_base_url = f'http://{THIS_SERVER_HOST}:{THIS_SERVER_PORT}'
    main_db = MYAPS_MAIN_DB

    @classmethod
    async def confirm_pl(cls, material_no: str, supply_no: str):
        """
        确认PL计划单
        当PL的Status变为'A2E'时，调用该方法，将PL记录推送至ERP
        
        - 对于需要根据APS的PL在ERP中创建MO的实施项目，子类需在该方法中实现推送PL至ERP的逻辑
        - 对于无需根据APS的PL在ERP中创建MO的实施项目，子类无需实现该方法
        """
        pass

    @classmethod
    async def pl_to_mo(cls, material_no: str, supply_no: str, mo_no: str=None):
        """
        将PL转为MO
        material_no: 物料编号
        supply_no: PL计划单编号
        mo_no: MO计划单编号，可选，若非None则更改PL的SupplyNo为mo_no

        
        """
        mo_data = [{
            'materialno': material_no,
            'supplyno': supply_no,
            'type': 'MO',   # 将类型改为MO（原本为PL）
            }]
        if mo_no:
            mo_data[0]['_overwrite'] = {
                    'match_on': {'materialno': material_no, 'supplyno': supply_no},
                    'new_value': {'supplyno': mo_no}
                    }
        await common_post(cls.main_db, TSupply, mo_data)

        # TODO 修改工序的SupplyNo为mo_no
        orderwc_response = common_get_by_orm(cls.main_db, TOrderwc, {
            'supplyno': supply_no,
            })
        orderwc_data = orderwc_response.json()['data']
        if orderwc_data:
            for orderwc in orderwc_data:
                orderwc['supplyno'] = mo_no
                orderwc['_overwrite'] = {
                    'match_on': {'orderno': orderwc['orderno']},
                    'new_value': {'orderno': f"{mo_no}{orderwc['itemno']}"}
                    }
            await common_post(cls.main_db, TOrderwc, orderwc_data)
        
