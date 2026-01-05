from typing import List, Dict, Optional, Callable, Union
from abc import ABC, abstractmethod

import pandas as pd

from apps.data_opt.utils.common import get_session, convert_timeunit, clean_value
# from apps.io_api.schemas import (AcceptMaterial) # 引起循环引用


class BaseConnection(ABC):
    
    def __init__(self):
        self._session = get_session()
        

    @abstractmethod
    def auth(self):
        pass

    @abstractmethod
    def _get_paged_data(self, url: str, params: dict = None) -> List[Dict]:
        """
        获取分页数据
        url: 请求URL
        params: 请求参数
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