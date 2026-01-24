import logging, json
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union, Any
from abc import ABC, abstractmethod
from Crypto.Util.Padding import unpad
import pandas as pd
from pydantic import BaseModel as PydanticModel

from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.data_opt.utils.data_processor import DataProcessor
from apps.io_api.schemas import (
    BaseModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold
    )
from globalobjects import globalconst


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)


# def reset_default_values(model: PydanticModel, required_fields: list[str] = None, default_fields: Dict[str, Any] = None):
#     """
#     重置模型字段的必填、选填和默认值
#     :param model: 要重置默认值的模型类
#     :param required_fields: 重置为必填的字段
#     :param default_fields: 重置字段的默认值
#     其余字段默认值为None
#     """
#     required_fields = required_fields or []
#     default_fields = default_fields or {}
#     for field_name, field in model.model_fields.items():
#         if field_name in required_fields:
#             field.default = ...
#             continue
#         field.default = default_fields.get(field_name, None)


class BaseConnection(ABC):
    
    def __init__(self, config, *args, **kwargs):
        self._session = get_session()


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


    def __enter__(self):
        """上下文管理器入口"""
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if hasattr(self, '_session') and self._session:
            self._session.close()



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



