"""
明道云 API v3 封装为 ORM，V2.0
"""

import os
import re
import json
from typing import List, Dict, Any, Optional, Union, Literal, Generator, Type, TypeVar, cast, Generic
from datetime import datetime
from decimal import Decimal
from abc import ABC, abstractmethod

from ..utils.data_processor import DataProcessor
from ..utils.common import parallel_executor
from ._base import get_session, filelog_normal, filelog_error, console_log


# 调用刷新函数时，距离上次刷新超过这个秒数，才会刷新行数据，否则直接返回缓存数据
REFRESH_INTERVAL_SECONDS = 5

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
                 max_length: Optional[int] = None, 
                 null: bool = False, 
                 default: Any = None, 
                 description: Optional[str] = None,
                 pk: bool = False):
        self.max_length = max_length
        self.null = null
        self.default = default
        self.description = description
        self.field_name = field_name
        self.pk = pk
        self.model: Optional[Type['Model']] = None
    
    def __set_name__(self, owner, name):
        # 当 field_name 未提供时，使用属性名作为默认值
        if self.field_name is None:
            self.field_name = name
        self.model = owner


# 文本字段
class TextField(Field):
    """文本字段"""
    def __init__(self, 
                 field_name: Optional[str] = None, 
                 max_length: Optional[int] = None, 
                 null: bool = False, 
                 default: Optional[str] = None, 
                 description: Optional[str] = None,
                 pk: bool = False):
        super().__init__(field_name, max_length, null, default, description, pk)


# 数值字段
class NumField(Field):
    """数值字段，支持整数和浮点数"""
    def __init__(self, 
                 field_name: Optional[str] = None, 
                 null: bool = False, 
                 default: Optional[Union[int, float]] = None, 
                 description: Optional[str] = None,
                 pk: bool = False):
        super().__init__(field_name, None, null, default, description, pk)


# 关联字段
class RelationField(Field):
    """关联字段"""
    def __init__(self, 
                 model: Type['Model'], 
                 field_name: Optional[str] = None, 
                 null: bool = False, 
                 description: Optional[str] = None,
                 pk: bool = False,
                 follow_with: Optional[str] = None):
        # 关联字段不能被设为主键
        if pk:
            raise ValueError("RelationField cannot be set as primary key")
        self.follow_with = follow_with  # 跟随的字段名，用于自动更新关联关系
        super().__init__(field_name, None, null, None, description, False)
        self.related_model = model


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
        # 获取模型的所有字段
        fields = self._get_fields()
        
        # 首先处理特殊属性
        if 'hap_conn' in kwargs:
            self.hap_conn = kwargs.pop('hap_conn')
        
        # 首先处理直接匹配的字段
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # 然后处理通过 field_name 映射的字段
        for attr_name, field in fields.items():
            if field.field_name in kwargs and not hasattr(self, attr_name):
                setattr(self, attr_name, kwargs[field.field_name])
    
    @classmethod
    def _get_fields(cls) -> Dict[str, Field]:
        """获取模型的所有字段"""
        fields = {}
        for attr_name in dir(cls):
            attr = getattr(cls, attr_name)
            if isinstance(attr, Field):
                fields[attr_name] = attr
        return fields
    
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
        pk_fields = [field_name for field_name, field in fields.items() if field.pk]
        # 确保每个模型只有一个主键
        if len(pk_fields) > 1:
            raise ValueError("Model can only have one primary key")
        return pk_fields[0] if pk_fields else None
    
    def update(self, **kwargs) -> 'Model':
        """更新模型实例
        
        Args:
            **kwargs: 要更新的字段和值
            
        Returns:
            Model: 更新后的模型实例
        """
        # 检查模型实例是否有 row_id
        if not hasattr(self, 'row_id'):
            raise ValueError("Model instance must have a row_id to update")
        
        # 构建更新请求
        endpoint = f"/v3/app/worksheets/{self.__class__.get_worksheet_id()}/rows/batch"
        
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.__class__._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 转换数据为字段列表，使用字段映射
        fields_list = HapUtils.convert_data_to_fieldslist(kwargs, field_map=field_map, model=self)
        
        # 构建请求体
        payload = {
            "rowIds": [self.row_id],
            "fields": fields_list,
            "triggerWorkflow": True
        }
        
        # 发送请求
        from .hapv2 import HapConnection
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
            raise Exception(f"Failed to update model instance: {response.get('message', 'Unknown error')}")
    
    def to_dict(self) -> Dict[str, Any]:
        """将模型实例转换为字典"""
        data = {}
        fields = self._get_fields()
        for attr_name, field in fields.items():
            if hasattr(self, attr_name):
                # 使用 field_name 作为字典键
                data[field.field_name] = getattr(self, attr_name)
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


