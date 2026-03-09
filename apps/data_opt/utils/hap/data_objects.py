"""
查询条件和查询集
"""

import json
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List, Type, Tuple, Union, Literal, Generator, Callable, AsyncGenerator, Generic, TYPE_CHECKING
from datetime import datetime, timedelta

from ..data_processor import DataProcessor
from ._base import console_log, filelog_error, HapConfig, ModelType, _MAX_CONCURRENCY, _DEFAULT_BUFFER_SIZE, _DEFAULT_MAX_RETRIES, _DEFAULT_RETRY_DELAY
from .fields import StrField, NumField, RelationField, ChoiceField, SubtableField
from .utils import(
    HapUtils, AdaptiveTimeout, EnhancedRetryStrategy, TokenBucket, DecimalEncoder, HapApiMonitor,
    StringInternPool, DataProcessingPipeline, LightweightRow, ObjectPool, ConnectionPoolWarmer, SmartBatchSizeCalculator,
    AdaptiveRateController, hap_async_timer
)

if TYPE_CHECKING:
    from .connection import HapConnection, AsyncHapConnection



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
    
    def to_filter_condition(self, field_map: Optional[Dict[str, str]] = None) -> dict:
        """
        将 Q 对象转换为明道云 API 要求的筛选条件格式
        
        Args:
            field_map: 属性名到 field_name 的映射字典，用于将属性名转换为字段名
        
        Returns:
            dict: 符合明道云 API 要求的筛选条件
        """
        # 处理逻辑运算符
        if self.connector:
            children_conditions = []
            for child in self.children:
                child_condition = child.to_filter_condition(field_map)
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
            
            # 使用 field_map 将属性名转换为 field_name
            if field_map and field in field_map:
                field = field_map[field]
            
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


# def set_global_hap_conn(conn: HapConnection):
#     """设置全局 HAP 连接实例
    
#     Args:
#         conn: HAP 连接实例
#     """
#     global hap_conn
#     hap_conn = conn


# def get_global_hap_conn() -> HapConnection:
#     """获取全局 HAP 连接实例
    
#     Returns:
#         HapConnection: HAP 连接实例
#     """
#     global hap_conn
#     if not hap_conn:
#         raise Exception("HAP 连接未初始化，请先调用 set_global_hap_conn")
#     return hap_conn


# class HapQuery:
#     """HAP 查询条件构建器
    
#     用于构建复杂的查询条件，支持链式调用。
#     """
    
#     def __init__(self, model: Type[Model]):
#         """
#         初始化查询条件构建器
        
#         Args:
#             model: 模型类
#         """
#         self.model = model
#         self.conditions = []
#         self.sort = []
#         self.page = 1
#         self.page_size = 100
    
#     def filter(self, **kwargs) -> 'HapQuery':
#         """添加筛选条件
        
#         支持的运算符：
#         - eq: 等于
#         - ne: 不等于
#         - gt: 大于
#         - ge: 大于等于
#         - lt: 小于
#         - le: 小于等于
#         - in_: 包含在列表中
#         - notin: 不包含在列表中
#         - contains: 包含字符串
#         - notcontains: 不包含字符串
#         - isempty: 为空
#         - isnotempty: 不为空
        
#         Args:
#             **kwargs: 筛选条件，格式为 field__operator=value
            
#         Returns:
#             HapQuery: 自身实例，支持链式调用
#         """
#         for key, value in kwargs.items():
#             if '__' in key:
#                 field, op = key.rsplit('__', 1)
#                 # 标准化字段名
#                 field = HapUtils.normalize_field_name(self.model, field)
                
#                 condition = {
#                     "type": "condition",
#                     "field": field,
#                     "operator": op,
#                     "value": value if op not in ['isempty', 'isnotempty'] else []
#                 }
#                 self.conditions.append(condition)
#         return self
    
#     def order_by(self, *fields) -> 'HapQuery':
#         """添加排序规则
        
#         Args:
#             *fields: 排序字段，以负号开头表示降序
            
#         Returns:
#             HapQuery: 自身实例，支持链式调用
#         """
#         for field in fields:
#             if field.startswith('-'):
#                 field_name = field[1:]
#                 is_asc = False
#             else:
#                 field_name = field
#                 is_asc = True
            
#             # 标准化字段名
#             field_name = HapUtils.normalize_field_name(self.model, field_name)
            
