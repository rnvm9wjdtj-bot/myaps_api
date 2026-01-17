import json, base64
from pathlib import Path
from typing import List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import pandas as pd

from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
from apps.io_api.schemas import (
    BaseModel, model_validator, Field,
    AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom,
    AcceptMold, AcceptMatWcMold
    ) # 引起循环引用



class BaseConnection(ABC):
    
    def __init__(self, *args, **kwargs):
        self._session = get_session()


    @abstractmethod
    def auth(self, *args, **kwargs):
        pass

    @abstractmethod
    def _get_paged_data(self, *args, **kwargs) -> List[Dict]:
        """
        获取分页数据
        url: 请求URL
        params: 请求参数
        """
        pass

    @abstractmethod
    def data_list(self, *args, **kwargs) -> Dict:
        """
        获取数据列表
        """
        pass

    @staticmethod
    def _merge_paged_data(paged_data_iter):
        """
        合并分页数据
        """
        row_count = 0
        merged_data = []
        for page in paged_data_iter:
            row_count += len(page)
            merged_data.extend(page)
        return merged_data

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if hasattr(self, '_session') and self._session:
            self._session.close()


    @staticmethod
    def flat_merge_parent_child_data(parent_data: List[Dict], child_data: List[Dict], 
                                    parent_key_fields: str | list[str] = 'id', 
                                    child_match_key_fields: str | list[str] = 'parentid') -> List[Dict]:
        """
        合并父表和子表数据为扁平结构
        """
        union_key_col = '$index'
        # 转换为DataFrame
        df_parent = pd.DataFrame(parent_data)
        df_child = pd.DataFrame(child_data)

        parent_key_fields = parent_key_fields if isinstance(parent_key_fields, list) else [parent_key_fields]
        child_match_key_fields = child_match_key_fields if isinstance(child_match_key_fields, list) else [child_match_key_fields]

        df_parent[union_key_col] = df_parent[parent_key_fields].apply(lambda x: tuple(x), axis=1)
        df_child[union_key_col] = df_child[child_match_key_fields].apply(lambda x: tuple(x), axis=1)
        
        # 处理单字段情况
        if isinstance(parent_key_fields, str):
            parent_key_fields = [parent_key_fields]
        if isinstance(child_match_key_fields, str):
            child_match_key_fields = [child_match_key_fields]
        
        # 合并数据
        merged_df = pd.merge(
            df_parent,
            df_child,
            left_on=union_key_col,
            right_on=union_key_col,
            how='left',
            suffixes=('_parent', '_child')
        )
        
        return merged_df.to_dict(orient='records')


def wrap_data_response(func):
    """
    装饰器：将数据列表封装为字典格式
    返回格式: {'total': len(data), 'data': data}
    """
    def wrapper(*args, **kwargs):
        data = func(*args, **kwargs)
        return {
            'total': len(data) if data else 0,
            'data': data
        }
    return wrapper



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