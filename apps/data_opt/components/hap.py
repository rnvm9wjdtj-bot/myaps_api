"""
明道云 API v3 封装为 ORM，V2.0
"""

import os
import re
import json
import time
from typing import List, Dict, Any, Optional, Union, Literal, Generator, Type, TypeVar, NamedTuple, Generic
from datetime import datetime
from decimal import Decimal
from abc import ABC, abstractmethod

from config.settings import BASE_DIR

from ..utils.data_processor import DataProcessor
from ..utils.common import parallel_executor
from ._base import get_session, filelog_normal, filelog_error, console_log, CACHE_JSON



# 令牌桶算法实现，用于控制QPS
class TokenBucket:
    """令牌桶算法实现，用于控制QPS"""
    def __init__(self, capacity: int, refill_rate: float):
        """
        初始化令牌桶
        :param capacity: 令牌桶容量
        :param refill_rate: 令牌生成速率（每秒）
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill_time = time.time()
        import threading
        self.lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        尝试消费令牌
        :param tokens: 需要消费的令牌数
        :return: 是否成功消费
        """
        with self.lock:
            # 先补充令牌
            now = time.time()
            time_passed = now - self.last_refill_time
            new_tokens = time_passed * self.refill_rate
            
            if new_tokens > 0:
                self.tokens = min(self.capacity, self.tokens + new_tokens)
                self.last_refill_time = now
            
            # 尝试消费令牌
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                return False
    
    def wait_for_token(self, tokens: int = 1, timeout: float = None) -> bool:
        """
        等待直到获取到令牌
        :param tokens: 需要消费的令牌数
        :param timeout: 超时时间（秒）
        :return: 是否成功获取令牌
        """
        start_time = time.time()
        while True:
            if self.consume(tokens):
                return True
            
            if timeout is not None and time.time() - start_time > timeout:
                return False
            
            # 短暂睡眠，避免CPU占用过高
            time.sleep(0.01)


# 自定义JSON编码器，用于处理Decimal类型
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


# Q 类，用于构建复杂查询条件
class Q:
    """
    查询条件类，用于构建复杂的查询条件
    支持 & (AND)、| (OR) 和 ~ (NOT) 操作符
    """
    def __init__(self, *args, **kwargs):
        """
        初始化查询条件
        
        Args:
            *args: 位置参数，用于指定 isempty 或 isnotempty 操作，格式为 "field__isempty" 或 "field__isnotempty"
            **kwargs: 查询条件，格式为 field__operator=value
        """
        self.conditions = {}
        
        # 处理位置参数（用于 isempty 操作）
        for arg in args:
            if isinstance(arg, str) and ('__isempty' in arg or '__isnotempty' in arg):
                # 对于位置参数，默认使用 isempty 操作
                self.conditions[arg] = True
        
        # 处理关键字参数
        self.conditions.update(kwargs)
        
        self.connector = None
        self.children = []
        self.negated = False
    
    def __and__(self, other):
        """AND 操作符"""
        if not isinstance(other, Q):
            raise TypeError("Q object can only be combined with other Q objects")
        q = Q()
        q.connector = "AND"
        q.children = [self, other]
        return q
    
    def __or__(self, other):
        """OR 操作符"""
        if not isinstance(other, Q):
            raise TypeError("Q object can only be combined with other Q objects")
        q = Q()
        q.connector = "OR"
        q.children = [self, other]
        return q
    
    def __invert__(self):
        """NOT 操作符"""
        self.negated = not self.negated
        return self
    
    def to_filter_condition(self) -> dict:
        """
        将 Q 对象转换为明道云 API 要求的筛选条件格式
        
        Returns:
            dict: 符合明道云 API 要求的筛选条件
        """
        # 处理逻辑运算符
        if self.connector:
            children_conditions = []
            for child in self.children:
                child_condition = child.to_filter_condition()
                if child_condition:
                    children_conditions.append(child_condition)
            
            if not children_conditions:
                return {}
            
            result = {
                "type": "group",
                "logic": self.connector,
                "children": children_conditions
            }
            
            # 处理 NOT 操作
            if self.negated:
                return {
                    "type": "group",
                    "logic": "NOT",
                    "children": [result]
                }
            
            return result
        
        # 处理单个条件
        conditions = []
        for field_op, value in self.conditions.items():
            if '__' in field_op:
                field, op = field_op.split('__', 1)
                operator = op
            else:
                continue
            
            # 处理需要数组值的运算符
            array_operators = ['in', 'notin', 'contains', 'notcontains', 'concurrent', 'belongsto', 'notbelongsto', 'between', 'notbetween']
            
            if operator in array_operators:
                if isinstance(value, list):
                    condition = {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": operator,
                        "value": value
                    }
                    conditions.append(condition)
            elif operator == 'isempty':
                # 根据 value 值决定使用 isempty 还是 isnotempty
                # 当 value 为 False 时，使用 isnotempty
                actual_operator = 'isnotempty' if value is False else 'isempty'
                condition = {
                    "type": "condition",
                    "field": field.strip(),
                    "operator": actual_operator,
                    "value": []
                }
                conditions.append(condition)
            elif operator == 'isnotempty':
                # 保持向后兼容，仍然支持 isnotempty
                condition = {
                    "type": "condition",
                    "field": field.strip(),
                    "operator": operator,
                    "value": []
                }
                conditions.append(condition)
            else:
                condition = {
                    "type": "condition",
                    "field": field.strip(),
                    "operator": operator,
                    "value": value
                }
                conditions.append(condition)
        
        if not conditions:
            return {}
        
        if len(conditions) == 1:
            result = conditions[0]
        else:
            result = {
                "type": "group",
                "logic": "AND",
                "children": conditions
            }
        
        # 处理 NOT 操作
        if self.negated:
            return {
                "type": "group",
                "logic": "NOT",
                "children": [result]
            }
        
        return result


# 字段基类
class Field(ABC):
    """字段基类"""
    def __init__(self, 
                 field_name: Optional[str] = None, 
                 default: Any = None, 
                 description: Optional[str] = None,
                 ):
        self.default = default
        self.description = description
        self.field_name = field_name
        self.model: Optional[Type['Model']] = None
    
    def __set_name__(self, owner, name):
        # 当 field_name 未提供时，使用属性名作为默认值
        if self.field_name is None:
            self.field_name = name
        self.model = owner


# 文本字段
class StrField(Field):
    """文本字段"""
    def __init__(self, 
                 field_name: Optional[str] = None,
                 default: Optional[str] = None,
                 description: Optional[str] = None,
                 pk: bool = False,
                 mapper: Optional[Dict[str, str]] = None,
                 follow_with: Optional[str] = None,
                ):
        self.pk = pk
        self.mapper = mapper  # 映射字典，用于将follow_with字段的值映射成新值
        self.follow_with = follow_with  # 跟随的字段名，用于自动更新映射值
        super().__init__(field_name=field_name, default=default, description=description)
    
    def process_mapping(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理文本字段的映射关系
        
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """
        if not self.follow_with or not self.mapper:
            return data
        
        processed_data = data.copy()
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            reverse_field_map = self.model._get_reverse_field_map()
            attr_name = reverse_field_map.get(self.field_name, None)
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 检查是否需要更新映射字段
        followwith_field = self.follow_with
        if not followwith_field in processed_data:
            field_map = self.model._get_field_map()
            if followwith_field in field_map:
                followwith_field = field_map[followwith_field]
        
        # 确保 follow_with 字段存在
        if followwith_field not in processed_data:
            return processed_data
        
        need_update = False
        follow_value = processed_data[followwith_field]
        if follow_value:
            # 情况一：创建记录时
            if not original_data:
                need_update = True
            # 情况二：更新记录时，值有变化
            else:
                # 确定在 original_data 中使用的键名（字段名）
                original_key = followwith_field
                field_map = self.model._get_field_map()
                if followwith_field in field_map:
                    # 如果 followwith_field 是属性名，转换为字段名
                    original_key = field_map[followwith_field]
                
                if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], follow_value):
                    need_update = True
        
        if not need_update:
            return processed_data
        
        # 执行映射
        mapped_value = self.mapper.get(str(follow_value), None)
        if mapped_value is not None:
            processed_data[attr_name] = mapped_value
        
        return processed_data


class ChoiceField(StrField):
    """选项字段
    继承自 StrField
    ChoiceField 类型的字段会被自动处理
    与 StrField 类型的字段一样
    调用其 process_mapping 方法来处理映射关系。
    """
    def __init__(self,
                 field_name: Optional[str] = None,
                 default: Optional[str] = None,
                 description: Optional[str] = None,
                 mapper: Optional[Dict[str, str]] = None,
                 follow_with: Optional[str] = None,
                 spliter: Optional[str] = ",",
                 ):
        self.spliter = spliter
        super().__init__(field_name=field_name, default=default, description=description, pk=False, mapper=mapper, follow_with=follow_with)
    
    def process_mapping(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理选择字段的映射关系
        
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """

        processed_data = data.copy()
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            # reverse_field_map = self.model._get_reverse_field_map()
            # reverse_field_map = self.model._get_field_map()
            # attr_name = reverse_field_map.get(self.field_name, None)
            attr_name = self.field_name
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 确定要处理的值
        value_to_process = None
        if self.follow_with:
            # 有 follow_with，处理 follow_with 字段的值
            followwith_field = self.follow_with
            if not followwith_field in processed_data:
                field_map = self.model._get_field_map()
                if followwith_field in field_map:
                    followwith_field = field_map[followwith_field]
            
            # 确保 follow_with 字段存在
            if followwith_field not in processed_data:
                return processed_data
            
            # 检查是否需要更新映射字段
            need_update = False
            value_to_process = processed_data[followwith_field]
            if value_to_process:
                # 情况一：创建记录时
                if not original_data:
                    need_update = True
                # 情况二：更新记录时，值有变化
                else:
                    # 确定在 original_data 中使用的键名（字段名）
                    original_key = followwith_field
                    field_map = self.model._get_field_map()
                    if followwith_field in field_map:
                        # 如果 followwith_field 是属性名，转换为字段名
                        original_key = field_map[followwith_field]
                    
                    if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], value_to_process):
                        need_update = True
            
            if not need_update:
                return processed_data
        else:
            # 没有 follow_with，直接处理本字段的值
            if attr_name not in processed_data:
                return processed_data
            value_to_process = processed_data[attr_name]
        
        # 处理不同类型的值
        values_to_process = []
        if isinstance(value_to_process, list):
            # 直接使用 list
            values_to_process = value_to_process
        elif isinstance(value_to_process, str):
            try:
                # 尝试解析为 json
                import json
                parsed_value = json.loads(value_to_process)
                if isinstance(parsed_value, list):
                    values_to_process = parsed_value
                else:
                    # 如果不是 list，按 spliter 分割
                    values_to_process = value_to_process.split(self.spliter)
            except:
                # 解析失败，按 spliter 分割
                values_to_process = value_to_process.split(self.spliter)
        
        # 执行映射
        processed_values = []
        for value in values_to_process:
            value_str = str(value).strip()
            if self.mapper:
                # 有 mapper，执行映射
                mapped_value = self.mapper.get(value_str, value_str)
                processed_values.append(mapped_value)
            else:
                # 没有 mapper，直接使用原值
                processed_values.append(value_str)
        
        # 保留 list 形式的结果
        processed_data[attr_name] = processed_values
        
        return processed_data


