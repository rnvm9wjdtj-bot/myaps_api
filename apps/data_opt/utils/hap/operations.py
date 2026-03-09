"""
增删改查操作
"""

from typing import Dict, Any, Optional, List, Type, Tuple, Union, Literal, Generator, Callable
import json
import time
from concurrent.futures import ThreadPoolExecutor
import asyncio

from ._base import console_log, HapConfig, ModelType, _MAX_CONCURRENCY, _DEFAULT_BUFFER_SIZE, _DEFAULT_MAX_RETRIES, _DEFAULT_RETRY_DELAY
from .models import Model
from .utils import (
    HapUtils, AdaptiveTimeout, EnhancedRetryStrategy, TokenBucket, DecimalEncoder, HapApiMonitor,
    StringInternPool, DataProcessingPipeline, LightweightRow, ObjectPool, ConnectionPoolWarmer, SmartBatchSizeCalculator,
    AdaptiveRateController, hap_async_timer
)
from .connection import HapConnection, AsyncHapConnection


# class HapOperations:
#     """HAP 操作类，包含增删改查等核心操作"""
    
#     def __init__(self, conn: HapConnection):
#         """
#         初始化 HAP 操作类
        
#         Args:
#             conn: HAP 连接实例
#         """
#         self.conn = conn
#         self.base_url = conn.base_url
#         self.headers = conn.headers
#         self.session = conn.session
    
#     # ==================== 核心操作方法 ====================
    
#     def create_row(self, model: Type[Model], data: Dict[str, Any], trigger_workflow: bool = True) -> Model:
#         """创建单行数据
        
#         Args:
#             model: 模型类
#             data: 数据字典
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             Model: 创建的模型实例
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/create"
        
#         # 转换数据格式
#         fields = HapUtils.convert_data_to_fieldslist(data, model=model)
#         payload = {
#             "fields": fields,
#             "triggerWorkflow": trigger_workflow
#         }
        
#         response = self.conn._post(endpoint, payload)
#         if response.get('success'):
#             row_data = response.get('data', {})
#             # 转换为模型实例
#             instance = model(**row_data)
#             # 更新缓存
#             self.conn._update_cache_for_instance(instance)
#             return instance
#         else:
#             raise Exception(f"创建失败: {response.get('message')}")
    
#     def update_row(self, model: Type[Model], row_id: str, data: Dict[str, Any], trigger_workflow: bool = True) -> Model:
#         """更新单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
#             data: 数据字典
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             Model: 更新后的模型实例
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/update/{row_id}"
        
#         # 转换数据格式
#         fields = HapUtils.convert_data_to_fieldslist(data, model=model)
#         payload = {
#             "fields": fields,
#             "triggerWorkflow": trigger_workflow
#         }
        
#         response = self.conn._patch(endpoint, payload)
#         if response.get('success'):
#             row_data = response.get('data', {})
#             # 转换为模型实例
#             instance = model(**row_data)
#             # 更新缓存
#             self.conn._update_cache_for_instance(instance)
#             return instance
#         else:
#             raise Exception(f"更新失败: {response.get('message')}")
    
#     def delete_row(self, model: Type[Model], row_id: str) -> bool:
#         """删除单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
            
#         Returns:
#             bool: 是否删除成功
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/delete/{row_id}"
        
#         response = self.conn._delete(endpoint)
#         if response.get('success'):
#             # 从缓存中移除
#             self.conn._remove_from_cache(row_id)
#             return True
#         else:
#             raise Exception(f"删除失败: {response.get('message')}")
    
#     def get_row(self, model: Type[Model], row_id: str) -> Optional[Model]:
#         """获取单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
            
#         Returns:
#             Optional[Model]: 模型实例，不存在则返回 None
#         """
#         # 先从缓存获取
#         cached_data = self.conn.get_cached_data(model, row_id, index_type='rowid')
#         if cached_data:
#             return model(**cached_data)
        
#         # 缓存未命中，从 API 获取
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/get/{row_id}"
        
#         response = self.conn._get(endpoint)
#         if response.get('success'):
#             row_data = response.get('data', {})
#             # 转换为模型实例
#             instance = model(**row_data)
#             # 更新缓存
#             self.conn._update_cache_for_instance(instance)
#             return instance
#         else:
#             return None
    
