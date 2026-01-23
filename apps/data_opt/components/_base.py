import logging, json, base64
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union, Any
from abc import ABC, abstractmethod
from Crypto.Cipher import AES
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


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_log = logging.getLogger(__name__)


def reset_default_values(model: PydanticModel, required_fields: list[str] = None, default_fields: Dict[str, Any] = None):
    """
    重置模型字段的必填、选填和默认值
    :param model: 要重置默认值的模型类
    :param required_fields: 重置为必填的字段
    :param default_fields: 重置字段的默认值
    其余字段默认值为None
    """
    required_fields = required_fields or []
    default_fields = default_fields or {}
    for field_name, field in model.model_fields.items():
        if field_name in required_fields:
            field.default = ...
            continue
        field.default = default_fields.get(field_name, None)


class BaseConnection(ABC):
    
    def __init__(self, config, *args, **kwargs):
        self._session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        pass


    @abstractmethod
    def data_list(self, *args, **kwargs) -> Dict:
        """
        获取数据列表
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



def aes_decrypt(encrypted_str: str, key: str) -> str:
    """
    AES/ECB/PKCS5Padding解密
    Args:
        encrypted_str: Base64编码的加密字符串
        key: 密钥（16/24/32字节对应AES-128/192/256）
    Returns:
        解密后的原始字符串
    """
    # Base64解码
    encrypted_bytes = base64.b64decode(encrypted_str)
    
    # 确保密钥长度符合AES要求（16, 24, 32字节）
    # 如果密钥长度不够，可以用特定方式填充（这里用null字节填充到最近的有效长度）
    key_bytes = key.encode('utf-8')
    if len(key_bytes) not in [16, 24, 32]:
        # 将密钥调整到最接近的有效长度
        valid_lengths = [16, 24, 32]
        target_length = min(valid_lengths, key=lambda x: abs(x - len(key_bytes)))
        # 用null字节填充到目标长度
        key_bytes = key_bytes.ljust(target_length, b'\0')
    # 创建AES解密器（ECB模式）
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    # 解密
    decrypted_bytes = cipher.decrypt(encrypted_bytes)
    # 去除PKCS5/PKCS7填充
    decrypted_bytes = unpad(decrypted_bytes, AES.block_size)
    # 返回UTF-8字符串
    return json.loads(decrypted_bytes.decode('utf-8'))