#             self.sort.append({
#                 "field": field_name,
#                 "isAsc": is_asc
#             })
#         return self
    
#     def limit(self, page_size: int) -> 'HapQuery':
#         """设置每页大小
        
#         Args:
#             page_size: 每页大小
            
#         Returns:
#             HapQuery: 自身实例，支持链式调用
#         """
#         self.page_size = page_size
#         return self
    
#     def offset(self, page: int) -> 'HapQuery':
#         """设置页码
        
#         Args:
#             page: 页码
            
#         Returns:
#             HapQuery: 自身实例，支持链式调用
#         """
#         self.page = page
#         return self
    
#     def get_filter(self) -> Dict[str, Any]:
#         """获取筛选条件
        
#         Returns:
#             Dict[str, Any]: 筛选条件
#         """
#         if not self.conditions:
#             return {}
#         elif len(self.conditions) == 1:
#             return self.conditions[0]
#         else:
#             return {
#                 "type": "group",
#                 "logic": "AND",
#                 "children": self.conditions
#             }
    
#     def get_sort(self) -> List[Dict[str, Any]]:
#         """获取排序规则
        
#         Returns:
#             List[Dict[str, Any]]: 排序规则
#         """
#         return self.sort
    
#     def get_page(self) -> int:
#         """获取页码
        
#         Returns:
#             int: 页码
#         """
#         return self.page
    
#     def get_page_size(self) -> int:
#         """获取每页大小
        
#         Returns:
#             int: 每页大小
#         """
#         return self.page_size