#     def list_rows(
#         self,
#         model: Type[Model],
#         page: int = 1,
#         page_size: int = 100,
#         filter: Optional[Dict[str, Any]] = None,
#         sort: Optional[List[Dict[str, Any]]] = None
#     ) -> Tuple[List[Model], int]:
#         """列出数据
        
#         Args:
#             model: 模型类
#             page: 页码，默认 1
#             page_size: 每页大小，默认 100
#             filter: 筛选条件
#             sort: 排序规则
            
#         Returns:
#             Tuple[List[Model], int]: (模型实例列表, 总条数)
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/list"
        
#         params = {
#             "page": page,
#             "pageSize": page_size
#         }
        
#         if filter:
#             params["filter"] = json.dumps(filter)
#         if sort:
#             params["sort"] = json.dumps(sort)
        
#         response = self.conn._get(endpoint, params=params)
#         if response.get('success'):
#             data = response.get('data', {})
#             rows = data.get('rows', [])
#             total = data.get('total', 0)
            
#             # 转换为模型实例
#             instances = [model(**row) for row in rows]
#             # 更新缓存
#             self.conn._update_cache(model, rows)
            
#             return instances, total
#         else:
#             raise Exception(f"获取列表失败: {response.get('message')}")
    
#     def bulk_create(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         trigger_workflow: bool = True
#     ) -> List[Model]:
#         """批量创建
        
#         Args:
#             model: 模型类
#             data_list: 数据列表
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             List[Model]: 创建的模型实例列表
#         """
#         if not data_list:
#             return []
        
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/batch"
        
#         rows_data = []
#         for data in data_list:
#             fields = HapUtils.convert_data_to_fieldslist(data, model=model)
#             rows_data.append({'fields': fields})
        
#         payload = {
#             "rows": rows_data,
#             "triggerWorkflow": trigger_workflow
#         }
        
#         response = self.conn._post(endpoint, payload)
#         if response.get('success'):
#             row_ids = response.get('data', {}).get('rowIds', [])
#             instances = []
#             for i, row_id in enumerate(row_ids):
#                 row_data = {"rowid": row_id}
#                 if i < len(data_list):
#                     row_data.update(data_list[i])
#                 instance = model(**row_data)
#                 instances.append(instance)
#             return instances
#         else:
#             message = response.get('message') or response.get('error_msg') or response.get('error') or 'Unknown error'
#             raise Exception(f"批量创建失败: {message}")
    
#     def bulk_update(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         trigger_workflow: bool = True
#     ) -> List[Model]:
#         """批量更新
        
#         Args:
#             model: 模型类
#             data_list: 数据列表（必须包含 row_id）
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             List[Model]: 更新的模型实例列表
#         """
#         if not data_list:
#             return []
        
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/batch"
        
#         rows_data = []
#         for data in data_list:
#             row_id = data.get('row_id') or data.get('rowid')
#             if not row_id:
#                 raise ValueError("数据必须包含 row_id 字段")
            
#             data_copy = data.copy()
#             data_copy.pop('row_id', None)
#             data_copy.pop('rowid', None)
            
#             fields = HapUtils.convert_data_to_fieldslist(data_copy, model=model)
#             rows_data.append({"rowId": row_id, "fields": fields})
        
#         payload = {
#             "rows": rows_data,
#             "triggerWorkflow": trigger_workflow
#         }
        
#         response = self.conn._patch(endpoint, payload)
#         if response.get('success'):
#             row_ids = response.get('data', {}).get('rowIds', [])
#             instances = []
#             for i, row_id in enumerate(row_ids):
#                 row_data = {"rowid": row_id}
#                 if i < len(data_list):
#                     row_data.update(data_list[i])
#                 instance = model(**row_data)
#                 instances.append(instance)
#             return instances
#         else:
#             message = response.get('message') or response.get('error_msg') or response.get('error') or 'Unknown error'
#             raise Exception(f"批量更新失败: {message}")
    
#     def bulk_delete(self, model: Type[Model], row_ids: List[str]) -> bool:
#         """批量删除
        
