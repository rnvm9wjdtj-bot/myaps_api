from typing import List, Dict, Optional, Callable, Union
import pandas as pd

from apps.data_opt.utils.common import get_session


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