class HapRowSet(Generic[ModelType]):
    """行集合类，用于管理多个模型实例"""
    def __init__(self, models: List[ModelType], model: Type[ModelType], hap_conn: 'HapConnection'):
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
        endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/batch"
        for i in range(0, total_items, batch_size):
            batch_data = data_list[i:i+batch_size]
            # 转换数据为字段列表
            rows_data = []
            processed_batch_data = []
            for data_dict in batch_data:
                processed_data = data_dict
                processed_batch_data.append(processed_data)
                
                row_fields = HapUtils.convert_data_to_fieldslist(processed_data, model=self.model)
                rows_data.append({'fields': row_fields})
            
            payload = {
                "rows": rows_data,
                "triggerWorkflow": True
            }
            
            # 发送请求
            try:
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
                else:
                    # 记录失败信息
                    error_msg = response.get('error_msg', 'Unknown error')
                    console_log.error(f"批量创建失败，批次 {i//batch_size + 1}: {error_msg}")
                    # 尝试单条创建失败的数据
                    for data in processed_batch_data:
                        try:
                            # 单条创建
                            single_response = self.hap_conn._post(endpoint, {
                                "rows": [{'fields': HapUtils.convert_data_to_fieldslist(data, model=self.model)}],
                                "triggerWorkflow": True
                            })
                            if single_response.get('success'):
                                row_id = single_response.get('data', {}).get('rowIds', [])[0]
                                model_instance = self.model(**data)
                                model_instance.row_id = row_id
                                self.row_objects.append(model_instance)
                                created_models.append(model_instance)
                        except Exception as e:
                            console_log.error(f"单条创建失败: {data}, 错误: {e}")
            except Exception as e:
                # 捕获网络等异常
                console_log.error(f"批量创建请求失败，批次 {i//batch_size + 1}: {e}")
                # 尝试单条创建
                for data in processed_batch_data:
                    try:
                        single_response = self.hap_conn._post(endpoint, {
                            "rows": [{'fields': HapUtils.convert_data_to_fieldslist(data, model=self.model)}],
                            "triggerWorkflow": True
                        })
                        if single_response.get('success'):
                            row_id = single_response.get('data', {}).get('rowIds', [])[0]
                            model_instance = self.model(**data)
                            model_instance.row_id = row_id
                            self.row_objects.append(model_instance)
                            created_models.append(model_instance)
                    except Exception as single_error:
                        console_log.error(f"单条创建失败: {data}, 错误: {single_error}")
        
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
                raise Exception(f"Failed to update model instances: {response.get('error_msg', 'Unknown error')}")
        
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
            raise Exception(f"Failed to delete model instances: {response.get('error_msg', 'Unknown error')}")

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
        failed_data = []  # 记录处理失败的数据
        
        # 逐行构建筛选条件并立即查询
        field_map = self.model._get_field_map()
        
        # filter_conditions = []
        # if pk_field:
        #     pk_values = []
        #     pk_field_name = field_map[pk_field]
        #     for data_dict in data_list:
        #         if pk_field in data_dict:
        #             pk_values.append(data_dict[pk_field])
        #         else:
        #             pk_values.append(data_dict[pk_field_name])
        #     filter_conditions.append(f"{pk_field_name}__in={json.dumps(pk_values, ensure_ascii=False)}")
        # elif conflict_fields:
        #     for data_dict in data_list:
        #         for field in conflict_fields:
        #             row_filter_conditions = []
        #             match_value = None
        #             if field in data_dict:
        #                 match_value = data_dict[field]
        #                 row_filter_conditions.append(f'{field}__eq=\"{match_value}\"')
        #             elif field in field_map:
        #                 c_field_name = field_map[field]
        #                 if c_field_name in data_dict:
        #                     match_value = data_dict[c_field_name]
        #                     row_filter_conditions.append(f'{c_field_name}__eq=\"{match_value}\"')
        #         filter_conditions.append(' && '.join(row_filter_conditions))
        try:
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
                    try:
                        # 构建查询条件
                        condition_str = " && ".join(filter_conditions)
                        # 立即执行查询
                        existing_rows = self.hap_conn.rows(self.model).filter(condition_str).all()
                        rows_count = existing_rows.count()
                        
                        if rows_count == 1:
                            # 找到一条记录，需要更新
                            existing_model = existing_rows.first()
                            to_update.append((existing_model, data_dict))
                        elif rows_count > 1:
                            # 找到多条记录，删除后创建新记录
                            existing_rows.delete()
                            to_create.append(data_dict)
                        else:
                            # 没有找到记录，需要创建
                            to_create.append(data_dict)
                    except Exception as e:
                        console_log.error(f"查询数据失败: {data_dict}, 错误: {e}")
                        # 查询失败，作为需要创建处理
                        to_create.append(data_dict)
                else:
                    to_create.append(data_dict)
        except Exception as e:
            console_log.error(f"构建查询条件失败: {e}")
            # 所有数据都作为需要创建处理
            to_create.extend(data_list)
        
        # 批量更新
        updated_models = []
        if to_update:
            try:
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
            except Exception as e:
                console_log.error(f"批量更新失败: {e}")
                # 更新失败，将这些数据作为需要创建处理
                for model_instance, data_dict in to_update:
                    to_create.append(data_dict)
        
        # 批量创建
        created_models = []
        if to_create:
            try:
                created = self.bulk_create(to_create)
                created_models.extend(created)
            except Exception as e:
                console_log.error(f"批量创建失败: {e}")
                # 创建失败，记录为失败数据
                failed_data.extend(to_create)
        
        # 合并结果
        all_models = updated_models + created_models
        
        # 如果有失败数据，尝试单条处理
        if failed_data:
            console_log.info(f"尝试单条处理 {len(failed_data)} 条失败数据")
            for data in failed_data:
                try:
                    # 单条 upsert
                    result = self._process_item(data, pk_field, conflict_fields, when_value_equal_then)
                    if result[0]:  # 更新成功
                        all_models.append(result[0])
                    elif result[1]:  # 需要创建
                        # 尝试单条创建
                        single_created = self.bulk_create([result[1]])
                        all_models.extend(single_created)
                except Exception as e:
                    console_log.error(f"单条处理失败: {data}, 错误: {e}")
        
        return all_models

    def _process_items_parallel(self, data_list, pk_field, conflict_fields, when_value_equal_then):
        """并行处理多个数据项的 upsert 操作"""
        from concurrent.futures import as_completed
        
        results = []
        failed_data = []  # 记录失败的数据
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
                filelog_error.error(f"处理 {data} 时出错: {exc}")
                # 记录失败的数据，稍后重试
                failed_data.append(data)
        
        # 处理剩余的数据（如果有）
        if len(data_list) > max_tasks:
            remaining_data = data_list[max_tasks:]
            for data in remaining_data:
                try:
                    result = self._process_item(data, pk_field, conflict_fields, when_value_equal_then)
                    results.append(result)
                except Exception as exc:
                    filelog_error.error(f"处理 {data} 时出错: {exc}")
                    # 记录失败的数据，稍后重试
                    failed_data.append(data)
        
        # 重试失败的数据（最多重试3次）
        for retry in range(3):
            if not failed_data:
                break
            retry_failed = []
            console_log.info(f"第 {retry + 1} 次重试，共 {len(failed_data)} 条数据")
            for data in failed_data:
                try:
                    result = self._process_item(data, pk_field, conflict_fields, when_value_equal_then)
                    results.append(result)
                except Exception as exc:
                    console_log.error(f"重试处理 {data} 时出错: {exc}")
                    retry_failed.append(data)
            failed_data = retry_failed
        
        # 如果仍有失败的数据，记录到错误日志
        if failed_data:
            filelog_error.error(f"最终失败的数据共 {len(failed_data)} 条: {failed_data}")
            # 将失败的数据作为需要创建的数据返回，避免丢失
            for data in failed_data:
                results.append((None, data))
        
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
        
        # 获取主键字段
        pk_field = self.model.get_pk_field()
        
        # 检查是否有冲突字段
        conflict_fields = self.model.get_conflict_fields()
        has_conflict_fields = bool(conflict_fields)
        
        # 如果既没有主键字段也没有冲突字段，直接批量创建
        if not pk_field and not has_conflict_fields:
            # 处理数据列表
            processed_data_list = []
            for data in data_list:
                # 处理关联字段
                processed_data = self._process_complex_fields(data)
                
                # 过滤掉值为 None 的字段
                if exclude_none:
                    processed_data = {k: v for k, v in processed_data.items() if v is not None}
                processed_data_list.append(processed_data)
            
            created_models = self.bulk_create(processed_data_list)
            return HapRowSet(models=created_models, model=self.model, hap_conn=self.hap_conn)
        
        # 调整处理顺序：先判断记录存在，再处理复杂字段
        processed_data_list = []
        field_map = self.model._get_field_map()
        
        for data in data_list:
            # 构建查询条件
            filter_conditions = []
            
            # 优先使用主键字段判断
            if pk_field:
                pk_field_name = field_map[pk_field]
                if pk_field in data:
                    match_value = data[pk_field]
                elif pk_field_name in data:
                    match_value = data[pk_field_name]
                else:
                    # 没有主键值，直接处理
                    processed_data = self._process_complex_fields(data)
                    if exclude_none:
                        processed_data = {k: v for k, v in processed_data.items() if v is not None}
                    processed_data_list.append(processed_data)
                    continue
                filter_conditions.append(f'{pk_field_name}__eq="{match_value}"')
            # 其次使用冲突字段判断
            elif conflict_fields:
                for field in conflict_fields:
                    match_value = None
                    if field in data:
                        match_value = data[field]
                        filter_conditions.append(f'{field}__eq="{match_value}"')
                    elif field in field_map:
                        c_field_name = field_map[field]
                        if c_field_name in data:
                            match_value = data[c_field_name]
                            filter_conditions.append(f'{c_field_name}__eq="{match_value}"')
            
            # 获取原始数据
            original_data = None
            if filter_conditions:
                try:
                    # 构建查询条件
                    condition_str = " && ".join(filter_conditions)
                    # 执行查询
                    existing_rows = self.hap_conn.rows(self.model).filter(condition_str).all()
                    if existing_rows.count() == 1:
                        # 找到一条记录，获取其原始数据
                        existing_model = existing_rows.first()
                        # 转换为字典
                        original_data = {}
                        for attr_name, field in self.model._get_fields().items():
                            field_name = field_map.get(attr_name, attr_name)
                            if hasattr(existing_model, attr_name):
                                original_data[field_name] = getattr(existing_model, attr_name)
                except Exception as e:
                    # 查询失败，继续处理
                    pass
            
            # 处理复杂字段（传递原始数据进行比较）
            processed_data = self._process_complex_fields(data, original_data)
            
            # 过滤掉值为 None 的字段
            if exclude_none:
                processed_data = {k: v for k, v in processed_data.items() if v is not None}
            processed_data_list.append(processed_data)
        
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