# 数值字段
class NumField(Field):
    """数值字段，支持整数和浮点数"""
    def __init__(self, 
                 field_name: Optional[str] = None, 
                 default: Optional[Union[int, float]] = None, 
                 description: Optional[str] = None,
                 pk: bool = False):
        self.pk = pk
        super().__init__(field_name=field_name, default=default, description=description)


# 关联字段
class RelationField(Field):
    """关联字段"""
    def __init__(self, 
                 model: Union[Type['Model'], str], 
                 field_name: Optional[str] = None, 
                 follow_with: Optional[str] = None,
                 query_field: Optional[str] = None,  # 显式指定关联模型的查询字段，若未指定，则使用关联模型的pk
                 description: Optional[str] = None,
                 ):
        self.follow_with = follow_with  # 跟随的字段名，用于自动更新关联关系
        self.query_field = query_field  # 显式指定关联模型的查询字段
        super().__init__(field_name=field_name, default=None, description=description)
        self.related_model = model
        self.model_name = model if isinstance(model, str) else model.__name__
    
    def process_relation(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None, hap_conn: Optional['HapConnection'] = None) -> Dict[str, Any]:
        """
        处理关联字段的关联关系
        
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            hap_conn: HapConnection 实例，用于查询关联数据
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """
        if not self.follow_with:
            return data
        
        processed_data = data.copy()
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            reverse_field_map = self.model._get_reverse_field_map()
            attr_name = reverse_field_map.get(self.field_name, None)
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 确保使用 follow_with 字段，而不是关联字段本身
        # 从 processed_data 中移除关联字段本身，避免干扰
        if attr_name in processed_data:
            del processed_data[attr_name]
        
        # 检查是否需要更新关联字段
        followwith_field = self.follow_with
        if not followwith_field in processed_data:
            field_map = self.model._get_field_map()
            if followwith_field in field_map:
                followwith_field = field_map[followwith_field]
        
        # 确保 follow_with 字段存在
        if followwith_field not in processed_data:
            return processed_data
        
        need_update = False
        code_value = str(processed_data[followwith_field])
        if code_value:
            # 情况一：创建记录时
            if not original_data:
                need_update = True
            # 情况二：更新记录时，值有变化
            else:
                # 确定在 original_data 中使用的键名（字段名）
                original_key = followwith_field
                field_map = self.model._get_field_map()
                if followwith_field in field_map:
                    # 如果 followwith_field 是属性名，转换为字段名
                    original_key = field_map[followwith_field]
                
                if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], code_value):
                    need_update = True
        
        if not need_update or not hap_conn:
            return processed_data
        
        # 处理延时导入的模型
        if isinstance(self.related_model, str):
            # 从 hap_conn 中获取注册的模型类
            related_model = hap_conn.get_model(self.related_model)
        else:
            related_model = self.related_model
        
        try:
            # 优先从缓存中获取数据
            relation_data = []
            
            # 处理逗号分隔的值
            code_values = [v.strip() for v in str(code_value).split(',')] if isinstance(code_value, str) else [code_value]
            
            # 检查缓存是否存在
            if hasattr(hap_conn, 'cache_data') and hasattr(hap_conn, 'cache_indexes'):
                worksheet_id = related_model.get_worksheet_id()
                cache_key = followwith_field
                if worksheet_id in hap_conn.cache_indexes:
                    # 确定缓存中使用的键名（字段名）
                    if self.query_field:
                        # 使用显式指定的查询字段
                        cache_key = cache_key
                    else:
                        # 未指定查询字段，使用关联模型的主键字段
                        pk_field = related_model.get_pk_field()
                        if pk_field:
                            # 获取主键字段的 field_name
                            pk_field_obj = related_model._get_fields().get(pk_field)
                            if pk_field_obj:
                                cache_key = pk_field_obj.field_name
                            else:
                                cache_key = pk_field
                        else:
                            # 无法确定查询字段，使用默认值
                            cache_key = followwith_field
                    
                    # 检查是否有 code_field_name 的索引
                    if cache_key in hap_conn.cache_indexes[worksheet_id]:
                        # 从索引中查找每个 code_value 对应的 row_id
                        for cv in code_values:
                            if cv in hap_conn.cache_indexes[worksheet_id][cache_key]:
                                row_id = hap_conn.cache_indexes[worksheet_id][cache_key][cv]
                                # 从缓存数据中获取完整信息
                                if worksheet_id in hap_conn.cache_data and row_id in hap_conn.cache_data[worksheet_id]:
                                    # 构建关联字段数据，只需要传入 rowid
                                    relation_data.append(row_id)
            
            # 缓存中没有，从 API 查询
            if not relation_data:
                # 确定查询时使用的字段名
                if self.query_field:
                    # 使用显式指定的查询字段
                    query_field = self.query_field
                else:
                    # 未指定查询字段，使用关联模型的主键字段
                    pk_field = related_model.get_pk_field()
                    if pk_field:
                        # 获取主键字段的 field_name
                        pk_field_obj = related_model._get_fields().get(pk_field)
                        if pk_field_obj:
                            query_field = pk_field_obj.field_name
                        else:
                            query_field = pk_field
                    else:
                        # 无法确定查询字段，使用默认值
                        query_field = followwith_field
                
                # 构建查询条件，使用 in 操作符
                if len(code_values) > 1:
                    # 多个值使用 in 操作符
                    from .hap import Q
                    filter_expr = Q(**{f"{query_field}__in": code_values})
                    related_instances = hap_conn.rows(related_model).filter(filter_expr).all()
                    for instance in related_instances.row_objects:
                        if hasattr(instance, 'row_id'):
                            relation_data.append(instance.row_id)
                            # 将查询结果添加到缓存中
                            hap_conn._update_cache_for_instance(instance)
                else:
                    # 单个值使用 eq 操作符
                    from .hap import Q
                    filter_expr = Q(**{f"{query_field}__eq": code_values[0]})
                    related_instance = hap_conn.rows(related_model).filter(filter_expr).all().first()
                    if related_instance and hasattr(related_instance, 'row_id'):
                        relation_data = [related_instance.row_id]
                        # 将查询结果添加到缓存中
                        hap_conn._update_cache_for_instance(related_instance)
            
            # 更新关联字段数据
            if relation_data:
                processed_data[attr_name] = relation_data
        except Exception as e:
            # 忽略查询错误，保持原始数据
            pass
        
        return processed_data


class SubtableField(Field):
    """子表字段"""
    def __init__(
        self,
        model: Type['Model'],
        data_source: str,   # 以 model 中哪个字段为数据源
        field_name: str = None,
        description: str = None
        ):
        super().__init__(field_name=field_name, description=description)
        self.subtable_model = model  # 使用 subtable_model 存储子表 model
        self.data_source = data_source  # 数据源字段名
    
    def process_subtable(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None, hap_conn: Optional['HapConnection'] = None) -> Dict[str, Any]:
        """
        处理子表字段的数据
        
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            hap_conn: HapConnection 实例，用于操作子表数据
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """
        if not self.data_source or not hap_conn:
            return data
        
        processed_data = data.copy()
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            parent_reverse_field_map = self.model._get_reverse_field_map()
            attr_name = parent_reverse_field_map.get(self.field_name, None)
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 确保使用 data_source 字段，而不是子表字段本身
        # 从 processed_data 中移除子表字段本身，避免干扰
        if attr_name in processed_data:
            del processed_data[attr_name]
        
        # parent_row = hap_conn.rows(self.model).get_by_rowid(row_id=processed_data.get('row_id'))
        parent_field_map = self.model._get_field_map()
        subtable_field_map = self.subtable_model._get_field_map()
        # 检查数据源字段是否存在
        data_source_field = self.data_source
        if not data_source_field in processed_data:
            if data_source_field in parent_field_map:
                data_source_field = parent_field_map[data_source_field]
        
        # 确保数据源字段存在
        if data_source_field not in processed_data:
            return processed_data
        
        need_update = False
        source_value = processed_data[data_source_field]
        if source_value:
            # 情况一：创建记录时
            if not original_data:
                need_update = True
            # 情况二：更新记录时，值有变化
            else:
                # 确定在 original_data 中使用的键名（字段名）
                original_key = data_source_field
                if data_source_field in parent_field_map:
                    # 如果 data_source_field 是属性名，转换为字段名
                    original_key = parent_field_map[data_source_field]
                
                if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], source_value):
                    need_update = True
        
        if not need_update:
            return processed_data
        
        try:
            # 解析数据源为字典列表
            if isinstance(source_value, str):
                subtable_data_list = json.loads(source_value)
            elif isinstance(source_value, list):
                subtable_data_list = source_value
            else:
                return processed_data
            
            # 确保是字典列表
            if not isinstance(subtable_data_list, list) or not all(isinstance(item, dict) for item in subtable_data_list):
                return processed_data
            
            # 获取子表模型的冲突字段
            conflict_fields = getattr(self.subtable_model.Meta, 'conflict_fields', None)
            
            # 获取子表模型的主键字段
            subtable_pk_field = self.subtable_model.get_pk_field()
            subtable_pk_field_name = subtable_field_map[subtable_pk_field] if subtable_pk_field else None
            # 预处理子表数据：确保字段名能够被正确地映射到模型的属性名
            preprocessed_data_list = []
            
            for subtable_data in subtable_data_list:
                # 使用工具方法将 API 字段名映射到模型属性名
                preprocessed_data = HapUtils.map_api_fields_to_model_attrs(self.subtable_model, subtable_data)
                
                # 确保所有需要的字段都存在
                for sub_attr_name, field_obj in self.subtable_model._get_fields().items():
                    # 处理关联字段的 follow_with
                    if isinstance(field_obj, RelationField) and field_obj.follow_with:
                        follow_with = field_obj.follow_with
                        # 检查 follow_with 字段是否存在
                        if follow_with not in preprocessed_data:
                            # 尝试从原始数据中获取
                            subtable_field_map = self.subtable_model._get_field_map()
                            if follow_with in subtable_field_map:
                                api_field = subtable_field_map[follow_with]
                                if api_field in subtable_data:
                                    preprocessed_data[follow_with] = subtable_data[api_field]
                
                preprocessed_data_list.append(preprocessed_data)
            
            # 检查子表模型是否既没有 pk 也没有 conflict fields
            subtable_has_pk_or_conflict = bool(subtable_pk_field or conflict_fields)
            
            # 如果子表模型既没有 pk 也没有 conflict fields，先删除主表当前挂载的子表记录
            if not subtable_has_pk_or_conflict:
                # 获取主记录当前挂载的子表记录 row_id
                current_row_ids = []
                if attr_name in processed_data:
                    current_row_ids = processed_data[attr_name]
                elif original_data and attr_name in original_data:
                    current_row_ids = original_data[attr_name]
                
                # 确保 current_row_ids 是列表
                if not isinstance(current_row_ids, list):
                    current_row_ids = []
                
                # 删除当前挂载的子表记录
                if current_row_ids:
                    try:
                        # 构建删除请求
                        endpoint = f"/v3/app/worksheets/{self.subtable_model.get_worksheet_id()}/rows/batch"
                        
                        # 构建请求体
                        payload = {
                            "rowIds": current_row_ids,
                            "triggerWorkflow": True
                        }
                        
                        # 发送请求
                        response = hap_conn._delete(endpoint=endpoint, payload=payload)
                        
                        # 从缓存中移除
                        for row_id in current_row_ids:
                            hap_conn._remove_from_cache(row_id)
                    except Exception as e:
                        # 忽略删除错误，继续处理其他记录
                        pass
            
            # 处理子表数据：复用 HapRowSet.upsert 方法
            # 创建空的 HapRowSet 实例
            row_set = HapRowSet(models=[], model=self.subtable_model, hap_conn=hap_conn)
            
            # 执行 upsert 操作
            upserted_row_set = row_set.upsert(preprocessed_data_list)
            
            # 收集处理后的子表记录 row_id
            subtable_row_ids = []
            
            # 直接检查 row_objects
            for model_instance in upserted_row_set.row_objects:
                if hasattr(model_instance, 'row_id'):
                    subtable_row_ids.append(model_instance.row_id)
            
            # 即使 row_objects 不为空，也尝试直接查询子表记录，确保获取所有记录的 row_id
            # 构建查询条件
            filter_conditions = []
            # subtable_reverse_field_map = self.subtable_model._get_reverse_field_map()
            
            for subtable_data in preprocessed_data_list:
                # 优先使用主键字段
                # pk_field = self.subtable_model.get_pk_field()
                if subtable_pk_field and subtable_pk_field in subtable_data:
                    match_value = subtable_data[subtable_pk_field]
                    # 获取主键字段的 API 字段名
                    api_pk_field = subtable_field_map.get(subtable_pk_field, subtable_pk_field)
                    filter_conditions.append(f'{api_pk_field}__eq="{match_value}"')
                # 其次使用冲突字段
                elif hasattr(self.subtable_model.Meta, 'conflict_fields'):
                    conflict_fields = self.subtable_model.Meta.conflict_fields
                    for field in conflict_fields:
                        if field in subtable_data:
                            match_value = subtable_data[field]
                            # 获取冲突字段的 API 字段名
                            api_field = subtable_field_map.get(field, field)
                            filter_conditions.append(f'{api_field}__eq="{match_value}"')
            
            # 如果有查询条件，执行查询
            if filter_conditions:
                try:
                    query = hap_conn.rows(self.subtable_model)
                    query = query.filter(" || ".join(filter_conditions))
                    queried_rows = query.all()
                    for model_instance in queried_rows.row_objects:
                        if hasattr(model_instance, 'row_id') and model_instance.row_id not in subtable_row_ids:
                            subtable_row_ids.append(model_instance.row_id)
                except Exception as e:
                    pass
            
            ## 删除不在 data_source 中的子表记录
            ## 获取主记录当前挂载的子表记录 row_id
            # current_row_ids = []
            # if attr_name in processed_data:
            #     current_row_ids = processed_data[attr_name]
            # elif original_data and attr_name in original_data:
            #     current_row_ids = original_data[attr_name]
            
            # # 确保 current_row_ids 是列表
            # if not isinstance(current_row_ids, list):
            #     current_row_ids = []
            
            # # 找出需要删除的子表记录
            # rows_to_delete = []
            # for row_id in current_row_ids:
            #     if row_id not in subtable_row_ids:
            #         # 尝试获取对应的模型实例
            #         try:
            #             query = hap_conn.rows(self.subtable_model)
            #             # 使用 row_id 直接查询
            #             query = query.filter(Q(**{f"row_id__eq": row_id}))
            #             existing_row = query.first()
            #             if existing_row:
            #                 rows_to_delete.append(existing_row)
            #         except Exception as e:
            #             # 忽略查询错误，继续处理其他记录
            #             pass
            
            # # 删除不需要保留的子表记录
            # if rows_to_delete:
            #     # 创建包含需要删除记录的 HapRowSet 实例
            #     delete_row_set = HapRowSet(models=rows_to_delete, model=self.subtable_model, hap_conn=hap_conn)
            #     # 执行删除操作
            #     delete_row_set.delete()

            # 将子表记录的 row_id 挂载到当前主记录
            if subtable_row_ids:
                processed_data[attr_name] = subtable_row_ids
            else:
                # 如果没有子表记录，清空主记录的子表字段
                processed_data[attr_name] = []
        except Exception as e:
            # 添加错误日志，以便于调试
            import traceback
            print(f"Error processing subtable field: {e}")
            print(traceback.format_exc())

        return processed_data