#         Args:
#             model: 模型类
#             row_ids: 行 ID 列表
            
#         Returns:
#             bool: 是否删除成功
#         """
#         if not row_ids:
#             return True
        
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/rows/batch-delete"
        
#         payload = {
#             "rowIds": row_ids
#         }
        
#         response = self.conn._delete(endpoint, payload)
#         if response.get('success'):
#             # 从缓存中移除
#             for row_id in row_ids:
#                 self.conn._remove_from_cache(row_id)
#             return True
#         else:
#             message = response.get('message') or response.get('error_msg') or response.get('error') or 'Unknown error'
#             raise Exception(f"批量删除失败: {message}")
    
#     def _process_complex_fields(self, model: Type[Model], data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
#         """
#         处理关联字段等复杂类型的字段
        
#         Args:
#             model: 模型类
#             data: 包含字段数据的字典
#             original_data: 原始数据字典，用于比较字段值是否变化
            
#         Returns:
#             Dict[str, Any]: 处理后的字段数据字典
#         """
#         processed_data = data.copy()
        
#         # 获取模型的所有字段
#         fields = model._get_fields()
        
#         # 遍历所有字段，查找关联字段和文本字段
#         for attr_name, field in fields.items():
#             if hasattr(field, 'process_relation'):
#                 # 调用 RelationField 自身的处理方法
#                 processed_data = field.process_relation(processed_data, original_data, self.conn)
#             elif hasattr(field, 'process_mapping'):
#                 # 调用 TextField 自身的处理方法
#                 processed_data = field.process_mapping(processed_data, original_data)
#             elif hasattr(field, 'process_subtable'):
#                 # 调用 SubtableField 自身的处理方法
#                 processed_data = field.process_subtable(processed_data, original_data, self.conn)
        
#         return processed_data
    
#     def _batch_process_items(self, model: Type[Model], data_list: List[Dict[str, Any]], pk_field: Optional[str], conflict_fields: Optional[List[str]], when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover', trigger_workflow: bool = True) -> List[Model]:
#         """批量处理多个数据项的 upsert 操作"""
#         if not data_list:
#             return []
        
#         # 分类数据：需要更新的和需要创建的
#         to_update = []
#         to_create = []
        
#         # 逐行构建筛选条件并立即查询
#         field_map = model._get_field_map()
        
#         try:
#             for data_dict in data_list:
#                 filter_conditions = []
                
#                 # 优先使用主键字段判断
#                 if pk_field:
#                     pk_field_name = field_map.get(pk_field, pk_field)
#                     if pk_field in data_dict:
#                         match_value = data_dict[pk_field]
#                     else:
#                         match_value = data_dict[pk_field_name]
#                     filter_conditions.append(f'{pk_field_name}__eq="{match_value}"')
#                 # 其次使用冲突字段判断
#                 elif conflict_fields:
#                     for field in conflict_fields:
#                         match_value = None
#                         if field in data_dict:
#                             match_value = data_dict[field]
#                             filter_conditions.append(f'{field}__eq="{match_value}"')
#                         elif field in field_map:
#                             c_field_name = field_map[field]
#                             if c_field_name in data_dict:
#                                 match_value = data_dict[c_field_name]
#                                 filter_conditions.append(f'{c_field_name}__eq="{match_value}"')
                
#                 if filter_conditions:
#                     try:
#                         # 构建查询条件
#                         condition_str = " && ".join(filter_conditions)
#                         # 立即执行查询
#                         from .data_objects import HapQuerySet
#                         queryset = HapQuerySet(model, self.conn)
#                         existing_rows = queryset.filter(condition_str).all()
#                         rows_count = existing_rows.count()
                        
#                         if rows_count == 1:
#                             # 找到一条记录，需要更新
#                             existing_model = existing_rows.first()
#                             to_update.append((existing_model, data_dict))
#                         elif rows_count > 1:
#                             # 找到多条记录，删除后创建新记录
#                             existing_rows.delete()
#                             to_create.append(data_dict)
#                         else:
#                             # 没有找到记录，需要创建
#                             to_create.append(data_dict)
#                     except Exception as e:
#                         console_log.error(f"查询数据失败: {data_dict}, 错误: {e}")
#                         # 查询失败，作为需要创建处理
#                         to_create.append(data_dict)
#                 else:
#                     to_create.append(data_dict)
#         except Exception as e:
#             console_log.error(f"构建查询条件失败: {e}")
#             # 所有数据都作为需要创建处理
#             to_create.extend(data_list)
        