class HapQuerySet(Generic[ModelType]):
    """查询集类，用于构建和执行查询"""
    def __init__(self, model: Type[ModelType], hap_conn: 'HapConnection'):
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
        response = self.hap_conn._get(endpoint=endpoint, params={})

        if response.get("success"):
            row_data = response['data']

            # 使用优化的数据处理管道
            processed_data = DataProcessingPipeline.process_row_data(row_data)
            
            # 创建模型实例
            model_instance = self.model(**processed_data)
            row_id_value = row_data.get('rowid') or row_data.get('rowId')
            if row_id_value:
                model_instance.row_id = row_id_value
            model_instance.hap_conn = self.hap_conn
            
            return model_instance
        
        return None
    

    def filter(self, *args, **kwargs) -> 'HapQuerySet[ModelType]':
        """添加筛选条件
        
        支持多种调用方式：
        1. 使用 Q 对象: filter(Q(field1__eq=value1) & Q(field2__eq=value2))
        2. 使用表达式字符串: filter("field1__eq=value1 && field2__eq=value2")
        3. 使用关键字参数: filter(field1__eq=value1, field2__eq=value2)
        
        支持同时使用属性名或 field_name 作为字段标识
        """
        # 获取字段映射（属性名 -> field_name）
        field_map = self.model._get_field_map()
        
        # 处理 Q 对象
        if args and isinstance(args[0], Q):
            self.filter_condition = args[0].to_filter_condition(field_map)
        # 处理表达式字符串
        elif args and isinstance(args[0], str):
            self.filter_condition = HapUtils.expression_to_filter_condition(args[0], field_map)
        # 处理关键字参数
        elif kwargs:
            q = Q(**kwargs)
            self.filter_condition = q.to_filter_condition(field_map)
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
        batch_size = min(self.page_size, 1000)
        
        # 预分配列表大小，减少动态扩容开销
        if self.limit:
            estimated_size = min(self.limit, batch_size * 2)
            all_models = []
        
        while True:
            # 构建查询参数
            payload = {
                "pageSize": batch_size,
                "pageIndex": page_index,
                "includeTotalCount": False,
                "filter": self.filter_condition,
                "sorts": self.sorts
            }
            
            # 发送请求
            endpoint = f"/v3/app/worksheets/{self.model.get_worksheet_id()}/rows/list"
            response = self.hap_conn._post(endpoint=endpoint, payload=payload)
            
            if response.get('success'):
                rows = response.get('data', {}).get('rows', [])
                
                for row_dict in rows:
                    # 使用优化的数据处理管道，一次性处理所有步骤
                    processed_data = DataProcessingPipeline.process_row_data(row_dict)
                    
                    # 创建模型实例
                    model_instance = self.model(**processed_data)
                    row_id = row_dict.get('rowid') or row_dict.get('rowId')
                    if row_id:
                        model_instance.row_id = row_id
                    model_instance.hap_conn = self.hap_conn
                    self.hap_conn._update_cache_for_instance(model_instance)
                    all_models.append(model_instance)
            
            # 应用 limit
            if self.limit and len(all_models) >= self.limit:
                all_models = all_models[:self.limit]
                break
            
            # 检查是否还有更多数据
            if not response.get('success') or len(response.get('data', {}).get('rows', [])) < batch_size:
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
                rows = response.get('data', {}).get('rows', [])
                
                for row_dict in rows:
                    # 使用优化的数据处理管道
                    processed_data = DataProcessingPipeline.process_row_data(row_dict)
                    
                    # 创建模型实例
                    model_instance = self.model(**processed_data)
                    row_id = row_dict.get('rowid') or row_dict.get('rowId')
                    if row_id:
                        model_instance.row_id = row_id
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
        return row_set.upsert(data_list, exclude_none, trigger_workflow, when_value_equal_then  )
        return row_set.upsert(data_list, exclude_none, trigger_workflow, when_value_equal_then  )


