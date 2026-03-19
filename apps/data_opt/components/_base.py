import json
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union, Any
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
import pandas as pd
from datetime import date, datetime
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
from globalobjects import globalconst, logger as log_config, CACHE_JSON, ProjectDefaultValues as pdv

# 获取统一日志器
console_log = log_config.get_logger(__name__)
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')



class BaseConnection(ABC):
    this_base_url = THIS_BASE_URL
    main_db = MYAPS_MAIN_DB
    _session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        """
        认证连接
        """
        pass


    @abstractmethod
    def pull_from_source(self, *args, **kwargs):
        """
        从目标系统获取数据
        """
        pass


    @abstractmethod
    def push_into_target(self, *args, **kwargs):
        """
        推送数据到目标系统
        """
        pass


    # def __enter__(self):
    #     """上下文管理器入口"""
    #     return self


    # def __exit__(self, exc_type, exc_val, exc_tb):
    #     """上下文管理器出口"""
    #     if hasattr(self, '_session') and self._session:
    #         self._session.close()


    @classmethod
    def _get_supplymo_detaildata(cls, supplyno: str):
        """
        获取工单计划单详情
        Args:
            supplyno: 工单号
        Returns:
            工单计划单详情
        """
        supply_response = cls._session.get(f"{cls.this_base_url}/api/v_supply_mo/{supplyno}?db_name={cls.main_db}")
        supply_response_json = supply_response.json()
        supplymo_detaildata = supply_response_json['data'][0]
        return supplymo_detaildata

    
    @classmethod
    def _get_demand_datalist(cls, demandno: str) -> List[Dict]:
        """
        获取工单原料需求
        Args:
            demandno: 需求编号，根据 APS pegging 算法，也即供应号
        Returns:
            工单原料需求详情
        """
        demand_response = cls._session.get(f"{cls.this_base_url}/api/v_demand/{demandno}?db_name={cls.main_db}")
        demand_response_json = demand_response.json()
        demand_detaildata = demand_response_json['data']
        return demand_detaildata


    @classmethod
    def get_dategrouped_pr(cls, db_name: str=None, period: int|str=30, groupdates: Optional[str]=None, field_map: dict=None):
        """
        从数据库获取按日期分组的计划任务数据
        🅰 db_name: 账套名称，默认cls.main_db
        🅰 period: 时间周期，默认30天
        🅰 groupdates: 日期范围，默认None
        🅰 field_map: 字段映射，默认None
        """
        db_name = db_name or cls.main_db
        # response = asyncio.run(get_matdailyqtyreport(db_name=db_name, period=period, groupdates=groupdates, materialno=None))
        # data = response.get('data', [])
        response = cls._session.get(f"{cls.this_base_url}/api/v_matdailyqtyreport?db_name={db_name}&period={period}&groupdates={groupdates}")
        response.raise_for_status()
        data = response.json().get('data', [])
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