#         # 批量更新
#         updated_models = []
#         if to_update:
#             try:
#                 # 按更新数据分组
#                 update_groups = {}
#                 for model_instance, data_dict in to_update:
#                     # 构建更新数据
#                     update_data = data_dict.copy()
#                     row_id = getattr(model_instance, 'row_id', None) or getattr(model_instance, 'rowid', None)
#                     if row_id:
#                         update_data['row_id'] = row_id
#                         if row_id not in update_groups:
#                             update_groups[row_id] = []
#                         update_groups[row_id].append(update_data)
                
#                 # 批量更新
#                 for row_id, update_datas in update_groups.items():
#                     updated = self.bulk_update(model, update_datas, trigger_workflow)
#                     updated_models.extend(updated)
#             except Exception as e:
#                 console_log.error(f"批量更新失败: {e}")
#                 # 更新失败，作为需要创建处理
#                 for model_instance, data_dict in to_update:
#                     to_create.append(data_dict)
        
#         # 批量创建
#         created_models = []
#         if to_create:
#             try:
#                 created = self.bulk_create(model, to_create, trigger_workflow)
#                 created_models.extend(created)
#             except Exception as e:
#                 console_log.error(f"批量创建失败: {e}")
        
#         return updated_models + created_models
    
#     def upsert(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         exclude_none: bool = True,
#         trigger_workflow: bool = True,
#         when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
#     ) -> 'HapRowSet':
#         """批量 upsert
        
#         Args:
#             model: 模型类
#             data_list: 数据列表
#             exclude_none: 是否排除值为 None 的字段，默认 True
#             trigger_workflow: 是否触发工作流，默认 True
#             when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
#                 - 'jumpover': 跳过不更新
#                 - 'update': 强制更新
                
#         Returns:
#             HapRowSet: 包含 upsert 后模型实例的行集合
#         """
#         from .data_objects import HapRowSet
        
#         if not data_list:
#             return HapRowSet(model, [])
        
#         # 获取主键字段
#         pk_field = model.get_pk_field()
        
#         # 检查是否有冲突字段
#         conflict_fields = model.get_conflict_fields()
#         has_conflict_fields = bool(conflict_fields)
        
#         # 如果既没有主键字段也没有冲突字段，直接批量创建
#         if not pk_field and not has_conflict_fields:
#             # 处理数据列表
#             processed_data_list = []
#             for data in data_list:
#                 # 处理关联字段
#                 processed_data = self._process_complex_fields(model, data)
                
#                 # 过滤掉值为 None 的字段
#                 if exclude_none:
#                     processed_data = {k: v for k, v in processed_data.items() if v is not None}
#                 processed_data_list.append(processed_data)
            
#             created_models = self.bulk_create(model, processed_data_list, trigger_workflow)
#             return HapRowSet(model, created_models)
        
#         # 调整处理顺序：先判断记录存在，再处理复杂字段
#         processed_data_list = []
#         field_map = model._get_field_map()
        
#         for data in data_list:
#             # 构建查询条件
#             filter_conditions = []
            
#             # 优先使用主键字段判断
#             if pk_field:
#                 pk_field_name = field_map.get(pk_field, pk_field)
#                 if pk_field in data:
#                     match_value = data[pk_field]
#                 elif pk_field_name in data:
#                     match_value = data[pk_field_name]
#                 else:
#                     # 没有主键值，直接处理
#                     processed_data = self._process_complex_fields(model, data)
#                     if exclude_none:
#                         processed_data = {k: v for k, v in processed_data.items() if v is not None}
#                     processed_data_list.append(processed_data)
#                     continue
#                 filter_conditions.append(f'{pk_field_name}__eq="{match_value}"')
#             # 其次使用冲突字段判断
#             elif conflict_fields:
#                 for field in conflict_fields:
#                     match_value = None
#                     if field in data:
#                         match_value = data[field]
#                         filter_conditions.append(f'{field}__eq="{match_value}"')
#                     elif field in field_map:
#                         c_field_name = field_map[field]
#                         if c_field_name in data:
#                             match_value = data[c_field_name]
#                             filter_conditions.append(f'{c_field_name}__eq="{match_value}"')
            