class AsyncHapQuerySet(Generic[ModelType]):
    """异步查询集包装器
    
    包装同步的 HapQuerySet，提供异步查询操作。
    链式调用方法（filter, order_by 等）保持同步，
    执行方法（all, first, count 等）改为异步。
    
    Example:
        >>> query = async_hap.query(MyModel)
        >>> query = query.filter(status="active").order_by("-created")
        >>> results = await query.all()
        >>> first = await query.first()
        >>> count = await query.count()
    """
    
    def __init__(
        self, 
        model: Type[ModelType], 
        sync_conn: 'HapConnection', 
        executor: ThreadPoolExecutor,
        async_hap: 'AsyncHapConnection' = None
    ):
        """
        初始化异步查询集
        
        Args:
            model: 模型类
            sync_conn: 同步 HAP 连接
            executor: 线程池执行器
            async_hap: 异步 HAP 连接实例（用于获取监控器）
        """
        self._model = model
        self._sync_conn = sync_conn
        self._executor = executor
        self._async_hap = async_hap
        self._sync_query = sync_conn.rows(model)
    
    def _run_in_executor(self, func: Callable, *args, **kwargs) -> asyncio.Future:
        """在线程池中执行同步函数"""
        loop = asyncio.get_event_loop()
        if kwargs:
            def wrapper():
                return func(*args, **kwargs)
            return loop.run_in_executor(self._executor, wrapper)
        else:
            return loop.run_in_executor(self._executor, func, *args)
    
    # ==================== 链式查询构建（同步）====================
    
    def filter(self, *args, **kwargs) -> 'AsyncHapQuerySet[ModelType]':
        """添加过滤条件
        
        Args:
            *args: Q 对象
            **kwargs: 字段过滤条件，如 name__eq="test"
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.filter(*args, **kwargs)
        return self
    
    def exclude(self, *args, **kwargs) -> 'AsyncHapQuerySet[ModelType]':
        """添加排除条件
        
        Args:
            *args: Q 对象
            **kwargs: 字段排除条件
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.exclude(*args, **kwargs)
        return self
    
    def order_by(self, *fields: str) -> 'AsyncHapQuerySet[ModelType]':
        """设置排序字段
        
        Args:
            *fields: 排序字段，前缀 "-" 表示降序，如 "-created"
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query = self._sync_query.order_by(*fields)
        return self
    
    def limit(self, n: int) -> 'AsyncHapQuerySet[ModelType]':
        """设置返回数量限制
        
        Args:
            n: 限制数量
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query.limit = n
        return self
    
    def offset(self, n: int) -> 'AsyncHapQuerySet[ModelType]':
        """设置偏移量
        
        Args:
            n: 偏移数量
            
        Returns:
            AsyncHapQuerySet: 自身，支持链式调用
        """
        self._sync_query.offset = n
        return self
    
    # ==================== 查询执行（异步）====================
    
    async def all(self) -> HapRowSet[ModelType]:
        """异步获取所有结果
        
        Returns:
            HapRowSet[ModelType]: 查询结果集
        """
        return await self._run_in_executor(self._sync_query.all)
    
    async def first(self) -> Optional[ModelType]:
        """异步获取第一条结果
        
        Returns:
            Optional[ModelType]: 第一个模型实例，不存在则返回 None
        """
        return await self._run_in_executor(self._sync_query.first)
    
    async def count(self) -> int:
        """异步获取记录数
        
        Returns:
            int: 符合条件的记录总数
        """
        return await self._run_in_executor(self._sync_query.count)
    
    async def stream(self, batch_size: int = 100) -> AsyncGenerator[ModelType, None]:
        """异步流式获取结果
        
        分批获取数据，避免内存溢出，适合处理大数据量。
        
        Args:
            batch_size: 每批获取数量，默认 100
            
        Yields:
            ModelType: 模型实例
            
        Example:
            >>> async for item in query.stream(batch_size=50):
            ...     await process_item(item)
        """
        offset = 0
        while True:
            batch_query = self._sync_query.limit(batch_size).offset(offset)
            batch = await self._run_in_executor(batch_query.all)
            
            if not batch.row_objects:
                break
                
            for item in batch.row_objects:
                yield item
                
            if len(batch.row_objects) < batch_size:
                break
                
            offset += batch_size
    
    # ==================== 数据修改（异步）====================
    
    @hap_async_timer()
    async def upsert(
        self,
        data_list: List[Dict[str, Any]],
        exclude_none: bool = True,
        trigger_workflow: bool = True,
        when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
    ) -> HapRowSet[ModelType]:
        """异步 upsert 操作
        
        Args:
            data_list: 要 upsert 的数据列表
            exclude_none: 是否排除值为 None 的字段，默认 True
            trigger_workflow: 是否触发工作流，默认 True
            when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
            
        Returns:
            HapRowSet[ModelType]: 包含 upsert 后模型实例的行集合
        """
        return await self._run_in_executor(
            self._sync_query.upsert,
            data_list,
            exclude_none=exclude_none,
            trigger_workflow=trigger_workflow,
            when_value_equal_then=when_value_equal_then
        )
    
    @hap_async_timer()
    async def bulk_create(
        self,
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量创建
        
        Args:
            data_list: 要创建的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 创建的模型实例列表
        """
        return await self._run_in_executor(
            self._sync_query.bulk_create,
            data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def bulk_update(
        self,
        data_list: List[Dict[str, Any]],
        trigger_workflow: bool = True
    ) -> List[ModelType]:
        """异步批量更新
        
        Args:
            data_list: 要更新的数据列表
            trigger_workflow: 是否触发工作流，默认 True
            
        Returns:
            List[ModelType]: 更新的模型实例列表
        """
        return await self._run_in_executor(
            self._sync_query.bulk_update,
            data_list,
            trigger_workflow=trigger_workflow
        )
    
    @hap_async_timer()
    async def delete(self, trigger_workflow: bool = True) -> bool:
        """异步删除模型实例
        
        Args:
            trigger_workflow: 是否触发工作流
            
        Returns:
            bool: 删除是否成功
        """
        return await self._run_in_executor(self._sync_query.delete, trigger_workflow)
    
    async def bulk_upsert(
        self,
        data_list: List[Dict[str, Any]],
        batch_size: int = 100,
        **kwargs
    ) -> List[ModelType]:
        """批量 upsert，分批处理大数据量
        
        Args:
            data_list: 要 upsert 的数据列表
            batch_size: 每批处理数量，默认 100
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            List[ModelType]: 处理后的模型实例列表
        """
        results = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i+batch_size]
            if batch:
                batch_result = await self.upsert(batch, **kwargs)
                results.extend(batch_result.row_objects)
        return results
    
    async def bulk_upsert_parallel(
        self,
        data_list: List[Dict[str, Any]],
        batch_size: int = 100,
        max_concurrency: int = _MAX_CONCURRENCY
    ) -> List[ModelType]:
        """并行批量 upsert，提高处理速度
        
        Args:
            data_list: 要 upsert 的数据列表
            batch_size: 每批处理数量，默认 100
            max_concurrency: 最大并发数，默认 _MAX_CONCURRENCY
            
        Returns:
            List[ModelType]: 处理后的模型实例列表
        """
        # 分批次
        batches = []
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i+batch_size]
            if batch:
                batches.append(batch)
        
        # 并行处理
        results = []
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def process_batch(batch):
            async with semaphore:
                batch_result = await self.upsert(batch)
                return batch_result.row_objects
        
        tasks = [process_batch(batch) for batch in batches]
        batch_results = await asyncio.gather(*tasks)
        
        for batch_result in batch_results:
            results.extend(batch_result)
        
        return results

    @hap_async_timer()
    async def upsert_from_generator(
        self,
        data_source,
        buffer_size: int = None,
        max_concurrency: int = None,
        max_retries: int = None,
        retry_delay: float = None,
        adaptive: bool = True,
        target_qps: float = None,
        **kwargs
    ) -> int:
        """从生成器函数批量 upsert 数据（高性能版本）
        
        针对数据同步场景优化，支持批量收集和并发处理。
        包含错误处理、重试机制和自适应速率控制。
        
        Args:
            data_source: 数据生成器函数，每次调用返回一个数据列表的生成器
            buffer_size: 缓冲区大小，None 时使用自适应调节
            max_concurrency: 最大并发数，None 时使用自适应调节
            max_retries: 最大重试次数，None 时使用配置默认值
            retry_delay: 重试延迟（秒），None 时使用配置默认值
            adaptive: 是否启用自适应速率控制，默认 True
            target_qps: 目标 QPS（每秒请求数），None 时自动从 HapConfig 获取
            **kwargs: 传递给 upsert 的其他参数
            
        Returns:
            int: 处理的总记录数
            
        Example:
            >>> # 自适应模式（推荐，自动从 HapConfig 获取 QPS）
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(data_gen_func)
            >>> 
            >>> # 固定参数模式
            >>> count = await async_hap.rows(MyModel).upsert_from_generator(
            ...     data_gen_func, buffer_size=200, max_concurrency=20
            ... )
        """
        import logging
        import time
        from typing import Callable, Generator
        
        model = self._model
        
        if callable(data_source):
            data_generator = data_source()
        else:
            raise ValueError("data_source 必须是生成器函数，请传递函数名而非函数调用结果")
        
        if max_retries is None:
            max_retries = _DEFAULT_MAX_RETRIES
        if retry_delay is None:
            retry_delay = _DEFAULT_RETRY_DELAY
        
        if target_qps is None:
            target_qps = getattr(self._sync_conn, 'qps_limit', 10.0)
            console_log.info(f"从 HapConfig 自动获取 QPS 限制: {target_qps}")
        
        smart_batch_calculator = getattr(self._sync_conn, '_batch_size_calculator', None)
        
        if adaptive:
            if buffer_size is None and smart_batch_calculator:
                initial_buffer = _DEFAULT_BUFFER_SIZE
            else:
                initial_buffer = buffer_size or _DEFAULT_BUFFER_SIZE
            
            controller = AdaptiveRateController(
                initial_buffer_size=initial_buffer,
                initial_concurrency=max_concurrency or _MAX_CONCURRENCY,
                target_qps=target_qps,
            )
            current_buffer_size = controller.buffer_size
            current_concurrency = controller.concurrency
        else:
            if buffer_size is None and smart_batch_calculator:
                current_buffer_size = _DEFAULT_BUFFER_SIZE
            else:
                current_buffer_size = buffer_size or _DEFAULT_BUFFER_SIZE
            current_concurrency = max_concurrency or _MAX_CONCURRENCY
        
        buffer = []
        total_count = 0
        semaphore = asyncio.Semaphore(current_concurrency)
        tasks = []
        
        async def do_upsert_with_retry(data_batch, batch_index):
            nonlocal current_buffer_size, current_concurrency, semaphore
            
            async with semaphore:
                start_time = time.time()
                for attempt in range(max_retries):
                    try:
                        result = await self.upsert(data_batch, **kwargs)
                        response_time = time.time() - start_time
                        
                        if adaptive:
                            controller.record_request(True, response_time)
                        
                        if self._async_hap and self._async_hap._monitor:
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._async_hap._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=True
                            )
                        
                        return result.count()
                    except Exception as e:
                        response_time = time.time() - start_time
                        console_log.warning(f"批次 {batch_index} 第 {attempt + 1} 次尝试失败: {e}")
                        
                        if adaptive:
                            controller.record_request(False, response_time)
                        
                        if self._async_hap and self._async_hap._monitor:
                            worksheet_id = getattr(model, '_worksheet_id', model.__name__)
                            self._async_hap._monitor.record_request(
                                method="POST",
                                endpoint=f"/api/v3/app/worksheets/{worksheet_id}/rows/upsert",
                                data={"batch_size": len(data_batch)},
                                response_time=response_time,
                                success=False,
                                error=str(e)
                            )
                        
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                        else:
                            console_log.error(f"批次 {batch_index} 最终失败，跳过 {len(data_batch)} 条数据")
                            return 0
                return 0
        
        batch_index = 0
        for data in data_generator:
            buffer.extend(data)
            
            if len(buffer) >= current_buffer_size:
                batch_index += 1
                
                if adaptive and batch_index % 5 == 0:
                    new_buffer_size, new_concurrency = controller.adjust()
                    
                    if new_concurrency != current_concurrency:
                        current_concurrency = new_concurrency
                        semaphore = asyncio.Semaphore(current_concurrency)
                        console_log.info(f"自适应调整: 并发数 -> {current_concurrency}")
                    
                    if new_buffer_size != current_buffer_size:
                        current_buffer_size = new_buffer_size
                        console_log.info(f"自适应调整: 缓冲区 -> {current_buffer_size}")
                    
                    if batch_index % 20 == 0:
                        stats = controller.get_stats()
                        console_log.info(
                            f"统计: 成功率={stats['success_rate']:.2%}, "
                            f"平均响应={stats['avg_response_time']:.2f}s, "
                            f"当前参数: buffer={current_buffer_size}, concurrency={current_concurrency}"
                        )
                
                tasks.append(asyncio.create_task(
                    do_upsert_with_retry(buffer[:], batch_index)
                ))
                buffer = []
                
                if len(tasks) >= current_concurrency * 2:
                    done, pending = await asyncio.wait(
                        tasks, 
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        try:
                            total_count += await task
                        except Exception as e:
                            console_log.error(f"任务执行失败: {e}")
                    tasks = list(pending)
        
        if buffer:
            batch_index += 1
            tasks.append(asyncio.create_task(
                do_upsert_with_retry(buffer, batch_index)
            ))
        
        if tasks:
            done, _ = await asyncio.wait(tasks)
            for task in done:
                try:
                    total_count += await task
                except Exception as e:
                    console_log.error(f"任务执行失败: {e}")
        
        console_log.info(f"upsert_from_generator 完成，总处理 {total_count} 条记录")
        return total_count