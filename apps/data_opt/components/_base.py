import json
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
from globalobjects import globalconst, logger as log_config, CACHE_JSON, ProjectDefaultValues as pdv

# 获取统一日志器
console_log = log_config.get_logger(__name__)
filelog_normal = log_config.get_file_logger(__name__, 'default')
filelog_error = log_config.get_file_logger(__name__, 'error')



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