#             # 获取原始数据
#             original_data = None
#             if filter_conditions:
#                 try:
#                     # 构建查询条件
#                     condition_str = " && ".join(filter_conditions)
#                     # 执行查询
#                     from .data_objects import HapQuerySet
#                     queryset = HapQuerySet(model, self.conn)
#                     existing_rows = queryset.filter(condition_str).all()
#                     if existing_rows.count() == 1:
#                         # 找到一条记录，获取其原始数据
#                         existing_model = existing_rows.first()
#                         # 转换为字典
#                         original_data = {}
#                         for attr_name, field in model._get_fields().items():
#                             field_name = field_map.get(attr_name, attr_name)
#                             if hasattr(existing_model, attr_name):
#                                 original_data[field_name] = getattr(existing_model, attr_name)
#                 except Exception as e:
#                     # 查询失败，继续处理
#                     console_log.error(f"查询原始数据失败: {e}")
#                     pass
            
#             # 处理复杂字段（传递原始数据进行比较）
#             processed_data = self._process_complex_fields(model, data, original_data)
            
#             # 过滤掉值为 None 的字段
#             if exclude_none:
#                 processed_data = {k: v for k, v in processed_data.items() if v is not None}
#             processed_data_list.append(processed_data)
        
#         # 根据数据量选择处理方式
#         result_models = []
#         if len(processed_data_list) > 10:  # 数据量较大时使用批量处理
#             # 批量处理数据
#             all_models = self._batch_process_items(
#                 model,
#                 processed_data_list,
#                 pk_field,
#                 conflict_fields,
#                 when_value_equal_then,
#                 trigger_workflow
#             )
#             result_models.extend(all_models)
#         else:  # 数据量较小时使用顺序处理
#             # 顺序处理数据
#             create_list = []
#             update_list = []
            
#             for data_dict in processed_data_list:
#                 filter_conditions = []
                
#                 # 优先使用主键字段判断
#                 if pk_field:
#                     pk_field_name = field_map.get(pk_field, pk_field)
#                     if pk_field in data_dict:
#                         match_value = data_dict[pk_field]
#                     else:
#                         match_value = data_dict[pk_field_name]
#                     filter_conditions.append(f'{pk_field_name}__eq="{match_value}"')
#                 # 其次使用冲突字段判断
#                 elif conflict_fields:
#                     for field in conflict_fields:
#                         match_value = None
#                         if field in data_dict:
#                             match_value = data_dict[field]
#                             filter_conditions.append(f'{field}__eq="{match_value}"')
#                         elif field in field_map:
#                             c_field_name = field_map[field]
#                             if c_field_name in data_dict:
#                                 match_value = data_dict[c_field_name]
#                                 filter_conditions.append(f'{c_field_name}__eq="{match_value}"')
                
#                 if filter_conditions:
#                     try:
#                         # 构建查询条件
#                         condition_str = " && ".join(filter_conditions)
#                         # 执行查询
#                         from .data_objects import HapQuerySet
#                         queryset = HapQuerySet(model, self.conn)
#                         existing_rows = queryset.filter(condition_str).all()
                        
#                         if existing_rows.count() == 1:
#                             # 找到一条记录，需要更新
#                             existing = existing_rows.first()
#                             row_id = getattr(existing, 'row_id', None) or getattr(existing, 'rowid', None)
#                             if row_id:
#                                 update_data = data_dict.copy()
#                                 update_data['row_id'] = row_id
#                                 update_list.append(update_data)
#                             else:
#                                 create_list.append(data_dict)
#                         else:
#                             # 没有找到记录或找到多条记录，需要创建
#                             create_list.append(data_dict)
#                     except Exception as e:
#                         console_log.error(f"查询数据失败: {data_dict}, 错误: {e}")
#                         # 查询失败，作为需要创建处理
#                         create_list.append(data_dict)
#                 else:
#                     create_list.append(data_dict)
            
