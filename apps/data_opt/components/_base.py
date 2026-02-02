import logging, json
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union, Any
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
import pandas as pd
from pydantic import BaseModel as PydanticModel

from config.settings import THIS_BASE_URL, MYAPS_MAIN_DB
from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.schemas import (
    BaseModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold, AcceptSupply, AcceptConfirm
)
from apps.io_api.models import TSupply, TDemand
from apps.io_api.utils.db_operation import db_query
from globalobjects import globalconst, file_timed_logger, CACHE_JSON, ProjectDefaultValues as pdv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)

filelog_normal = file_timed_logger.setup_logging(__name__, log_filename='normal.log')
filelog_error = file_timed_logger.setup_logging(__name__, log_filename='error.log')



class BaseConnection(ABC):
    
    def __init__(self, *args, **kwargs):
        self._session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        pass


    @abstractmethod
    async def pull_from_source(self, *args, **kwargs):
        """
        从目标系统获取数据
        """
        pass


    @abstractmethod
    async def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass


    def __enter__(self):
        """上下文管理器入口"""
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if hasattr(self, '_session') and self._session:
            self._session.close()


# class ApsConnection():
#     this_base_url = THIS_BASE_URL
#     main_db = MYAPS_MAIN_DB
#     session = get_session()

#     @classmethod
#     def _get_supplymo_detaildata(cls, supplyno: str):
#         """
#         获取工单计划单详情
#         Args:
#             supplyno: 工单号
#         Returns:
#             工单计划单详情
#         """
#         supply_response = cls.session.get(f"{cls.this_base_url}/api/v_supply_mo?db_name={cls.main_db}&supplyno={supplyno}")
#         supply_response_json = supply_response.json()
#         supplymo_detaildata = supply_response_json['data'][0]
#         return supplymo_detaildata
    

#     @classmethod
#     def _get_demand_datalist(cls, demandno: str):
#         """
#         获取工单原料需求
#         Args:
#             demandno: 需求编号，根据 APS pegging 算法，也即供应号
#         Returns:
#             工单原料需求详情
#         """
#         demand_response = cls.session.get(f"{cls.this_base_url}/api/t_demand?db_name={cls.main_db}&demandno={demandno}")
#         demand_response_json = demand_response.json()
#         demand_detaildata = demand_response_json['data'][0]
#         return demand_detaildata




# def wrap_data_response(func):
#     """
#     装饰器：将数据列表封装为字典格式
#     返回格式: {'total': len(data), 'data': data}
#     """
#     def wrapper(*args, **kwargs):
#         data = func(*args, **kwargs)
#         return {
#             'total': len(data) if data else 0,
#             'data': data
#         }
#     return wrapper