# TODO 选项集属性
# class ChoiceProperty(NamedTuple):
#     """单个选项属性"""
#     key: str
#     value: str
#     index: int
#     score: float = 0.0
#     is_delete: bool = False



# Model基类
ModelType = TypeVar('ModelType', bound='Model')

class Model(ABC):
    """模型基类"""
    
    class Meta:
        """模型配置类"""
        worksheet_id: str
        conflict_fields: Optional[List[str]] = None
        cache: Optional[List[str]] = None
    
    def __init__(self, **kwargs):
        # 首先处理特殊属性
        if 'hap_conn' in kwargs:
            self.hap_conn = kwargs.pop('hap_conn')
        
        # 获取反向字段映射（field_name 到属性名）
        reverse_field_map = self._get_reverse_field_map()
        
        # 处理所有关键字参数
        for key, value in kwargs.items():
            # 通过 field_name 映射设置属性（优先）
            if key in reverse_field_map:
                attr_name = reverse_field_map[key]
                setattr(self, attr_name, value)
            # 直接设置属性（作为后备）
            elif hasattr(self, key):
                setattr(self, key, value)
        
        # 设置刷新时间戳
        self.refresh_stamp = datetime.now().timestamp()
    
    @classmethod
    def _get_fields(cls) -> Dict[str, Field]:
        """获取模型的所有字段"""
        if not hasattr(cls, '_fields_cache'):
            fields = {}
            for attr_name in dir(cls):
                attr = getattr(cls, attr_name)
                if isinstance(attr, Field):
                    fields[attr_name] = attr
            cls._fields_cache = fields
        return cls._fields_cache
    
    @classmethod
    def _get_field_map(cls) -> Dict[str, str]:
        """获取属性名到field_name的映射"""
        if not hasattr(cls, '_field_map_cache'):
            field_map = {}
            fields = cls._get_fields()
            for attr_name, field in fields.items():
                field_map[attr_name] = field.field_name
            cls._field_map_cache = field_map
        return cls._field_map_cache
    
    @classmethod
    def _get_reverse_field_map(cls) -> Dict[str, str]:
        """获取field_name到属性名的映射"""
        if not hasattr(cls, '_reverse_field_map_cache'):
            reverse_field_map = {}
            fields = cls._get_fields()
            for attr_name, field in fields.items():
                reverse_field_map[field.field_name] = attr_name
            cls._reverse_field_map_cache = reverse_field_map
        return cls._reverse_field_map_cache
    
    @classmethod
    def clear_field_caches(cls) -> None:
        """清理字段相关的缓存"""
        # 清理字段缓存
        if hasattr(cls, '_fields_cache'):
            delattr(cls, '_fields_cache')
        # 清理字段映射缓存
        if hasattr(cls, '_field_map_cache'):
            delattr(cls, '_field_map_cache')
        # 清理反向字段映射缓存
        if hasattr(cls, '_reverse_field_map_cache'):
            delattr(cls, '_reverse_field_map_cache')
    
    def __setattr__(self, name, value):
        """设置属性值时清理缓存"""
        # 如果设置的是字段属性，清理缓存
        if name not in ['hap_conn', 'row_id']:
            # 检查是否是字段属性
            try:
                fields = self._get_fields()
                if name in fields:
                    # 清理缓存
                    self.__class__.clear_field_caches()
            except Exception:
                pass
        super().__setattr__(name, value)
    
    def get_field_by_name(self, name: str) -> Optional[Field]:
        """通过属性名获取字段对象"""
        fields = self._get_fields()
        return fields.get(name)
    
    def get_field_by_field_name(self, field_name: str) -> Optional[Field]:
        """通过field_name获取字段对象"""
        reverse_map = self._get_reverse_field_map()
        attr_name = reverse_map.get(field_name)
        if attr_name:
            fields = self._get_fields()
            return fields.get(attr_name)
        return None
    
    def get_attribute_by_field_name(self, field_name: str) -> Optional[Any]:
        """通过field_name获取属性值"""
        reverse_map = self._get_reverse_field_map()
        attr_name = reverse_map.get(field_name)
        if attr_name and hasattr(self, attr_name):
            return getattr(self, attr_name)
        return None
    
    def set_attribute_by_field_name(self, field_name: str, value: Any) -> None:
        """通过field_name设置属性值"""
        reverse_map = self._get_reverse_field_map()
        attr_name = reverse_map.get(field_name)
        if attr_name:
            setattr(self, attr_name, value)
    
    @classmethod
    def _get_field_names(cls) -> List[str]:
        """获取模型的所有字段名"""
        return list(cls._get_fields().keys())
    
    @classmethod
    def get_worksheet_id(cls) -> str:
        """获取工作表ID"""
        return cls.Meta.worksheet_id
    
    @classmethod
    def get_conflict_fields(cls) -> Optional[List[str]]:
        """获取冲突字段"""
        return getattr(cls.Meta, 'conflict_fields', None)
    
    @classmethod
    def get_pk_field(cls) -> Optional[str]:
        """获取主键字段名"""
        fields = cls._get_fields()
        pk_fields = [field_name for field_name, field in fields.items() if hasattr(field, 'pk') and field.pk]
        # 确保每个模型只有一个主键
        if len(pk_fields) > 1:
            raise ValueError("Model can only have one primary key")
        return pk_fields[0] if pk_fields else None
    
    def update(self, **kwargs) -> 'Model':
        """更新模型实例
        
        Args:
            **kwargs: 要更新的字段和值
            when_value_equal_then: 当字段值相等时的处理方式，默认'jumpover' 跳过，'update' 则无论字段是否与data一样都更新
            
        Returns:
            Model: 更新后的模型实例
        """
        # 检查模型实例是否有 row_id
        if not hasattr(self, 'row_id'):
            raise ValueError("Model instance must have a row_id to update")
        
        # 获取 when_value_equal_then 参数
        when_value_equal_then = kwargs.pop('when_value_equal_then', 'jumpover')
        
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 获取模型实例的原始数据
        original_data = self.to_dict()
        
        # 直接使用传入的 kwargs，不再调用 _process_complex_fields
        # 因为在 upsert 操作中已经处理过了
        processed_data = kwargs
        
        # 比较字段值差异，只包含变化的字段
        changed_data = {}
        if when_value_equal_then == 'update':
            # 无论字段值是否变化，都更新
            changed_data = processed_data
        else:
            # 只包含变化的字段
            from apps.data_opt.utils.data_processor import DataProcessor
            for key, value in processed_data.items():
                # 确定在 original_data 中使用的键名
                original_key = key
                if key in field_map:
                    original_key = field_map[key]
                elif key in original_data:
                    original_key = key
                
                # 检查字段值是否变化
                if original_key in original_data and not DataProcessor.is_equal(original_data[original_key], value):
                    changed_data[key] = value
                # if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], value):
                #     changed_data[key] = value
        
        # 如果没有变化的字段，直接返回
        if not changed_data:
            return self
        
        # 构建更新请求
        endpoint = f"/v3/app/worksheets/{self.__class__.get_worksheet_id()}/rows/batch"
        
        # 转换数据为字段列表，使用字段映射，保留未注册的字段
        fields_list = HapUtils.convert_data_to_fieldslist(changed_data, field_map=field_map, model=self, remain_irrelevant_fields=True)
        
        # 构建请求体
        payload = {
            "rowIds": [self.row_id],
            "fields": fields_list,
            "triggerWorkflow": True
        }
        
        # 发送请求
        # from .hap import HapConnection
        # 检查是否有 hap_conn 属性
        if not hasattr(self, 'hap_conn'):
            raise ValueError("Model instance must have a hap_conn attribute to update")
        
        response = self.hap_conn._patch(endpoint=endpoint, payload=payload)
        
        # 处理响应
        if response.get('success'):
            # 更新模型实例的属性
            for key, value in kwargs.items():
                setattr(self, key, value)
            return self
        else:
            err_msg = response.get('error_msg', 'Unknown error')
            raise Exception(f"更新失败，HAP返回错误信息: {err_msg}")
    
    def to_dict(self) -> Dict[str, Any]:
        """将模型实例转换为字典"""
        data = {}
        fields = self._get_fields()
        
        # 首先添加所有注册的字段
        for attr_name, field in fields.items():
            if hasattr(self, attr_name):
                # 使用 field_name 作为字典键
                data[field.field_name] = getattr(self, attr_name)
        
        # 然后添加所有未注册的字段（不包括特殊属性）
        special_attrs = ['hap_conn', 'row_id', '_fields_cache', '_field_map_cache', '_reverse_field_map_cache']
        for attr_name in dir(self):
            # 跳过私有属性、方法和特殊属性
            if not attr_name.startswith('_') and not callable(getattr(self, attr_name)) and attr_name not in special_attrs:
                # 检查是否已经在注册字段中
                if attr_name not in fields:
                    # 尝试使用属性名作为字段名
                    data[attr_name] = getattr(self, attr_name)
        
        return data
    
    def get_relation_detail(self, field_name: str) -> List[Dict[str, Any]]:
        """
        获取关联字段的详细信息
        
        Args:
            field_name: 关联字段名称
            
        Returns:
            List[Dict[str, Any]]: 关联字段的详细信息列表
        """
        if not hasattr(self, field_name):
            return []
        
        relation_data = getattr(self, field_name)
        if not isinstance(relation_data, list):
            return []
        
        return relation_data
    
    def get_relation_ids(self, field_name: str) -> List[str]:
        """
        获取关联字段的所有 sid（rowid）
        
        Args:
            field_name: 关联字段名称
            
        Returns:
            List[str]: 关联 ID 列表
        """
        relation_data = self.get_relation_detail(field_name)
        return [item.get('sid') for item in relation_data if 'sid' in item]
    
    def refresh(self) -> 'Model':
        """从服务器刷新模型数据
        
        Returns:
            Model: 刷新后的模型实例
        """
        if not hasattr(self, 'row_id'):
            raise ValueError("Model instance must have a row_id to refresh")
        
        # 检查是否在刷新间隔内
        if datetime.now().timestamp() - self.refresh_stamp < self.hap_conn.refresh_interval_seconds:
            return self
        
        # 从服务器获取最新数据
        endpoint = f"/v3/app/worksheets/{self.__class__.get_worksheet_id()}/rows/detail"
        params = {
            "rowId": self.row_id
        }
        
        response = self.hap_conn._get(endpoint=endpoint, params=params)
        
        if response.get('success'):
            row_dict = response.get('data', {})
            # 处理行数据
            processed_data = HapUtils.process_choice_fields(row_dict)
            processed_data = HapUtils.exclude_unamed_fields(processed_data)
            processed_data = HapUtils.exclude_sys_fields(processed_data)
            
            # 更新模型实例的属性
            reverse_field_map = self._get_reverse_field_map()
            for key, value in processed_data.items():
                # 通过 field_name 映射设置属性（优先）
                if key in reverse_field_map:
                    attr_name = reverse_field_map[key]
                    setattr(self, attr_name, value)
                # 直接设置属性（作为后备）
                elif hasattr(self, key):
                    setattr(self, key, value)
            
            # 更新刷新时间戳
            self.refresh_stamp = datetime.now().timestamp()
        
        return self