#             # 批量创建需要新增的模型
#             if create_list:
#                 created = self.bulk_create(model, create_list, trigger_workflow)
#                 result_models.extend(created)
            
#             # 批量更新需要更新的模型
#             if update_list:
#                 updated = self.bulk_update(model, update_list, trigger_workflow)
#                 result_models.extend(updated)
        
#         # 批量更新缓存
#         self.conn._update_cache_for_instances(result_models)
        
#         return HapRowSet(model, result_models)
    
#     def get_worksheet_info(self, model: Type[Model]) -> Dict[str, Any]:
#         """获取工作表信息
        
#         Args:
#             model: 模型类
            
#         Returns:
#             Dict[str, Any]: 工作表信息
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}"
        
#         response = self.conn._get(endpoint)
#         if response.get('success'):
#             return response.get('data', {})
#         else:
#             raise Exception(f"获取工作表信息失败: {response.get('message')}")
    
#     def get_fields_info(self, model: Type[Model]) -> List[Dict[str, Any]]:
#         """获取字段信息
        
#         Args:
#             model: 模型类
            
#         Returns:
#             List[Dict[str, Any]]: 字段信息列表
#         """
#         worksheet_id = model.get_worksheet_id()
#         endpoint = f"/v3/app/worksheets/{worksheet_id}/fields"
        
#         response = self.conn._get(endpoint)
#         if response.get('success'):
#             return response.get('data', {}).get('fields', [])
#         else:
#             raise Exception(f"获取字段信息失败: {response.get('message')}")


# class AsyncHapOperations:
#     """异步 HAP 操作类"""
    
#     def __init__(self, async_conn: AsyncHapConnection):
#         """
#         初始化异步 HAP 操作类
        
#         Args:
#             async_conn: 异步 HAP 连接实例
#         """
#         self.async_conn = async_conn
#         self.sync_conn = async_conn._sync_conn
#         self.operations = HapOperations(self.sync_conn)
#         self._executor = async_conn._executor
    
#     def _run_in_executor(self, func: Callable, *args, **kwargs) -> asyncio.Future:
#         """在线程池中执行同步函数
        
#         Args:
#             func: 要执行的同步函数
#             *args: 位置参数
#             **kwargs: 关键字参数
            
#         Returns:
#             asyncio.Future: 异步 Future 对象
#         """
#         loop = asyncio.get_event_loop()
#         if kwargs:
#             def wrapper():
#                 return func(*args, **kwargs)
#             return loop.run_in_executor(self._executor, wrapper)
#         else:
#             return loop.run_in_executor(self._executor, func, *args)
    
#     @hap_async_timer()
#     async def create_row(self, model: Type[Model], data: Dict[str, Any], trigger_workflow: bool = True) -> Model:
#         """异步创建单行数据
        
#         Args:
#             model: 模型类
#             data: 数据字典
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             Model: 创建的模型实例
#         """
#         return await self._run_in_executor(
#             self.operations.create_row,
#             model,
#             data,
#             trigger_workflow
#         )
    
#     @hap_async_timer()
#     async def update_row(self, model: Type[Model], row_id: str, data: Dict[str, Any], trigger_workflow: bool = True) -> Model:
#         """异步更新单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
#             data: 数据字典
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             Model: 更新后的模型实例
#         """
#         return await self._run_in_executor(
#             self.operations.update_row,
#             model,
#             row_id,
#             data,
#             trigger_workflow
#         )
    
#     @hap_async_timer()
#     async def delete_row(self, model: Type[Model], row_id: str) -> bool:
#         """异步删除单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
            
#         Returns:
#             bool: 是否删除成功
#         """
#         return await self._run_in_executor(
#             self.operations.delete_row,
#             model,
#             row_id
#         )
    
#     @hap_async_timer()
#     async def get_row(self, model: Type[Model], row_id: str) -> Optional[Model]:
#         """异步获取单行数据
        
#         Args:
#             model: 模型类
#             row_id: 行 ID
            