# 工具类，包含通用方法
class HapUtils:
    """
    明道云工具类，包含通用方法
    """
    
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
            try:
                control_id = field_map[k]
            except:
                if remain_irrelevant_fields:
                    control_id = k
                else:
                    continue

            v_type = type(v)
            if v_type in (dict, list):
                # 检查是否需要 json.dumps
                need_json_dumps = True
                if model:
                    # 获取模型的字段映射
                    field_map_reverse = {v: k for k, v in field_map.items()}
                    # 获取字段名
                    field_name = field_map_reverse.get(control_id, k)
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


HAP_BASEURL_EXAMPLE = ('https://api.mingdao.com', 'http://127.0.0.1:8080/api')


class HapConnection:
    def __init__(self, app_key: str, sign: str, base_url: str=HAP_BASEURL_EXAMPLE[0], max_workers: int=os.cpu_count() * 3):
        self.models: Dict[str, Type[Model]] = {}
        self.base_url = base_url
        self.api_key = app_key
        self.sign = sign
        self.max_workers = max_workers
        self.headers = {
            'HAP-Appkey': app_key,
            'HAP-Sign': sign,
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate"  # 启用压缩
        }
        # 缓存结构，包含数据和索引
        self.cache_data: Dict[str, Dict[str, Dict[str, Any]]] = {}  # 以 rowid 为键存储实际数据
        self.cache_indexes: Dict[str, Dict[str, Dict[str, str]]] = {}  # 存储不同索引到 rowid 的映射
        
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

    def _post(self, endpoint: str, payload: dict):
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def _get(self, endpoint: str, params: dict=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def _patch(self, endpoint: str, payload: dict):
        url = f"{self.base_url}{endpoint}"
        response = self.session.patch(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def _delete(self, endpoint: str, payload: dict=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.delete(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def register_model(self, model: Type[Model]):
        """注册模型"""
        self.models[model.get_worksheet_id()] = model
        
        # 检查模型是否配置了缓存
        cache_fields = getattr(model.Meta, 'cache', None)
        if cache_fields:
            # 初始化该模型的缓存数据和索引
            worksheet_id = model.get_worksheet_id()
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
                    # 首先添加 rowid
                    cache_value['row_id'] = row_id
                    # 然后添加用户指定的字段
                    for field_name in cache_fields:
                        if hasattr(model_instance, field_name):
                            cache_value[field_name] = getattr(model_instance, field_name)
                    
                    # 存储数据（以 rowid 为键）
                    self.cache_data[worksheet_id][row_id] = cache_value
                    
                    # 创建 rowid 索引
                    self.cache_indexes[worksheet_id]['rowid'][row_id] = row_id
                    
                    # 如果有主键，创建主键索引
                    if pk_field and hasattr(model_instance, pk_field):
                        pk_value = str(getattr(model_instance, pk_field))
                        self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                        # 同时添加按字段名的索引
                        if not pk_field in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][pk_field] = {}
                        self.cache_indexes[worksheet_id][pk_field][pk_value] = row_id
                    
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
                            # 如果该字段还没有索引，创建一个
                            if not field_name in self.cache_indexes[worksheet_id]:
                                self.cache_indexes[worksheet_id][field_name] = {}
                            # 添加字段值到索引
                            self.cache_indexes[worksheet_id][field_name][field_value] = row_id
            except Exception as e:
                # 缓存失败时记录错误，但不影响模型注册
                console_log(f"缓存模型 {model.__name__} 失败: {str(e)}")

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
        
        # 通过 rowid 获取数据
        return self.cache_data[worksheet_id].get(row_id)
    
    def refresh_cache(self, model: Type[Model]) -> bool:
        """
        刷新模型的缓存
        
        Args:
            model: 模型类
            
        Returns:
            bool: 刷新是否成功
        """
        worksheet_id = model.get_worksheet_id()
        cache_fields = getattr(model.Meta, 'cache', None)
        
        if not cache_fields:
            return False
        
        try:
            # 移除旧缓存
            if worksheet_id in self.cache_data:
                del self.cache_data[worksheet_id]
            if worksheet_id in self.cache_indexes:
                del self.cache_indexes[worksheet_id]
            
            # 重新初始化缓存数据和索引
            self.cache_data[worksheet_id] = {}
            self.cache_indexes[worksheet_id] = {
                'pk': {},  # 主键到 rowid 的映射
                'rowid': {}  # rowid 到 rowid 的映射（自身映射）
            }
            
            # 获取冲突字段和主键字段
            conflict_fields = model.get_conflict_fields()
            pk_field = model.get_pk_field()
            
            # 获取该表的所有行数据
            query = self.rows(model)
            for model_instance in query.stream():
                # 获取 rowid
                row_id = getattr(model_instance, 'row_id', str(id(model_instance)))
                
                # 生成缓存值
                cache_value = {}
                # 首先添加 rowid
                cache_value['row_id'] = row_id
                # 然后添加用户指定的字段
                for field_name in cache_fields:
                    if hasattr(model_instance, field_name):
                        cache_value[field_name] = getattr(model_instance, field_name)
                
                # 存储数据（以 rowid 为键）
                self.cache_data[worksheet_id][row_id] = cache_value
                
                # 创建 rowid 索引
                self.cache_indexes[worksheet_id]['rowid'][row_id] = row_id
                
                # 如果有主键，创建主键索引
                if pk_field and hasattr(model_instance, pk_field):
                    pk_value = str(getattr(model_instance, pk_field))
                    self.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                    # 同时添加按字段名的索引
                    if not pk_field in self.cache_indexes[worksheet_id]:
                        self.cache_indexes[worksheet_id][pk_field] = {}
                    self.cache_indexes[worksheet_id][pk_field][pk_value] = row_id
                
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
                        # 如果该字段还没有索引，创建一个
                        if not field_name in self.cache_indexes[worksheet_id]:
                            self.cache_indexes[worksheet_id][field_name] = {}
                        # 添加字段值到索引
                        self.cache_indexes[worksheet_id][field_name][field_value] = row_id
            
            return True
        except Exception as e:
            # 刷新失败时记录错误
            console_log(f"刷新模型 {model.__name__} 缓存失败: {str(e)}")
            return False
    
    def start_cache_refresh_task(self, interval_seconds: int = 3600) -> None:
        """
        启动定时刷新缓存的任务
        
        Args:
            interval_seconds: 刷新间隔，单位为秒，默认为 3600 秒（1小时）
        """
        import threading
        import time
        
        def refresh_task():
            while True:
                try:
                    # 刷新所有已注册且有缓存配置的模型
                    for model in self.models.values():
                        if getattr(model.Meta, 'cache', None):
                            self.refresh_cache(model)
                except Exception as e:
                    console_log(f"定时刷新缓存任务失败: {str(e)}")
                # 等待指定的间隔时间
                time.sleep(interval_seconds)
        
        # 创建并启动后台线程
        thread = threading.Thread(target=refresh_task, daemon=True)
        thread.start()
        console_log(f"定时刷新缓存任务已启动，刷新间隔: {interval_seconds} 秒")

    def rows(self, model: Type[ModelType], filter_expression: Optional[str] = None, sort_str: Optional[str] = None) -> 'HapRowsQuery[ModelType]':
        """获取行查询对象"""
        return HapRowsQuery(model=model, hap_conn=self, filter_expression=filter_expression, sort_str=sort_str)


class HapRowsQuery(Generic[ModelType]):
    """行查询类，支持链式查询操作"""
    def __init__(self, model: Type[ModelType], hap_conn: HapConnection, filter_expression: Union[str, 'Q', None] = None, sort_str: str = None):
        self.model = model
        self.hap_conn = hap_conn
        self.filter_expression = filter_expression
        self.filter_condition = self._get_filter_condition(filter_expression)
        self.page_size = 1000
        self.page_index = 1
        self.sort_str = sort_str
        self.sorts = HapUtils.str_to_sort_list(sort_str)
        self.limit = None
        self.last_query_timestamp = None
    
    def _get_filter_condition(self, filter_expression: Union[str, 'Q', None]) -> dict:
        """
        获取过滤条件
        
        Args:
            filter_expression: 过滤表达式，可以是字符串或 Q 对象
            
        Returns:
            dict: 符合明道云 API 要求的筛选条件
        """
        if isinstance(filter_expression, Q):
            return filter_expression.to_filter_condition()
        elif isinstance(filter_expression, str):
            return HapUtils.expression_to_filter_condition(filter_expression)
        return {}

    def filter(self, filter_expression: Union[str, 'Q']) -> 'HapRowsQuery[ModelType]':
        """添加过滤条件"""
        self.filter_expression = filter_expression
        self.filter_condition = self._get_filter_condition(filter_expression)
        return self

    def sort(self, sort_str: str) -> 'HapRowsQuery[ModelType]':
        """添加排序条件"""
        self.sort_str = sort_str
        self.sorts = HapUtils.str_to_sort_list(sort_str)
        return self

    def set_limit(self, limit: int) -> 'HapRowsQuery[ModelType]':
        """设置返回记录数限制"""
        self.limit = limit
        return self

    def offset(self, offset: int) -> 'HapRowsQuery[ModelType]':
        """设置偏移量"""
        self.page_index = offset // self.page_size + 1
        return self

    def _execute_query(self, page_size: int, include_total: bool = True) -> 'HapRowSet[ModelType]':
        """执行查询并返回结果"""
        # 构建查询参数
        payload = {
            "pageSize": page_size,
            "pageIndex": self.page_index,
            "includeTotalCount": include_total,
        }
        
        payload["filter"] = self.filter_condition
        payload['sorts'] = self.sorts
        
        # 发送请求
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/list"
        response = self.hap_conn._post(endpoint=endpoint, payload=payload)
        self.last_query_timestamp = datetime.now().timestamp()
        
        # 处理响应
        models = []
        if response.get('success'):
            for row_dict in response.get('data', {}).get('rows', []):
                # 处理行数据
                processed_data = HapUtils.process_choice_fields(row_dict)
                processed_data = HapUtils.exclude_unamed_fields(processed_data)
                processed_data = HapUtils.exclude_sys_fields(processed_data)
                
                # 创建模型实例，传递 hap_conn 属性
                model_instance = self.model(**processed_data, hap_conn=self.hap_conn)
                if 'rowid' in row_dict:
                    model_instance.row_id = row_dict['rowid']
                elif 'rowId' in row_dict:
                    model_instance.row_id = row_dict['rowId']
                models.append(model_instance)
        
        return HapRowSet(models=models, model=self.model, hap_conn=self.hap_conn)

    def first(self) -> Optional[ModelType]:
        """获取第一条记录"""
        # 只获取一条记录，不包含总数
        model_set = self._execute_query(page_size=1, include_total=False)
        return model_set.first()

    def all(self) -> 'HapRowSet[ModelType]':
        """获取所有匹配的记录"""
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
            return HapRowSet(models=[], model=self.model, hap_conn=self.hap_conn)
        
        total_count = total_response.get('data', {}).get('total', 0)
        
        # 如果数据量过大，抛出警告
        if total_count > 10000:
            print(f"警告：数据量较大 ({total_count} 条)，可能会导致内存溢出。建议使用 stream() 方法。")
        
        # 计算需要的页数
        page_size = min(self.limit, self.page_size) if self.limit else self.page_size
        page_size = min(page_size, 1000)  # 确保不超过 HAP 系统限制
        total_pages = (total_count + page_size - 1) // page_size
        
        all_models = []
        
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
                    all_models.append(model_instance)
            
            # 应用 limit
            if self.limit and len(all_models) >= self.limit:
                all_models = all_models[:self.limit]
                break
        
        self.last_query_timestamp = datetime.now().timestamp()
        return HapRowSet(models=all_models, model=self.model, hap_conn=self.hap_conn)

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

    def _process_relation_fields(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理关联字段，根据特定字段自动更新关联关系
        
        Args:
            data: 包含字段数据的字典
            original_data: 原始数据字典，用于比较字段值是否变化
            
        Returns:
            Dict[str, Any]: 处理后的字段数据字典
        """
        processed_data = data.copy()
        
        # 获取模型的所有字段
        fields = self.model._get_fields()
        
        # 遍历所有字段，查找关联字段
        for attr_name, field in fields.items():
            if isinstance(field, RelationField):
                # 确定代码字段名
                code_field_name = None
                
                # 优先使用 follow_with 参数指定的字段名
                if field.follow_with:
                    code_field_name = field.follow_with
                # 否则使用默认规则（例如：currency -> currencyCode）
                else:
                    code_field_name = f"{field.field_name}Code"
                
                # 检查是否需要更新关联字段
                # 情况一：创建记录时 code_field_name 有值
                # 情况二：更新记录时 code_field_name 与原数据不一样
                need_update = False
                
                if code_field_name in processed_data:
                    code_value = processed_data[code_field_name]
                    if code_value:
                        # 情况一：创建记录时
                        if not original_data:
                            need_update = True
                        # 情况二：更新记录时，值有变化
                        elif code_field_name not in original_data or original_data[code_field_name] != code_value:
                            need_update = True
                
                if need_update:
                    code_value = processed_data[code_field_name]
                    related_model = field.related_model
                    
                    try:
                        # 优先从缓存中获取数据
                        related_instance = None
                        relation_data = []
                        
                        # 处理逗号分隔的值
                        code_values = [v.strip() for v in str(code_value).split(',')] if isinstance(code_value, str) else [code_value]
                        
                        # 检查缓存是否存在
                        if hasattr(self.hap_conn, 'cache_data') and hasattr(self.hap_conn, 'cache_indexes'):
                            worksheet_id = related_model.get_worksheet_id()
                            if worksheet_id in self.hap_conn.cache_indexes:
                                # 检查是否有 code_field_name 的索引
                                if code_field_name in self.hap_conn.cache_indexes[worksheet_id]:
                                    # 从索引中查找每个 code_value 对应的 row_id
                                    for cv in code_values:
                                        if cv in self.hap_conn.cache_indexes[worksheet_id][code_field_name]:
                                            row_id = self.hap_conn.cache_indexes[worksheet_id][code_field_name][cv]
                                            # 从缓存数据中获取完整信息
                                            if worksheet_id in self.hap_conn.cache_data and row_id in self.hap_conn.cache_data[worksheet_id]:
                                                # 构建关联字段数据，只需要传入 rowid
                                                relation_data.append(row_id)
                        
                        # 缓存中没有，从 API 查询
                        if not relation_data:
                            # 构建查询条件，使用 in 操作符
                            if len(code_values) > 1:
                                # 多个值使用 in 操作符
                                # filter_expr = f"{code_field_name}__in=[\"{\",\".join(code_values)}\"]"
                                filter_expr = Q(**{f"{code_field_name}__in": code_values})
                                related_instances = self.hap_conn.rows(related_model).filter(filter_expr).all()
                                for instance in related_instances.row_objects:
                                    if hasattr(instance, 'row_id'):
                                        relation_data.append(instance.row_id)
                            else:
                                # 单个值使用 eq 操作符
                                # filter_expr = f"{code_field_name}__eq={code_values[0]}"
                                filter_expr = Q(**{f"{code_field_name}__eq": code_values[0]})
                                related_instance = self.hap_conn.rows(related_model).filter(filter_expr).first()
                                if related_instance and hasattr(related_instance, 'row_id'):
                                    relation_data = [related_instance.row_id]
                        
                        # 更新关联字段数据
                        if relation_data:
                            processed_data[attr_name] = relation_data
                    except Exception as e:
                        # 忽略查询错误，保持原始数据
                        pass
        
        return processed_data

    def create(self, **kwargs) -> ModelType:
        """创建新模型实例"""
        # 处理关联字段
        processed_kwargs = self._process_relation_fields(kwargs)
        
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
                # 处理关联字段
                processed_data = self._process_relation_fields(data_dict)
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
                        created_models.append(model_instance)
                        self.row_objects.append(model_instance)
        
        return created_models

    def _update_cache_for_instance(self, model_instance: ModelType) -> None:
        """
        更新缓存中的单个模型实例
        
        Args:
            model_instance: 模型实例
        """
        worksheet_id = self.model.get_worksheet_id()
        cache_fields = getattr(self.model.Meta, 'cache', None)
        
        if not cache_fields:
            return
        
        # 检查缓存是否存在
        if worksheet_id not in self.hap_conn.cache_data or worksheet_id not in self.hap_conn.cache_indexes:
            return
        
        try:
            # 获取 rowid
            row_id = getattr(model_instance, 'row_id', None)
            if not row_id:
                return
            
            # 生成缓存值
            cache_value = {}
            # 首先添加 rowid
            cache_value['row_id'] = row_id
            # 然后添加用户指定的字段
            for field_name in cache_fields:
                if hasattr(model_instance, field_name):
                    cache_value[field_name] = getattr(model_instance, field_name)
            
            # 存储数据（以 rowid 为键）
            self.hap_conn.cache_data[worksheet_id][row_id] = cache_value
            
            # 更新 rowid 索引
            self.hap_conn.cache_indexes[worksheet_id]['rowid'][row_id] = row_id
            
            # 如果有主键，更新主键索引
            pk_field = self.model.get_pk_field()
            if pk_field and hasattr(model_instance, pk_field):
                pk_value = str(getattr(model_instance, pk_field))
                self.hap_conn.cache_indexes[worksheet_id]['pk'][pk_value] = row_id
                # 同时更新按字段名的索引
                if pk_field in self.hap_conn.cache_indexes[worksheet_id]:
                    self.hap_conn.cache_indexes[worksheet_id][pk_field][pk_value] = row_id
            
            # 如果有冲突字段，更新冲突字段索引
            conflict_fields = self.model.get_conflict_fields()
            if conflict_fields:
                key_parts = []
                for field_name in conflict_fields:
                    if hasattr(model_instance, field_name):
                        key_parts.append(str(getattr(model_instance, field_name)))
                conflict_key = tuple(key_parts)
                if not 'conflict' in self.hap_conn.cache_indexes[worksheet_id]:
                    self.hap_conn.cache_indexes[worksheet_id]['conflict'] = {}
                self.hap_conn.cache_indexes[worksheet_id]['conflict'][conflict_key] = row_id
            
            # 更新所有缓存字段的索引
            cache_fields = getattr(self.model.Meta, 'cache', None)
            if cache_fields:
                for field_name in cache_fields:
                    if hasattr(model_instance, field_name):
                        field_value = str(getattr(model_instance, field_name))
                        # 如果该字段有索引，更新它
                        if field_name in self.hap_conn.cache_indexes[worksheet_id]:
                            self.hap_conn.cache_indexes[worksheet_id][field_name][field_value] = row_id
        except Exception as e:
            # 更新缓存失败时记录错误，但不影响主流程
            console_log(f"更新缓存失败: {str(e)}")
    
    def _remove_from_cache(self, row_id: str) -> None:
        """
        从缓存中移除指定 rowid 的记录
        
        Args:
            row_id: 记录的 rowid
        """
        worksheet_id = self.model.get_worksheet_id()
        
        # 检查缓存是否存在
        if worksheet_id not in self.hap_conn.cache_data or worksheet_id not in self.hap_conn.cache_indexes:
            return
        
        try:
            # 从数据中移除
            if row_id in self.hap_conn.cache_data[worksheet_id]:
                del self.hap_conn.cache_data[worksheet_id][row_id]
            
            # 从 rowid 索引中移除
            if row_id in self.hap_conn.cache_indexes[worksheet_id]['rowid']:
                del self.hap_conn.cache_indexes[worksheet_id]['rowid'][row_id]
            
            # 从主键索引中移除（需要遍历查找）
            pk_index = self.hap_conn.cache_indexes[worksheet_id].get('pk', {})
            keys_to_remove = [key for key, value in pk_index.items() if value == row_id]
            for key in keys_to_remove:
                del pk_index[key]
            
            # 从冲突字段索引中移除（需要遍历查找）
            conflict_index = self.hap_conn.cache_indexes[worksheet_id].get('conflict', {})
            keys_to_remove = [key for key, value in conflict_index.items() if value == row_id]
            for key in keys_to_remove:
                del conflict_index[key]
        except Exception as e:
            # 移除缓存失败时记录错误，但不影响主流程
            console_log(f"从缓存中移除记录失败: {str(e)}")
    
    def create(self, **kwargs) -> ModelType:
        """创建新模型实例"""
        # 处理关联字段
        processed_kwargs = self._process_relation_fields(kwargs)
        
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.model._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 构建创建请求
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
        
        # 转换数据为字段列表，使用字段映射
        row_fields = HapUtils.convert_data_to_fieldslist(processed_kwargs, field_map=field_map, model=self.model)
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
                # 创建模型实例，传递 hap_conn 属性
                model_instance = self.model(**processed_kwargs, hap_conn=self.hap_conn)
                model_instance.row_id = row_ids[0]
                self.row_objects.append(model_instance)
                
                # 更新缓存
                self._update_cache_for_instance(model_instance)
                
                return model_instance
        
        raise Exception("Failed to create model instance")
    
    def bulk_create(self, data_list: List[Dict[str, Any]]) -> List[ModelType]:
        """批量创建模型实例"""
        # 分批处理，每批最多100条
        batch_size = 100
        total_items = len(data_list)
        created_models = []
        
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.model._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        for i in range(0, total_items, batch_size):
            batch_data = data_list[i:i+batch_size]
            
            # 构建创建请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
            
            # 转换数据为字段列表
            rows_data = []
            processed_batch_data = []
            for data_dict in batch_data:
                # 处理关联字段
                processed_data = self._process_relation_fields(data_dict)
                processed_batch_data.append(processed_data)
                
                row_fields = HapUtils.convert_data_to_fieldslist(processed_data, field_map=field_map, model=self.model)
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
                        # 创建模型实例，传递 hap_conn 属性
                        model_instance = self.model(**processed_batch_data[j], hap_conn=self.hap_conn)
                        model_instance.row_id = row_id
                        created_models.append(model_instance)
                        self.row_objects.append(model_instance)
                        
                        # 更新缓存
                        self._update_cache_for_instance(model_instance)
        
        return created_models
    
    def update(self, **kwargs) -> List[ModelType]:
        """批量更新模型实例"""
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.model._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 分批处理，每批最多100条
        batch_size = 100
        total_models = len(self.row_objects)
        updated_models = []
        
        for i in range(0, total_models, batch_size):
            batch_models = self.row_objects[i:i+batch_size]
            batch_row_ids = [model.row_id for model in batch_models if hasattr(model, 'row_id')]
            
            if not batch_row_ids:
                continue
            
            # 为每个模型实例处理关联字段，传递原始数据以便比较
            processed_batch_data = []
            for model in batch_models:
                # 获取模型实例的原始数据
                original_data = model.to_dict()
                # 处理关联字段，传递原始数据以便比较
                processed_data = self._process_relation_fields(kwargs, original_data)
                processed_batch_data.append(processed_data)
            
            # 构建更新请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
            
            # 转换数据为字段列表，使用字段映射
            if processed_batch_data:
                fields = HapUtils.convert_data_to_fieldslist(processed_batch_data[0], field_map=field_map, model=self.model)
            else:
                fields = HapUtils.convert_data_to_fieldslist(kwargs, field_map=field_map, model=self.model)
            
            payload = {
                "rowIds": batch_row_ids,
                "fields": fields,
                "triggerWorkflow": True
            }
            
            # 发送请求
            response = self.hap_conn._patch(endpoint=endpoint, payload=payload)
            
            # 处理响应
            if response.get('success'):
                for j, model in enumerate(batch_models):
                    # 更新模型实例的属性
                    if j < len(processed_batch_data):
                        for key, value in processed_batch_data[j].items():
                            setattr(model, key, value)
                    else:
                        for key, value in kwargs.items():
                            setattr(model, key, value)
                    updated_models.append(model)
                    
                    # 更新缓存
                    self._update_cache_for_instance(model)
        
        return updated_models
    
    def delete(self) -> List[bool]:
        """批量删除模型实例"""
        # 分批处理，每批最多100条
        batch_size = 100
        total_models = len(self.row_objects)
        results = [False] * total_models
        
        for i in range(0, total_models, batch_size):
            batch_models = self.row_objects[i:i+batch_size]
            batch_row_ids = [model.row_id for model in batch_models if hasattr(model, 'row_id')]
            
            if not batch_row_ids:
                continue
            
            # 构建删除请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
            
            payload = {
                "rowIds": batch_row_ids,
                "triggerWorkflow": True,
                "permanent": False
            }
            
            # 发送请求
            response = self.hap_conn._delete(endpoint=endpoint, payload=payload)
            
            # 处理响应
            if response.get('success'):
                for j, model in enumerate(batch_models):
                    if i + j < total_models:
                        results[i + j] = True
                        
                        # 从缓存中移除
                        if hasattr(model, 'row_id'):
                            self._remove_from_cache(model.row_id)
        
        # 从集合中移除已删除的模型实例
        self.row_objects = [model for i, model in enumerate(self.row_objects) if not results[i]]
        
        return results

    def upsert(self, data_list: List[Dict[str, Any]], exclude_none: bool = True, trigger_workflow: bool = True, when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover') -> 'HapRowSet[ModelType]':
        """批量 upsert 操作
        
        Args:
            data_list: 行数据字典列表
            exclude_none: 是否排除 data_list 中值为 None 的字段
            trigger_workflow: 是否触发工作流
            when_value_equal_then: 当字段值相等时的处理方式，默认'jumpover' 跳过 以减少不必要的【工作表事件】，'update' 则无论字段是否与data一样都更新
            
        Returns:
            HapRowSet: 处理后的模型实例集合
        """
        result_models = []
        create_list = []  # 存储需要创建的数据
        
        # 检查是否有冲突字段
        conflict_fields = self.model.get_conflict_fields()
        has_conflict_fields = bool(conflict_fields)
        
        # 如果没有冲突字段，直接批量创建
        if not has_conflict_fields:
            created_models = self.bulk_create(data_list)
            result_models.extend(created_models)
            return HapRowSet(models=result_models, model=self.model, hap_conn=self.hap_conn)
        
        import concurrent.futures
        
        # 处理数据列表，转换为字典格式并排除 None 值
        processed_data_list = []
        for data in data_list:
            if exclude_none:
                processed_data = {k: v for k, v in data.items() if v is not None}
            else:
                processed_data = data.copy()
            processed_data_list.append(processed_data)
        
        # 构建字段映射，将属性名映射到正确的字段名（优先使用 field_name）
        field_map = {}
        fields = self.model._get_fields()
        for attr_name, field in fields.items():
            if field.field_name:
                field_map[attr_name] = field.field_name
            else:
                field_map[attr_name] = attr_name
        
        # 定义查询和更新函数
        def process_item(data_dict):
            # 构建查询条件
            filter_conditions = []
            for field in conflict_fields:
                if field in data_dict:
                    value = data_dict[field]
                    if isinstance(value, str):
                        value = f"\"{value}\""
                    filter_conditions.append(f'{field}__eq={value}')

            # 如果没有有效的冲突字段值，返回需要创建
            if not filter_conditions:
                return (None, data_dict)
            
            # 执行查询
            filter_expression = " && ".join(filter_conditions)
            existing_models = self.hap_conn.rows(self.model).filter(filter_expression).all()
            models_count = existing_models.count()
            
            if models_count == 1:
                # 若有且仅有1条则执行更新
                existing_model = existing_models.first()
                # 创建只包含该模型的 HapRowSet
                single_model_set = HapRowSet(models=[existing_model], model=self.model, hap_conn=self.hap_conn)
                updated_models = single_model_set.update(**data_dict)
                if updated_models:
                    return (updated_models[0], None)
            elif models_count > 1:
                # 存在多条，则删除所有匹配行，然后准备创建
                existing_models.delete()
            return (None, data_dict)
        
        # 使用线程池并发处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.hap_conn.max_workers) as executor:
            futures = [executor.submit(process_item, data_dict) for data_dict in processed_data_list]
            
            # 收集结果
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result[0]:  # 更新成功的模型
                    result_models.append(result[0])
                elif result[1]:  # 需要创建的模型数据
                    create_list.append(result[1])
        
        # 批量创建需要新增的模型
        if create_list:
            created_models = self.bulk_create(create_list)
            result_models.extend(created_models)
        
        return HapRowSet(models=result_models, model=self.model, hap_conn=self.hap_conn)


# 示例模型定义
class Material(Model):
    """物料模型"""
    class Meta:
        worksheet_id = "t_material"
        conflict_fields = ["material_code"]
    
    material_code = TextField(max_length=50, description="物料编码")
    material_name = TextField(max_length=100, description="物料名称")
    material_spec = TextField(max_length=200, description="物料规格")
    unit = TextField(max_length=20, description="单位")
    price = NumField(description="单价")
    stock = NumField(description="库存")


class WorkCenter(Model):
    """工作中心模型"""
    class Meta:
        worksheet_id = "t_workcenter"
        conflict_fields = ["workcenter_code"]
    
    workcenter_code = TextField(max_length=50, description="工作中心编码")
    workcenter_name = TextField(max_length=100, description="工作中心名称")
    capacity = NumField(description="产能")


class MaterialWorkCenter(Model):
    """物料工作中心关联模型"""
    class Meta:
        worksheet_id = "t_mat_wc"
        conflict_fields = ["material_code", "workcenter_code"]
    
    material_code = TextField(max_length=50, description="物料编码")
    workcenter_code = TextField(max_length=50, description="工作中心编码")
    material = RelationField(Material, description="关联物料")
    workcenter = RelationField(WorkCenter, description="关联工作中心")