# 工具类，包含通用方法
class HapUtils:
    """
    明道云工具类，包含通用方法
    """
    
    @staticmethod
    def normalize_field_name(model, field_identifier: str) -> str:
        """
        将属性名或 field_name 标准化为 field_name
        
        Args:
            model: 模型类
            field_identifier: 属性名或 field_name
            
        Returns:
            str: 标准化后的 field_name
        """
        if not model:
            return field_identifier
        
        # 检查是否已经是 field_name
        try:
            reverse_map = model._get_reverse_field_map()
            if field_identifier in reverse_map:
                return field_identifier
        except Exception:
            pass
        
        # 检查是否是属性名
        try:
            field_map = model._get_field_map()
            if field_identifier in field_map:
                return field_map[field_identifier]
        except Exception:
            pass
        
        # 如果都不是，返回原标识符
        return field_identifier
    
    @staticmethod
    def normalize_data_fields(model, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化数据字典的字段名，将属性名转换为 field_name
        
        Args:
            model: 模型类
            data: 数据字典
            
        Returns:
            Dict[str, Any]: 标准化后的字段名
        """
        if not model or not data:
            return data
        
        normalized_data = {}
        for key, value in data.items():
            normalized_key = HapUtils.normalize_field_name(model, key)
            normalized_data[normalized_key] = value
        return normalized_data
    
    @staticmethod
    def map_api_fields_to_model_attrs(model, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        将 API 字段名映射到模型属性名
        
        Args:
            model: 模型类
            data: 数据字典，键为 API 字段名
            
        Returns:
            Dict[str, Any]: 映射后的数据字典，键为模型属性名
        """
        if not model or not data:
            return data
        
        mapped_data = {}
        reverse_field_map = model._get_reverse_field_map()
        
        for api_field, value in data.items():
            # 尝试将 API 字段名映射到模型属性名
            if api_field in reverse_field_map:
                model_attr = reverse_field_map[api_field]
                mapped_data[model_attr] = value
            else:
                # 如果无法映射，保留原字段名
                mapped_data[api_field] = value
        
        return mapped_data
    
    @staticmethod
    def convert_data_to_fieldslist(data: Dict[str, Any], exclude_none: bool = True, ignore_fields=[], field_map={}, remain_irrelevant_fields=True, model=None) -> List[Dict[str, Any]]:
        """
        将单个数据字典转换为工作表API字段值list
        
        Args:
            data: 行数据字典
            exclude_none: 是否排除值为None的字段
            ignore_fields: 忽略的字段列表
            field_map: 字段名称映射规则，将row_data_dict中的字段名称（键）映射为目标工作表control_id
            remain_irrelevant_fields: 是否保留 field_map 未提及的字段
            model: 当前的模型类，用于判断字段类型
            
        Returns:
            List[Dict[str, Any]]: 字段值列表
        """
        
        if exclude_none:
            data = {k: v for k, v in data.items() if v is not None}
        else:
            data = data
        
        fieldlist = []
        for k, v in data.items():
            if k in ignore_fields: 
                continue
            
            # 标准化字段名，将属性名或field_name转换为field_name
            normalized_key = HapUtils.normalize_field_name(model, k)
            
            try:
                control_id = field_map.get(k, normalized_key)
            except:
                if remain_irrelevant_fields:
                    control_id = normalized_key
                else:
                    continue

            v_type = type(v)
            if v_type in (dict, list):
                # 检查是否需要 json.dumps
                need_json_dumps = True
                if model:
                    # 获取反向字段映射（field_name 到属性名）
                    reverse_field_map = model._get_reverse_field_map()
                    # 获取字段名（属性名）
                    field_name = reverse_field_map.get(control_id, k)
                    # 获取字段对象
                    field_obj = getattr(model, field_name, None)
                    # 检查字段类型
                    if hasattr(field_obj, '__class__'):
                        field_class_name = field_obj.__class__.__name__
                        # 如果不是文本字段，保留原格式
                        if field_class_name not in ['TextField']:
                            need_json_dumps = False
                
                if need_json_dumps:
                    fieldlist.append({'id': control_id, 'value': json.dumps(v, ensure_ascii=False, cls=DecimalEncoder)})
                else:
                    fieldlist.append({'id': control_id, 'value': v})
            elif v_type in (int, float, Decimal):
                fieldlist.append({'id': control_id, 'value': float(v), 'type': 2})
            elif v_type == str:
                fieldlist.append({'id': control_id, 'value': v, 'type': 2})
            else:
                # 处理枚举类型
                if hasattr(v, 'value'):
                    fieldlist.append({'id': control_id, 'value': v.value, 'type': 2})
                else:
                    # 其他类型，尝试转换为字符串
                    fieldlist.append({'id': control_id, 'value': str(v), 'type': 2})
        
        return fieldlist
    

    @staticmethod
    def expression_to_filter_condition(expression):
        """
        将逻辑表达式字符串转换为筛选条件JSON结构

        参数:
            expression: 逻辑表达式字符串，格式如 "(age__gt=18 && status__in=[\"active\",\"pending\"]) || name__isempty"
            
        返回:
            符合明道云API要求的筛选条件JSON结构
        """
        # 处理None值
        if expression is None:
            return {}
        
        # 去除空白字符
        expression = ''.join(expression.split())
        
        def parse(expression):
            # 辅助函数：解析表达式
            
            # 处理括号嵌套
            def find_matching_bracket(expr, start):
                # 找到匹配的右括号索引
                count = 1
                for i in range(start + 1, len(expr)):
                    if expr[i] == '(':
                        count += 1
                    elif expr[i] == ')':
                        count -= 1
                        if count == 0:
                            return i
                return -1
            
            # 如果表达式被括号包围，先解析括号内的内容
            if expression.startswith('(') and find_matching_bracket(expression, 0) == len(expression) - 1:
                return parse(expression[1:-1])
            
            # 查找最高级别的逻辑运算符（先||，后&&）
            bracket_level = 0
            or_pos = -1
            and_pos = -1
            
            for i, char in enumerate(expression):
                if char == '(':
                    bracket_level += 1
                elif char == ')':
                    bracket_level -= 1
                elif bracket_level == 0:
                    if char == '|' and i + 1 < len(expression) and expression[i + 1] == '|':
                        or_pos = i
                        break
                    elif char == '&' and i + 1 < len(expression) and expression[i + 1] == '&':
                        and_pos = i
            
            # 如果找到OR运算符
            if or_pos != -1:
                left = parse(expression[:or_pos])
                right = parse(expression[or_pos + 2:])
                return {
                    "type": "group",
                    "logic": "OR",
                    "children": [left, right]
                }
            
            # 如果找到AND运算符
            elif and_pos != -1:
                left = parse(expression[:and_pos])
                right = parse(expression[and_pos + 2:])
                return {
                    "type": "group",
                    "logic": "AND",
                    "children": [left, right]
                }
            
            # 否则，这是一个条件表达式
            else:
                # 处理 isempty 和 isnotempty 不带等号的情况
                if '__isempty' in expression:
                    field = expression.replace('__isempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isempty",
                        "value": []
                    }
                elif '__isnotempty' in expression:
                    field = expression.replace('__isnotempty', '')
                    return {
                        "type": "condition",
                        "field": field.strip(),
                        "operator": "isnotempty",
                        "value": []
                    }
                # 处理带等号的情况
                elif '=' in expression:
                    # 分割字段名（包含运算符）和值
                    field_op, value = expression.split('=', 1)
                    
                    # 分割字段名和运算符
                    if '__' in field_op:
                        field, op = field_op.split('__', 1)
                        operator = op
                    else:
                        return {}
                    
                    # 处理需要数组值的运算符
                    array_operators = ['in', 'notin', 'contains', 'notcontains', 'concurrent', 'belongsto', 'notbelongsto', 'between', 'notbetween']
                    
                    if operator in array_operators:
                        # 解析数组格式的值
                        if value.startswith('[') and value.endswith(']'):
                            import json
                            try:
                                array_value = json.loads(value)
                                if isinstance(array_value, list):
                                    return {
                                        "type": "condition",
                                        "field": field.strip(),
                                        "operator": operator,
                                        "value": array_value
                                    }
                            except:
                                pass
                    
                    # 处理普通运算符，去除字符串值的双引号
                    if operator not in array_operators:
                        # 移除字符串值的双引号
                        stripped_value = value.strip()
                        if stripped_value.startswith('"') and stripped_value.endswith('"'):
                            stripped_value = stripped_value[1:-1]
                        return {
                            "type": "condition",
                            "field": field.strip(),
                            "operator": operator,
                            "value": stripped_value
                        }
                return {}
        
        return parse(expression)
    

    @staticmethod
    def str_to_sort_list(sorts: str) -> list:
        """
        将排序字符串转换为排序列表
        
        Args:
            sorts: 排序字符串，格式如 "-x,y"（负号表示降序，正号或无符号表示升序）
            
        Returns:
            list: 排序列表，格式如 [{"field":"x","isAsc":False},{"field":"y","isAsc":True}]
        """
        if not sorts:
            return []
        sort_fields = sorts.split(',')
        sort_list = []
        for field_str in sort_fields:
            field_str = field_str.strip()
            if not field_str:
                continue
            
            # 检查是否以负号开头
            if field_str.startswith('-'):
                field = field_str[1:].strip()
                is_asc = False
            else:
                # 移除可能的正号
                field = field_str.lstrip('+').strip()
                is_asc = True
            
            if field:
                sort_list.append({"field": field, "isAsc": is_asc})
        return sort_list
    

    @staticmethod
    def exclude_sys_fields(data: dict) -> dict:
        """
        排除系统字段
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 排除系统字段后的数据字典
        """
        filtered_data = {}
        for k, v in data.items():
            if not k.startswith('_'):
                filtered_data[k] = v
        return filtered_data
    

    @staticmethod
    def exclude_unamed_fields(data: dict) -> dict:
        """
        排除未命名字段（UUID格式的字段）
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 排除未命名字段后的数据字典
        """
        # 匹配18-24个十六进制字符的正则表达式（不区分大小写）
        uuid_pattern = r'^[0-9a-f]{18,24}$'
        filtered_data = {}
        for k, v in data.items():
            # 检查键名是否匹配UUID格式
            if not re.match(uuid_pattern, k.lower()):
                filtered_data[k] = v
        return filtered_data
    

    @staticmethod
    def process_choice_fields(data: dict) -> dict:
        """
        处理选项字段，将选项字段（list of dict with key and value）转换为逗号分隔的字符串
        
        Args:
            data: 数据字典
            
        Returns:
            dict: 处理后的数据字典
        """
        processed_data = {}
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'key' in v[0] and 'value' in v[0]:
                # 选项字段，提取 value 并用逗号连接
                picked_options = [item['value'] for item in v]
                processed_data[k] = ','.join(picked_options)
            else:
                processed_data[k] = v
        return processed_data



class HapConfig:
    _SAAS_ENV = "https://api.mingdao.com"
    MAX_WORKERS = os.cpu_count() * 3
    # 调用刷新函数时，距离上次刷新超过这个秒数，才会刷新行数据，否则直接返回缓存数据
    REFRESH_INTERVAL_SECONDS = 60
    BASE_URL = CACHE_JSON.get("hap", {}).get("base_url", _SAAS_ENV)
    # QPS 限制，SAAS环境默认 50，私有部署默认 100
    QPS_LIMIT = 50 if BASE_URL == _SAAS_ENV else 100
    APP_KEY = CACHE_JSON.get("hap", {}).get("app_key", "")
    SIGN = CACHE_JSON.get("hap", {}).get("sign", "")
    DESCRIPTION = CACHE_JSON.get("hap", {}).get("description", "")



class HapConnection:
    def __init__(self, config: HapConfig=HapConfig):
        self.config = config
        self.base_url = config.BASE_URL
        self.app_key = config.APP_KEY
        self.sign = config.SIGN
        self.description = config.DESCRIPTION
        self.max_workers = config.MAX_WORKERS
        self.refresh_interval_seconds = config.REFRESH_INTERVAL_SECONDS
        self.qps_limit = getattr(config, 'QPS_LIMIT', 50)  # 从配置中读取QPS限制，默认为50
        self.models: Dict[str, Type[Model]] = {}
        self.headers = {
            'HAP-Appkey': self.app_key,
            'HAP-Sign': self.sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        # 缓存结构，包含数据和索引
        self.cache_data: Dict[str, Dict[str, Dict[str, Any]]] = {}  # 以 rowid 为键存储实际数据
        self.cache_indexes: Dict[str, Dict[str, Dict[str, str]]] = {}  # 存储不同索引到 rowid 的映射
        
        # 初始化令牌桶，用于控制QPS
        self.token_bucket = TokenBucket(capacity=self.qps_limit, refill_rate=self.qps_limit)
        
        # 根据 max_workers 动态调整 session 参数，确保至少 20 个连接
        session_pool_size = max(self.max_workers, 20)
        # 初始化Session并配置性能参数
        self.session = get_session(
            retries=3,
            allowed_methods=["GET", "POST", "PATCH", "DELETE"],
            pool_connections=session_pool_size,  # 根据并发度动态调整连接池数量
            pool_maxsize=session_pool_size,     # 根据并发度动态调整最大连接数  
            connect_timeout=5.0,  # 增加连接超时时间
            read_timeout=60.0,    # 增加读取超时时间
        )
        
        # 初始化线程池
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # 启动缓存定时刷新任务
        self._start_cache_refresh_task()


    def _post(self, endpoint: str, payload: dict):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def _get(self, endpoint: str, params: dict=None):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()


    def _patch(self, endpoint: str, payload: dict):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        response = self.session.patch(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def _delete(self, endpoint: str, payload: dict=None):
        # QPS限制检查
        self.token_bucket.wait_for_token()
        url = f"{self.base_url}{endpoint}"
        response = self.session.delete(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()


    def register_model(self, model: Type[Model]):
        """注册模型"""
        # 同时通过 worksheet_id 和类名存储模型
        worksheet_id = model.get_worksheet_id()
        self.models[worksheet_id] = model
        self.models[model.__name__] = model  # 通过类名存储模型
        
        # 检查模型是否配置了缓存
        cache_fields = getattr(model.Meta, 'cache', None)
        if cache_fields:
            # 初始化该模型的缓存数据和索引
            self.cache_data[worksheet_id] = {}
            self.cache_indexes[worksheet_id] = {
                'pk': {},  # 主键到 rowid 的映射
                'rowid': {}  # rowid 到 rowid 的映射（自身映射）
            }
            
            # 获取冲突字段
            conflict_fields = model.get_conflict_fields()
            pk_field = model.get_pk_field()
            
            # 获取该表的所有行数据
            try:
                # 创建查询对象
                query = self.rows(model)
                # 流式获取所有数据，避免内存溢出
                for model_instance in query.stream():
                    # 获取 rowid
                    row_id = getattr(model_instance, 'row_id', str(id(model_instance)))
                    
                    # 生成缓存值
                    cache_value = {}
                    # 首先添加 row_id
                    cache_value['row_id'] = row_id
                    # 然后添加用户指定的字段（使用field_name作为键）
                    for field_name in cache_fields:
                        if hasattr(model_instance, field_name):
                            # 标准化字段名，使用field_name作为键
                            normalized_field = HapUtils.normalize_field_name(model, field_name)
                            cache_value[normalized_field] = getattr(model_instance, field_name)
                    
                    # 存储数据（以 rowid 为键）
                    self.cache_data[worksheet_id][row_id] = cache_value
                    
                    # 创建 rowid 索引
                    self.cache_indexes[worksheet_id]['rowid'][row_id] = row_id
                    
                    # 如果有主键，创建主键索引
                    if pk_field and hasattr(model_instance, pk_field):
                        pk_value = str(getattr(model_instance, pk_field))
                        self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                        # 同时添加按field_name的索引
                        normalized_pk_field = HapUtils.normalize_field_name(model, pk_field)
                        if not normalized_pk_field in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][normalized_pk_field] = {}
                        self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
                    
                    # 如果有冲突字段，创建冲突字段索引
                    elif conflict_fields:
                        # 使用冲突字段形成元组作为键
                        key_parts = []
                        for field_name in conflict_fields:
                            if hasattr(model_instance, field_name):
                                key_parts.append(str(getattr(model_instance, field_name)))
                        conflict_key = tuple(key_parts)
                        if not 'conflict' in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id]['conflict'] = {}
                        self.cache_indexes[worksheet_id]['conflict'][conflict_key] = row_id
                    
                    # 为所有缓存字段创建索引
                    for field_name in cache_fields:
                        if hasattr(model_instance, field_name):
                            field_value = str(getattr(model_instance, field_name))
                            # 标准化字段名，使用field_name作为索引键
                            normalized_field = HapUtils.normalize_field_name(model, field_name)
                            # 如果该字段还没有索引，创建一个
                            if not normalized_field in self.cache_indexes[worksheet_id]:
                                self.cache_indexes[worksheet_id][normalized_field] = {}
                            # 添加字段值到索引
                            self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
            except Exception as e:
                # 缓存失败时记录错误，但不影响模型注册
                console_log.error(f"缓存模型 {model.__name__} 失败: {str(e)}")


    def register_models(self, models: List[Type[Model]]):
        """批量注册模型"""
        for model in models:
            self.register_model(model)


    def get_model(self, model_name: str) -> Type[Model]:
        """获取模型"""
        return self.models[model_name]
    

    def get_cached_data(self, model: Type[Model], key: Union[str, tuple], index_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        从缓存中获取数据
        
        Args:
            model: 模型类
            key: 索引值
            index_type: 索引类型，可选值: 'pk' (主键), 'rowid' (行ID), 'conflict' (冲突字段)。
                      如果为 None，则自动检测索引类型。
            
        Returns:
            Optional[Dict[str, Any]]: 缓存的数据，如果不存在则返回 None
        """
        import re
        
        # 自动检测索引类型
        if index_type is None:
            if isinstance(key, tuple):
                # 元组类型使用冲突字段索引
                index_type = 'conflict'
            elif isinstance(key, str):
                # 检查是否为 UUID 格式
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                if re.match(uuid_pattern, key, re.IGNORECASE):
                    # UUID 格式使用 rowid 索引
                    index_type = 'rowid'
                else:
                    # 其他字符串使用主键索引
                    index_type = 'pk'
            else:
                # 不支持的类型
                return None
        
        worksheet_id = model.get_worksheet_id()
        
        # 检查缓存是否存在
        if worksheet_id not in self.cache_data or worksheet_id not in self.cache_indexes:
            return None
        
        # 检查索引类型是否存在
        if index_type not in self.cache_indexes[worksheet_id]:
            return None
        
        # 通过索引获取 rowid
        row_id = self.cache_indexes[worksheet_id][index_type].get(key)
        if not row_id:
            return None
        
        # 通过 rowid 获取缓存数据
        return self.cache_data[worksheet_id].get(row_id)
    

    def get_choice_sets(self):
        self.choice_sets = {}
        response = self._get("/v3/app/optionsets")
        return response



    def rows(self, model: Type[ModelType]) -> 'HapQuerySet[ModelType]':
        """获取模型的查询集"""
        return HapQuerySet(model=model, hap_conn=self)
    

    def _update_cache_for_instance(self, model_instance: Model) -> None:
        """
        更新缓存中的模型实例数据
        
        Args:
            model_instance: 模型实例
        """
        # 检查模型是否配置了缓存
        cache_fields = getattr(model_instance.__class__.Meta, 'cache', None)
        if not cache_fields:
            return
        
        worksheet_id = model_instance.__class__.get_worksheet_id()
        row_id = getattr(model_instance, 'row_id', None)
        
        if not row_id or worksheet_id not in self.cache_data:
            return
        
        # 更新缓存数据
        cache_value = {}
        cache_value['row_id'] = row_id
        
        for field_name in cache_fields:
            if hasattr(model_instance, field_name):
                # 标准化字段名，使用field_name作为键
                normalized_field = HapUtils.normalize_field_name(model_instance.__class__, field_name)
                cache_value[normalized_field] = getattr(model_instance, field_name)
        
        self.cache_data[worksheet_id][row_id] = cache_value
        
        # 更新索引
        pk_field = model_instance.__class__.get_pk_field()
        if pk_field and hasattr(model_instance, pk_field):
            pk_value = str(getattr(model_instance, pk_field))
            self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
            # 同时更新按field_name的索引
            normalized_pk_field = HapUtils.normalize_field_name(model_instance.__class__, pk_field)
            if normalized_pk_field in self.cache_indexes[worksheet_id]:
                self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
        
        # 更新缓存字段的索引
        for field_name in cache_fields:
            if hasattr(model_instance, field_name):
                field_value = str(getattr(model_instance, field_name))
                # 标准化字段名，使用field_name作为索引键
                normalized_field = HapUtils.normalize_field_name(model_instance.__class__, field_name)
                if normalized_field in self.cache_indexes[worksheet_id]:
                    self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
    

    def _remove_from_cache(self, row_id: str) -> None:
        """
        从缓存中移除指定的行数据
        
        Args:
            row_id: 行ID
        """
        # 遍历所有模型的缓存
        for worksheet_id, cache_data in self.cache_data.items():
            if row_id in cache_data:
                # 从缓存数据中移除
                del cache_data[row_id]
                
                # 从索引中移除
                if worksheet_id in self.cache_indexes:
                    # 从 rowid 索引中移除
                    if 'rowid' in self.cache_indexes[worksheet_id] and row_id in self.cache_indexes[worksheet_id]['rowid']:
                        del self.cache_indexes[worksheet_id]['rowid'][row_id]
                    
                    # 从其他索引中移除
                    for index_name, index_data in self.cache_indexes[worksheet_id].items():
                        if index_name not in ['pk', 'rowid', 'conflict']:
                            # 查找并删除引用该 row_id 的条目
                            keys_to_delete = []
                            for key, value in index_data.items():
                                if value == row_id:
                                    keys_to_delete.append(key)
                            for key in keys_to_delete:
                                del index_data[key]
                break
    
    def _update_cache_for_instances(self, model_instances: List[Model]) -> None:
        """
        批量更新缓存中的模型实例数据
        
        Args:
            model_instances: 模型实例列表
        """
        if not model_instances:
            return
        
        # 按模型类型分组处理
        instances_by_model = {}
        for instance in model_instances:
            model_class = instance.__class__
            if model_class not in instances_by_model:
                instances_by_model[model_class] = []
            instances_by_model[model_class].append(instance)
        
        # 分组处理每个模型的实例
        for model_class, instances in instances_by_model.items():
            # 检查模型是否配置了缓存
            cache_fields = getattr(model_class.Meta, 'cache', None)
            if not cache_fields:
                continue
            
            worksheet_id = model_class.get_worksheet_id()
            if worksheet_id not in self.cache_data:
                continue
            
            # 批量更新缓存
            for instance in instances:
                row_id = getattr(instance, 'row_id', None)
                if not row_id:
                    continue
                
                # 更新缓存数据
                cache_value = {}
                cache_value['row_id'] = row_id
                
                for field_name in cache_fields:
                    if hasattr(instance, field_name):
                        # 标准化字段名，使用field_name作为键
                        normalized_field = HapUtils.normalize_field_name(model_class, field_name)
                        cache_value[normalized_field] = getattr(instance, field_name)
                
                self.cache_data[worksheet_id][row_id] = cache_value
                
                # 更新索引
                pk_field = model_class.get_pk_field()
                if pk_field and hasattr(instance, pk_field):
                    pk_value = str(getattr(instance, pk_field))
                    self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                    # 同时更新按field_name的索引
                    normalized_pk_field = HapUtils.normalize_field_name(model_class, pk_field)
                    if normalized_pk_field in self.cache_indexes[worksheet_id]:
                        self.cache_indexes[worksheet_id][normalized_pk_field][pk_value] = row_id
                
                # 更新缓存字段的索引
                for field_name in cache_fields:
                    if hasattr(instance, field_name):
                        field_value = str(getattr(instance, field_name))
                        # 标准化字段名，使用field_name作为索引键
                        normalized_field = HapUtils.normalize_field_name(model_class, field_name)
                        if normalized_field in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][normalized_field][field_value] = row_id
    
    def _start_cache_refresh_task(self):
        """
        启动缓存定时刷新任务
        """
        import threading
        import time
        
        def refresh_cache():
            """
            定时刷新缓存的函数
            """
            while True:
                try:
                    # 每隔30分钟刷新一次
                    time.sleep(30 * 60)
                    
                    # 遍历所有已注册的模型
                    for model_name, model_class in self.models.items():
                        # 只处理类名对应的模型（避免重复处理）
                        if not isinstance(model_name, str) or model_name != model_class.__name__:
                            continue
                        
                        # 检查模型是否配置了缓存
                        cache_fields = getattr(model_class.Meta, 'cache', None)
                        if not cache_fields:
                            continue
                        
                        worksheet_id = model_class.get_worksheet_id()
                        if worksheet_id not in self.cache_data:
                            continue
                        
                        # 获取最新的1000条记录
                        try:
                            # 构建查询：过滤所有记录，按utime降序排序，获取最新的1000条
                            query = self.rows(model_class)
                            # 应用过滤和排序
                            query = query.filter()  # 空过滤，获取所有记录
                            query = query.order_by("-utime")  # 按utime降序排序
                            query.page_size = 1000  # 设置每页大小为1000
                            query.limit = 1000  # 限制最多获取1000条
                            
                            # 执行查询
                            latest_instances = query.all()
                            
                            # 刷新缓存
                            if latest_instances.count() > 0:
                                self._update_cache_for_instances(latest_instances.row_objects)
                                console_log.info(f"已刷新模型 {model_class.__name__} 的缓存，更新了 {latest_instances.count()} 条记录")
                        except Exception as e:
                            console_log.error(f"刷新模型 {model_class.__name__} 的缓存失败: {str(e)}")
                except Exception as e:
                    console_log.error(f"缓存刷新任务执行失败: {str(e)}")
        
        # 启动后台线程执行定时刷新
        refresh_thread = threading.Thread(target=refresh_cache, daemon=True)
        refresh_thread.start()
        console_log.info("缓存定时刷新任务已启动")



class HapQuerySet(Generic[ModelType]):
    """查询集类，用于构建和执行查询"""
    def __init__(self, model: Type[ModelType], hap_conn: HapConnection):
        self.model = model
        self.hap_conn = hap_conn
        self.filter_condition = {}
        self.sorts = []
        self.page_size = 1000
        self.limit = None
        self.last_query_timestamp = 0


    def get_by_rowid(self, row_id: str) -> Optional[ModelType]:
        """根据行ID获取单条记录"""
        worksheet_id = self.model.get_worksheet_id()
        endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/{row_id}"
        response = self.hap_conn._get(endpoint=endpoint, payload={})

        if response.get("success"):
            row_data = response['data']

            # 处理行数据
            processed_data = HapUtils.process_choice_fields(row_data)
            processed_data = HapUtils.exclude_unamed_fields(processed_data)
            processed_data = HapUtils.exclude_sys_fields(processed_data)
            
            # 创建模型实例
            model_instance = self.model(**processed_data)
            if 'rowid' in row_data:
                model_instance.row_id = row_data['rowid']
            elif 'rowId' in row_data:
                model_instance.row_id = row_data['rowId']
            # 设置 hap_conn 属性，用于后续的 update 操作
            model_instance.hap_conn = self.hap_conn
            
            return model_instance
        
        return None
    

    def filter(self, *args, **kwargs) -> 'HapQuerySet[ModelType]':
        """添加筛选条件
        
        支持多种调用方式：
        1. 使用 Q 对象: filter(Q(field1__eq=value1) & Q(field2__eq=value2))
        2. 使用表达式字符串: filter("field1__eq=value1 && field2__eq=value2")
        3. 使用关键字参数: filter(field1__eq=value1, field2__eq=value2)
        """
        # 处理 Q 对象
        if args and isinstance(args[0], Q):
            self.filter_condition = args[0].to_filter_condition()
        # 处理表达式字符串
        elif args and isinstance(args[0], str):
            self.filter_condition = HapUtils.expression_to_filter_condition(args[0])
        # 处理关键字参数
        elif kwargs:
            q = Q(**kwargs)
            self.filter_condition = q.to_filter_condition()
        return self
    
    def order_by(self, sorts: str) -> 'HapQuerySet[ModelType]':
        """添加排序条件
        
        Args:
            sorts: 排序字符串，格式如 "-x,y"（负号表示降序，正号或无符号表示升序）
        """
        self.sorts = HapUtils.str_to_sort_list(sorts)
        return self
    
    def limit(self, limit: int) -> 'HapQuerySet[ModelType]':
        """设置返回记录数上限
        
        Args:
            limit: 返回记录数上限
        """
        self.limit = limit
        return self
    
    def all(self) -> 'HapRowSet[ModelType]':
        """获取所有匹配的记录"""
        all_models = []
        page_index = 1
        
        while True:
            # 构建查询参数
            payload = {
                "pageSize": min(self.page_size, 1000),  # 确保不超过 HAP 系统限制
                "pageIndex": page_index,
                "includeTotalCount": False,
                "filter": self.filter_condition,
                "sorts": self.sorts
            }
            
            # 发送请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/list"
            response = self.hap_conn._post(endpoint=endpoint, payload=payload)
            
            if response.get('success'):
                for row_dict in response.get('data', {}).get('rows', []):
                    # 处理行数据
                    processed_data = HapUtils.process_choice_fields(row_dict)
                    processed_data = HapUtils.exclude_unamed_fields(processed_data)
                    processed_data = HapUtils.exclude_sys_fields(processed_data)
                    
                    # 创建模型实例
                    model_instance = self.model(**processed_data)
                    if 'rowid' in row_dict:
                        model_instance.row_id = row_dict['rowid']
                    elif 'rowId' in row_dict:
                        model_instance.row_id = row_dict['rowId']
                    # 设置 hap_conn 属性，用于后续的 update 操作
                    model_instance.hap_conn = self.hap_conn
                    # 将查询结果添加到缓存中
                    self.hap_conn._update_cache_for_instance(model_instance)
                    all_models.append(model_instance)
            
            # 应用 limit
            if self.limit and len(all_models) >= self.limit:
                all_models = all_models[:self.limit]
                break
            
            # 检查是否还有更多数据
            if not response.get('success') or len(response.get('data', {}).get('rows', [])) < payload['pageSize']:
                break
            
            page_index += 1
        
        self.last_query_timestamp = datetime.now().timestamp()
        return HapRowSet(models=all_models, model=self.model, hap_conn=self.hap_conn)
    

    def first(self) -> Optional[ModelType]:
        """获取第一个匹配的记录"""
        # 创建一个新的查询集，限制只获取一条记录
        limited_query = self.__class__(self.model, self.hap_conn)
        limited_query.filter_condition = self.filter_condition.copy() if self.filter_condition else {}
        limited_query.sorts = self.sorts.copy() if self.sorts else []
        limited_query.page_size = self.page_size
        limited_query.limit = 1
        
        # 执行查询
        row_set = limited_query.all()
        
        # 返回第一个记录
        return row_set.first() if row_set.count() > 0 else None
    

    def stream(self) -> Generator[ModelType, None, None]:
        """流式获取所有匹配的记录"""
        # 首先获取总数
        total_payload = {
            "pageSize": 1,
            "pageIndex": 1,
            "includeTotalCount": True,
            "filter": self.filter_condition,
            "sorts": self.sorts
        }
        
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/list"
        total_response = self.hap_conn._post(endpoint=endpoint, payload=total_payload)
        
        if not total_response.get('success'):
            return
        
        total_count = total_response.get('data', {}).get('total', 0)
        
        # 计算需要的页数
        page_size = min(self.limit, self.page_size) if self.limit else self.page_size
        page_size = min(page_size, 1000)  # 确保不超过 HAP 系统限制
        total_pages = (total_count + page_size - 1) // page_size
        
        fetched_count = 0
        
        # 逐页获取数据
        for page in range(1, total_pages + 1):
            # 构建查询参数
            payload = {
                "pageSize": page_size,
                "pageIndex": page,
                "includeTotalCount": False,
                "filter": self.filter_condition,
                "sorts": self.sorts
            }
            
            # 发送请求
            response = self.hap_conn._post(endpoint=endpoint, payload=payload)
            
            if response.get('success'):
                for row_dict in response.get('data', {}).get('rows', []):
                    # 处理行数据
                    processed_data = HapUtils.process_choice_fields(row_dict)
                    processed_data = HapUtils.exclude_unamed_fields(processed_data)
                    processed_data = HapUtils.exclude_sys_fields(processed_data)
                    
                    # 创建模型实例
                    model_instance = self.model(**processed_data)
                    if 'rowid' in row_dict:
                        model_instance.row_id = row_dict['rowid']
                    elif 'rowId' in row_dict:
                        model_instance.row_id = row_dict['rowId']
                    # 设置 hap_conn 属性，用于后续的 update 操作
                    model_instance.hap_conn = self.hap_conn
                    
                    yield model_instance
                    fetched_count += 1
                    
                    # 应用 limit
                    if self.limit and fetched_count >= self.limit:
                        return
    
    def create(self, **kwargs) -> ModelType:
        """创建新模型实例"""
        # 创建一个空的 HapRowSet 实例，然后调用其 create 方法
        row_set = HapRowSet(models=[], model=self.model, hap_conn=self.hap_conn)
        return row_set.create(**kwargs)
    
    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[ModelType]:
        """批量创建模型实例"""
        # 创建一个空的 HapRowSet 实例，然后调用其 bulk_create 方法
        row_set = HapRowSet(models=[], model=self.model, hap_conn=self.hap_conn)
        return row_set.bulk_create(data_list)
    
    def upsert(self, data_list: List[Dict[str, Any]], exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> 'HapRowSet[ModelType]':
        """批量 upsert 操作"""
        # 创建一个空的 HapRowSet 实例，然后调用其 upsert 方法
        row_set = HapRowSet(models=[], model=self.model, hap_conn=self.hap_conn)
        return row_set.upsert(data_list, exclude_none, trigger_workflow, when_value_equal_then)


class HapRowSet(Generic[ModelType]):
    """行集合类，用于管理多个模型实例"""
    def __init__(self, models: List[ModelType], model: Type[ModelType], hap_conn: HapConnection):
        self.row_objects = models
        self.model = model
        self.hap_conn = hap_conn
        self.refresh_stamp = datetime.now().timestamp()

    def all(self) -> List[ModelType]:
        """获取所有模型实例"""
        return self.row_objects

    def first(self) -> Optional[ModelType]:
        """获取第一个模型实例"""
        return self.row_objects[0] if self.row_objects else None

    def last(self) -> Optional[ModelType]:
        """获取最后一个模型实例"""
        return self.row_objects[-1] if self.row_objects else None

    def count(self) -> int:
        """获取模型实例数量"""
        return len(self.row_objects)
    
    def refresh(self) -> 'HapRowSet[ModelType]':
        """批量刷新模型实例的数据
        
        Returns:
            HapRowSet[ModelType]: 刷新后的行集合
        """
        for model in self.row_objects:
            model.refresh()
        return self

    def _process_complex_fields(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理关联字段等复杂类型的字段
    
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """
        processed_data = data.copy()
        
        # 获取模型的所有字段
        fields = self.model._get_fields()
        
        # 遍历所有字段，查找关联字段和文本字段
        # 注意：不处理 SubtableField 类型的字段，因为它会在 upsert 操作中被单独处理
        for attr_name, field in fields.items():
            if isinstance(field, RelationField):
                # 调用 RelationField 自身的处理方法
                processed_data = field.process_relation(processed_data, original_data, self.hap_conn)
            elif isinstance(field, StrField):
                # 调用 TextField 自身的处理方法
                processed_data = field.process_mapping(processed_data, original_data)
            elif isinstance(field, SubtableField):
                processed_data = field.process_subtable(processed_data, original_data, self.hap_conn)
        
        return processed_data

    def create(self, **kwargs) -> ModelType:
        """创建新模型实例"""
        # 处理关联字段
        processed_kwargs = self._process_complex_fields(kwargs)
        
        # 构建创建请求
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
        
        # 转换数据为字段列表
        row_fields = HapUtils.convert_data_to_fieldslist(processed_kwargs, model=self.model)
        payload = {
            "rows": [{"fields": row_fields}],
            "triggerWorkflow": True
        }
        
        # 发送请求
        response = self.hap_conn._post(endpoint, payload)
        
        # 处理响应
        if response.get('success'):
            row_ids = response.get('data', {}).get('rowIds', [])
            if row_ids:
                # 创建模型实例
                model_instance = self.model(**processed_kwargs)
                model_instance.row_id = row_ids[0]
                self.row_objects.append(model_instance)
                return model_instance
        
        raise Exception("Failed to create model instance")

    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[ModelType]:
        """批量创建模型实例"""
        # 分批处理，每批最多100条
        batch_size = 100
        total_items = len(data_list)
        created_models = []
        
        for i in range(0, total_items, batch_size):
            batch_data = data_list[i:i+batch_size]
            
            # 构建创建请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
            
            # 转换数据为字段列表
            rows_data = []
            processed_batch_data = []
            for data_dict in batch_data:
                # 直接使用传入的数据，不再调用 _process_complex_fields
                # 因为在 upsert 操作中已经处理过了
                processed_data = data_dict
                processed_batch_data.append(processed_data)
                
                row_fields = HapUtils.convert_data_to_fieldslist(processed_data, model=self.model)
                rows_data.append({'fields': row_fields})
            
            payload = {
                "rows": rows_data,
                "triggerWorkflow": True
            }
            
            # 发送请求
            response = self.hap_conn._post(endpoint, payload)
            
            # 处理响应
            if response.get('success'):
                row_ids = response.get('data', {}).get('rowIds', [])
                for j, row_id in enumerate(row_ids):
                    if i + j < total_items:
                        # 创建模型实例
                        model_instance = self.model(**processed_batch_data[j])
                        model_instance.row_id = row_id
                        self.row_objects.append(model_instance)
                        created_models.append(model_instance)
        
        # 批量更新缓存
        self.hap_conn._update_cache_for_instances(created_models)
        
        return created_models

    def update(self, **kwargs) -> List[ModelType]:
        """批量更新模型实例
        
        Args:
            **kwargs: 要更新的字段和值
            when_value_equal_then: 当字段值相等时的处理方式，默认'jumpover' 跳过，'update' 则无论字段是否与data一样都更新
        """
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.model._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 获取 when_value_equal_then 参数
        when_value_equal_then = kwargs.pop('when_value_equal_then', 'jumpover')
        
        # 构建更新数据，按模型实例分组
        update_groups = {}
        for model in self.row_objects:
            # 获取模型实例的原始数据
            original_data = model.to_dict()
            
            # 处理关联字段
            processed_kwargs = self._process_complex_fields(kwargs, original_data)
            
            # 比较字段值差异，只包含变化的字段
            changed_data = {}
            if when_value_equal_then == 'update':
                # 无论字段值是否变化，都更新
                changed_data = processed_kwargs
            else:
                # 只包含变化的字段
                for key, value in processed_kwargs.items():
                    # 确定在 original_data 中使用的键名
                    original_key = key
                    if key in field_map:
                        original_key = field_map[key]
                    elif key in original_data:
                        original_key = key
                    
                    # 检查字段值是否变化
                    if original_key not in original_data or not DataProcessor.is_equal(original_data[original_key], value):
                        changed_data[key] = value
            
            # 如果有变化的字段，添加到更新组
            if changed_data:
                # 转换数据为字段列表，使用字段映射，保留未注册的字段
                fields_list = HapUtils.convert_data_to_fieldslist(changed_data, field_map=field_map, model=self.model, remain_irrelevant_fields=True)
                
                # 按字段列表分组，相同字段列表的模型实例可以一起更新
                fields_key = str(fields_list)
                if fields_key not in update_groups:
                    update_groups[fields_key] = {
                        "fields_list": fields_list,
                        "row_ids": [],
                        "models": []
                    }
                update_groups[fields_key]["row_ids"].append(model.row_id)
                update_groups[fields_key]["models"].append(model)
        
        # 执行更新操作
        updated_models = []
        for group in update_groups.values():
            # 构建更新请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
            
            # 构建请求体
            payload = {
                "rowIds": group["row_ids"],
                "fields": group["fields_list"],
                "triggerWorkflow": True
            }
            
            # 发送请求
            response = self.hap_conn._patch(endpoint=endpoint, payload=payload)
            
            # 处理响应
            if response.get('success'):
                # 更新模型实例的属性
                for model in group["models"]:
                    for key, value in kwargs.items():
                        setattr(model, key, value)
                    updated_models.append(model)
            else:
                raise Exception(f"Failed to update model instances: {response.get('message', 'Unknown error')}")
        
        # 批量更新缓存
        self.hap_conn._update_cache_for_instances(updated_models)
        
        return updated_models

    def delete(self, trigger_workflow: bool = True) -> bool:
        """批量删除模型实例
        
        Args:
            trigger_workflow: 是否触发工作流
        
        Returns:
            bool: 删除是否成功
        """
        if not self.row_objects:
            return True
        
        # 构建删除请求
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
        
        # 构建请求体
        payload = {
            "rowIds": [model.row_id for model in self.row_objects],
            "triggerWorkflow": trigger_workflow
        }
        
        # 发送请求
        response = self.hap_conn._delete(endpoint=endpoint, payload=payload)
        
        # 处理响应
        if response.get('success'):
            # 从缓存中移除
            for model in self.row_objects:
                if hasattr(model, 'row_id'):
                    self.hap_conn._remove_from_cache(model.row_id)
            # 清空行对象列表
            self.row_objects = []
            return True
        else:
            raise Exception(f"Failed to delete model instances: {response.get('message', 'Unknown error')}")

    def _process_item(self, data_dict, pk_field, conflict_fields, when_value_equal_then):
        """处理单个数据项的 upsert 操作"""
        # 构建查询条件
        field_map = self.model._get_field_map()
        filter_conditions = []
        
        # 优先使用主键字段判断
        if pk_field:
            pk_field_name = field_map[pk_field]
            if pk_field in data_dict:
                match_value = data_dict[pk_field]
            else:
                match_value = data_dict[pk_field_name]
            filter_conditions.append(f'{pk_field_name}__eq=\"{match_value}\"')
        # 其次使用冲突字段判断
        if conflict_fields and not filter_conditions:
            for field in conflict_fields:
                match_value = None
                if field in data_dict:
                    match_value = data_dict[field]
                    filter_conditions.append(f'{field}__eq=\"{match_value}\"')
                elif field in field_map:
                    c_field_name = field_map[field]
                    if c_field_name in data_dict:
                        match_value = data_dict[c_field_name]
                        filter_conditions.append(f'{c_field_name}__eq=\"{match_value}\"')
        
        # 如果没有有效的判断字段值，返回需要创建
        if not filter_conditions:
            return (None, data_dict)
        
        # 执行查询
        existing_rows = self.hap_conn.rows(self.model).filter(" && ".join(filter_conditions)).all()
        rows_count = existing_rows.count()
        
        if rows_count == 1:
            # 若有且仅有一条则执行更新
            existing_model = existing_rows.first()
            # 构建更新数据
            update_data = {}
            for key, value in data_dict.items():
                # 跳过特殊字段
                if key not in ['row_id', 'hap_conn']:
                    update_data[key] = value
            # 执行更新
            updated_model = existing_model.update(**update_data, when_value_equal_then=when_value_equal_then)
            return (updated_model, None)
        if rows_count > 1:
            # 存在多条，删除所有匹配行
            existing_rows.delete()
        return (None, data_dict)
    
    def _batch_process_items(self, data_list, pk_field, conflict_fields, when_value_equal_then):
        """批量处理多个数据项的 upsert 操作"""
        if not data_list:
            return []
        
        # 分类数据：需要更新的和需要创建的
        to_update = []
        to_create = []
        
        # 构建批量查询条件
        field_map = self.model._get_field_map()
        batch_conditions = []
        data_map = {}
        
        for data_dict in data_list:
            filter_conditions = []
            
            # 优先使用主键字段判断
            if pk_field:
                pk_field_name = field_map[pk_field]
                if pk_field in data_dict:
                    match_value = data_dict[pk_field]
                else:
                    match_value = data_dict[pk_field_name]
                filter_conditions.append(f'{pk_field_name}__eq=\"{match_value}\"')
            # 其次使用冲突字段判断
            elif conflict_fields:
                for field in conflict_fields:
                    match_value = None
                    if field in data_dict:
                        match_value = data_dict[field]
                        filter_conditions.append(f'{field}__eq=\"{match_value}\"')
                    elif field in field_map:
                        c_field_name = field_map[field]
                        if c_field_name in data_dict:
                            match_value = data_dict[c_field_name]
                            filter_conditions.append(f'{c_field_name}__eq=\"{match_value}\"')
            
            if filter_conditions:
                condition_str = " && ".join(filter_conditions)
                batch_conditions.append(condition_str)
                data_map[condition_str] = data_dict
            else:
                to_create.append(data_dict)
        
        # 批量查询
        if batch_conditions:
            # 构建 OR 条件
            or_condition = " || ".join([f"({cond})" for cond in batch_conditions])
            existing_rows = self.hap_conn.rows(self.model).filter(or_condition).all()
            
            # 构建查询结果映射
            existing_map = {}
            for model_instance in existing_rows.row_objects:
                # 构建唯一键
                key_parts = []
                if pk_field:
                    pk_value = getattr(model_instance, pk_field)
                    key_parts.append(f'{field_map[pk_field]}__eq=\"{pk_value}\"')
                elif conflict_fields:
                    for field in conflict_fields:
                        field_value = getattr(model_instance, field)
                        key_parts.append(f'{field}__eq=\"{field_value}\"')
                if key_parts:
                    key = " && ".join(key_parts)
                    existing_map[key] = model_instance
            
            # 分类数据
            for condition_str, data_dict in data_map.items():
                if condition_str in existing_map:
                    to_update.append((existing_map[condition_str], data_dict))
                else:
                    to_create.append(data_dict)
        
        # 批量更新
        updated_models = []
        if to_update:
            # 按更新数据分组
            update_groups = {}
            for model_instance, data_dict in to_update:
                # 构建更新数据
                update_data = {}
                for key, value in data_dict.items():
                    if key not in ['row_id', 'hap_conn']:
                        update_data[key] = value
                
                # 按更新数据分组
                data_key = str(update_data)
                if data_key not in update_groups:
                    update_groups[data_key] = {
                        "data": update_data,
                        "models": []
                    }
                update_groups[data_key]["models"].append(model_instance)
            
            # 执行批量更新
            for group in update_groups.values():
                # 创建 HapRowSet 并执行批量更新
                row_set = HapRowSet(models=group["models"], model=self.model, hap_conn=self.hap_conn)
                updated = row_set.update(**group["data"], when_value_equal_then=when_value_equal_then)
                updated_models.extend(updated)
        
        # 批量创建
        created_models = []
        if to_create:
            created = self.bulk_create(to_create)
            created_models.extend(created)
        
        # 合并结果
        all_models = updated_models + created_models
        return all_models

    def _process_items_parallel(self, data_list, pk_field, conflict_fields, when_value_equal_then):
        """并行处理多个数据项的 upsert 操作"""
        from concurrent.futures import as_completed
        
        results = []
        # 动态调整任务数，避免创建过多线程
        max_tasks = min(len(data_list), self.hap_conn.max_workers)
        
        # 使用 HapConnection 中的全局线程池
        executor = self.hap_conn.executor
        
        # 提交所有任务
        future_to_data = {executor.submit(self._process_item, data, pk_field, conflict_fields, when_value_equal_then): data for data in data_list[:max_tasks]}
        
        # 收集结果
        for future in as_completed(future_to_data):
            data = future_to_data[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                console_log.error(f"处理 {data} 时出错: {exc}")
        
        # 处理剩余的数据（如果有）
        if len(data_list) > max_tasks:
            remaining_data = data_list[max_tasks:]
            for data in remaining_data:
                try:
                    result = self._process_item(data, pk_field, conflict_fields, when_value_equal_then)
                    results.append(result)
                except Exception as exc:
                    console_log.error(f"处理 {data} 时出错: {exc}")
        
        return results

    def upsert(self, data_list: List[Dict[str, Any]], exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> 'HapRowSet[ModelType]':
        """批量 upsert 操作
        
        Args:
            data_list: 要 upsert 的数据列表
            exclude_none: 是否排除值为 None 的字段
            trigger_workflow: 是否触发工作流
            when_value_equal_then: 当字段值相等时的处理方式，默认'jumpover' 跳过，'update' 则无论字段是否与data一样都更新
        
        Returns:
            HapRowSet[ModelType]: 包含 upsert 后模型实例的行集合
        """
        result_models = []
        create_list = []  # 存储需要创建的数据
        
        # 处理数据列表 - 只处理一次
        processed_data_list = []
        for data in data_list:
            # 处理关联字段
            processed_data = self._process_complex_fields(data)

            # 过滤掉值为 None 的字段
            if exclude_none:
                processed_data = {k: v for k, v in processed_data.items() if v is not None}
            processed_data_list.append(processed_data)
        
        # 获取主键字段
        pk_field = self.model.get_pk_field()
        
        # 检查是否有冲突字段
        conflict_fields = self.model.get_conflict_fields()
        has_conflict_fields = bool(conflict_fields)
        
        # 如果既没有主键字段也没有冲突字段，直接批量创建
        if not pk_field and not has_conflict_fields:
            created_models = self.bulk_create(processed_data_list)
            return HapRowSet(models=created_models, model=self.model, hap_conn=self.hap_conn)
        
        # 根据数据量选择处理方式
        if len(processed_data_list) > 10:  # 数据量较大时使用批量处理
            # 批量处理数据
            all_models = self._batch_process_items(
                processed_data_list,
                pk_field,
                conflict_fields,
                when_value_equal_then
            )
            result_models.extend(all_models)
        else:  # 数据量较小时使用并行处理
            # 并行处理数据
            results = self._process_items_parallel(
                processed_data_list,
                pk_field,
                conflict_fields,
                when_value_equal_then
            )
            
            # 处理结果
            for result in results:
                if result[0]:  # 更新成功的模型
                    result_models.append(result[0])
                elif result[1]:  # 需要创建的模型
                    create_list.append(result[1])
            
            # 批量创建需要新增的模型
            if create_list:
                created_models = self.bulk_create(create_list)
                result_models.extend(created_models)
        
        # 批量更新缓存
        self.hap_conn._update_cache_for_instances(result_models)
        
        return HapRowSet(models=result_models, model=self.model, hap_conn=self.hap_conn)