#         Returns:
#             Optional[Model]: 模型实例，不存在则返回 None
#         """
#         return await self._run_in_executor(
#             self.operations.get_row,
#             model,
#             row_id
#         )
    
#     @hap_async_timer()
#     async def list_rows(
#         self,
#         model: Type[Model],
#         page: int = 1,
#         page_size: int = 100,
#         filter: Optional[Dict[str, Any]] = None,
#         sort: Optional[List[Dict[str, Any]]] = None
#     ) -> Tuple[List[Model], int]:
#         """异步列出数据
        
#         Args:
#             model: 模型类
#             page: 页码，默认 1
#             page_size: 每页大小，默认 100
#             filter: 筛选条件
#             sort: 排序规则
            
#         Returns:
#             Tuple[List[Model], int]: (模型实例列表, 总条数)
#         """
#         return await self._run_in_executor(
#             self.operations.list_rows,
#             model,
#             page,
#             page_size,
#             filter,
#             sort
#         )
    
#     @hap_async_timer()
#     async def bulk_create(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         trigger_workflow: bool = True
#     ) -> List[Model]:
#         """异步批量创建
        
#         Args:
#             model: 模型类
#             data_list: 数据列表
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             List[Model]: 创建的模型实例列表
#         """
#         return await self._run_in_executor(
#             self.operations.bulk_create,
#             model,
#             data_list,
#             trigger_workflow
#         )
    
#     @hap_async_timer()
#     async def bulk_update(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         trigger_workflow: bool = True
#     ) -> List[Model]:
#         """异步批量更新
        
#         Args:
#             model: 模型类
#             data_list: 数据列表（必须包含 row_id）
#             trigger_workflow: 是否触发工作流，默认 True
            
#         Returns:
#             List[Model]: 更新的模型实例列表
#         """
#         return await self._run_in_executor(
#             self.operations.bulk_update,
#             model,
#             data_list,
#             trigger_workflow
#         )
    
#     @hap_async_timer()
#     async def bulk_delete(self, model: Type[Model], row_ids: List[str]) -> bool:
#         """异步批量删除
        
#         Args:
#             model: 模型类
#             row_ids: 行 ID 列表
            
#         Returns:
#             bool: 是否删除成功
#         """
#         return await self._run_in_executor(
#             self.operations.bulk_delete,
#             model,
#             row_ids
#         )
    
#     @hap_async_timer()
#     async def upsert(
#         self,
#         model: Type[Model],
#         data_list: List[Dict[str, Any]],
#         exclude_none: bool = True,
#         trigger_workflow: bool = True,
#         when_value_equal_then: Literal['jumpover', 'update'] = 'jumpover'
#     ) -> 'HapRowSet':
#         """异步批量 upsert
        
#         Args:
#             model: 模型类
#             data_list: 数据列表
#             exclude_none: 是否排除值为 None 的字段，默认 True
#             trigger_workflow: 是否触发工作流，默认 True
#             when_value_equal_then: 值相等时的处理方式，默认 'jumpover'
#                 - 'jumpover': 跳过不更新
#                 - 'update': 强制更新
                
#         Returns:
#             HapRowSet: 包含 upsert 后模型实例的行集合
#         """
#         return await self._run_in_executor(
#             self.operations.upsert,
#             model,
#             data_list,
#             exclude_none,
#             trigger_workflow,
#             when_value_equal_then
#         )
    
#     @hap_async_timer()
#     async def get_worksheet_info(self, model: Type[Model]) -> Dict[str, Any]:
#         """异步获取工作表信息
        
#         Args:
#             model: 模型类
            
#         Returns:
#             Dict[str, Any]: 工作表信息
#         """
#         return await self._run_in_executor(
#             self.operations.get_worksheet_info,
#             model
#         )
    
#     @hap_async_timer()
#     async def get_fields_info(self, model: Type[Model]) -> List[Dict[str, Any]]:
#         """异步获取字段信息
        
#         Args:
#             model: 模型类
            
#         Returns:
#             List[Dict[str, Any]]: 字段信息列表
#         """
#         return await self._run_in_executor(
#             self.operations.get_fields_info,
#             model
#         )
