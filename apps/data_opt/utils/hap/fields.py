"""
字段定义
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, Union, List, TYPE_CHECKING

from ..data_processor import DataProcessor
from .utils import HapUtils
from globalobjects import logger as log_config
from config.settings import LOG_LEVEL


logger = log_config.get_logger(__name__, level=LOG_LEVEL)

if TYPE_CHECKING:
    from .data_objects import Q, HapRowSet, HapQuerySet, AsyncHapQuerySet


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
        self.attr_name: Optional[str] = None  # 保存属性名
    
    def __set_name__(self, owner, name):
        # 当 field_name 未提供时，使用属性名作为默认值
        if self.field_name is None:
            self.field_name = name
        self.model = owner
        self.attr_name = name  # 直接保存属性名


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
    
    def _get_attr_name(self) -> str:
        """获取当前字段在模型中的属性名"""
        # 直接返回在 __set_name__ 中保存的属性名
        if self.attr_name:
            return self.attr_name
        return self.field_name
    
    def _resolve_field_name(self, field_name: str) -> str:
        """将属性名解析为字段名"""
        if not self.model:
            return field_name
        
        # 直接尝试从 __dict__ 中查找字段，避免调用 _get_field_map 造成循环依赖
        try:
            if hasattr(self.model, field_name):
                field_obj = getattr(self.model, field_name)
                if isinstance(field_obj, Field) and field_obj.field_name:
                    return field_obj.field_name
        except Exception:
            pass
        
        return field_name
    
    def _check_need_update(self, processed_data: Dict[str, Any], original_data: Optional[Dict[str, Any]], followwith_field: str) -> bool:
        """检查是否需要更新映射字段"""
        follow_value = processed_data.get(followwith_field)
        if not follow_value:
            return False
        
        # 情况一：创建记录时
        if not original_data:
            return True
        
        # 情况二：更新记录时，值有变化
        original_key = self._resolve_field_name(followwith_field)
        if original_key not in original_data:
            return True
        
        return not DataProcessor.is_equal(original_data[original_key], follow_value)
    
    def _get_followwith_field(self, processed_data: Dict[str, Any]) -> Optional[str]:
        """获取并验证 follow_with 字段名"""
        if not self.follow_with:
            return None
        
        followwith_field = self.follow_with
        if followwith_field not in processed_data:
            followwith_field = self._resolve_field_name(followwith_field)
        
        return followwith_field if followwith_field in processed_data else None
    
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
        
        # 直接使用传入的数据字典，不创建副本
        
        # 获取属性名和 follow_with 字段
        attr_name = self._get_attr_name()
        followwith_field = self._get_followwith_field(data)
        
        if not followwith_field:
            return data
        
        # 检查是否需要更新
        if not self._check_need_update(data, original_data, followwith_field):
            return data
        
        # 执行映射
        follow_value = data[followwith_field]
        mapped_value = self.mapper.get(str(follow_value))
        if mapped_value is not None:
            data[attr_name] = mapped_value
        
        return data


class ChoiceField(StrField):
    """选项字段
    继承自 StrField，支持多选项的映射处理
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
    
    def _parse_values(self, value_to_process: Any) -> List[str]:
        """解析输入值为字符串列表"""
        if isinstance(value_to_process, list):
            return [str(v).strip() for v in value_to_process]
        
        if isinstance(value_to_process, str):
            try:
                import json
                parsed_value = json.loads(value_to_process)
                if isinstance(parsed_value, list):
                    return [str(v).strip() for v in parsed_value]
            except:
                pass
            # 按分隔符分割
            return [v.strip() for v in value_to_process.split(self.spliter)]
        
        return [str(value_to_process).strip()]
    
    def _apply_mapping(self, values: List[str]) -> List[str]:
        """应用映射到值列表"""
        if not self.mapper:
            return values
        return [self.mapper.get(v, v) for v in values]
    
    def process_mapping(self, data: Dict[str, Any], original_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        处理选择字段的映射关系
        支持多选项的批量映射处理
        """
        attr_name = self._get_attr_name()
        
        # 确定要处理的值
        value_to_process = None
        if self.follow_with:
            followwith_field = self._get_followwith_field(data)
            if not followwith_field:
                return data
            
            if not self._check_need_update(data, original_data, followwith_field):
                return data
            
            value_to_process = data[followwith_field]
        else:
            # 直接使用 self.field_name，避免调用 _get_field_map()
            field_name = self.field_name
            if field_name not in data and attr_name not in data:
                return data
            # 尝试从 field_name 或 attr_name 中获取值
            value_to_process = data.get(field_name) or data.get(attr_name)
        
        # 解析值并应用映射
        values = self._parse_values(value_to_process)
        # data[attr_name] = self._apply_mapping(values)
        data[field_name] = self._apply_mapping(values)
        
        return data


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
        
        # 直接使用传入的数据字典，不创建副本
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            reverse_field_map = self.model._get_reverse_field_map()
            attr_name = reverse_field_map.get(self.field_name, None)
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 确保使用 follow_with 字段，而不是关联字段本身
        # 从 data 中移除关联字段本身，避免干扰
        if attr_name in data:
            del data[attr_name]
        
        # 检查是否需要更新关联字段
        followwith_field = self.follow_with
        if followwith_field not in data:
            try:
                # 直接尝试从模型属性中查找，避免调用 _get_field_map()
                if hasattr(self.model, followwith_field):
                    field_obj = getattr(self.model, followwith_field)
                    if isinstance(field_obj, Field) and field_obj.field_name:
                        followwith_field = field_obj.field_name
            except (AttributeError, KeyError):
                # 模型没有对应属性或字段
                pass
        
        # 确保 follow_with 字段存在
        if followwith_field not in data:
            return data
        
        need_update = False
        code_value = str(data[followwith_field])
        if code_value:
            # 情况一：创建记录时
            if not original_data:
                need_update = True
            # 情况二：更新记录时，值有变化
            else:
                # 确定在 original_data 中使用的键名（字段名）
                original_key = followwith_field
                try:
                    # 直接尝试从模型属性中查找，避免调用 _get_field_map()
                    if hasattr(self.model, followwith_field):
                        field_obj = getattr(self.model, followwith_field)
                        if isinstance(field_obj, Field) and field_obj.field_name:
                            original_key = field_obj.field_name
                except (AttributeError, KeyError):
                    # 模型没有对应属性或字段
                    pass
                
                if original_key not in original_data or not DataProcessor.is_equal(original_data.get(original_key), code_value):
                    need_update = True
        
        if not need_update or not hap_conn:
            return data
        
        # 处理延时导入的模型
        if isinstance(self.related_model, str):
            # 从 hap_conn 中获取注册的模型类
            related_model = hap_conn.get_model(self.related_model)
        else:
            related_model = self.related_model
        
        try:

            # 调用实例方法查询关联数据
            relation_data = self._query_relation_data(
                code_value=code_value,
                hap_conn=hap_conn
        )

            # 更新关联字段数据
            if relation_data:
                data[self.field_name] = relation_data
        except Exception as e:
            # 忽略查询错误，保持原始数据
            pass
        
        return data


    def _query_relation_data(self, code_value, hap_conn):
        """
        查询关联数据并返回关联记录的 row_id 列表

        Args:
            code_value: 关联值
            followwith_field: 跟随字段
            hap_conn: HapConnection 实例
            
        Returns:
            List[Any]: 关联记录的 row_id 列表
        """
        relation_data = []
        followwith_field = self.follow_with
        # 处理逗号分隔的值
        code_values = [v.strip() for v in str(code_value).split(',')] if isinstance(code_value, str) else [code_value]
        
        # 处理延时导入的模型
        if isinstance(self.related_model, str):
            # 从 hap_conn 中获取注册的模型类
            related_model = hap_conn.get_model(self.related_model)
        else:
            related_model = self.related_model
        
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
                worksheet_indexes = hap_conn.cache_indexes.get(worksheet_id)
                if worksheet_indexes:
                    field_index = worksheet_indexes.get(cache_key)
                    if field_index:
                        # 从索引中查找每个 code_value 对应的 row_id
                        worksheet_cache_data = hap_conn.cache_data.get(worksheet_id)
                        if worksheet_cache_data:
                            for cv in code_values:
                                row_id = field_index.get(cv)
                                if row_id and row_id in worksheet_cache_data:
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
            from .data_objects import Q
            if len(code_values) > 1:
                # 多个值使用 in 操作符
                filter_expr = Q(**{f"{query_field}__in": code_values})
                related_instances = hap_conn.rows(related_model).filter(filter_expr).all()
                for instance in related_instances.row_objects:
                    if hasattr(instance, 'row_id'):
                        relation_data.append(instance.row_id)
                        # 将查询结果添加到缓存中
                        hap_conn._update_cache_for_instance(instance)
            else:
                # 单个值使用 eq 操作符
                filter_expr = Q(**{f"{query_field}__eq": code_values[0]})
                related_instance = hap_conn.rows(related_model).filter(filter_expr).all().first()
                if related_instance and hasattr(related_instance, 'row_id'):
                    relation_data = [related_instance.row_id]
                    # 将查询结果添加到缓存中
                    hap_conn._update_cache_for_instance(related_instance)
        
        return relation_data



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
        
        # 直接使用传入的数据字典，不创建副本
        
        # 获取当前字段在模型中的属性名
        attr_name = None
        if self.model:
            # 直接使用保存的 attr_name，避免调用 _get_reverse_field_map()
            attr_name = self.attr_name
        if not attr_name:
            # 如果无法获取属性名，使用字段名作为后备
            attr_name = self.field_name
        
        # 确保使用 data_source 字段，而不是子表字段本身
        # 从 data 中移除子表字段本身，避免干扰
        if attr_name in data:
            del data[attr_name]
        
        # parent_row = hap_conn.rows(self.model).get_by_rowid(row_id=data.get('row_id'))
        # 不使用 _get_field_map()，直接在需要时从模型属性中查找
        parent_field_map = {}
        subtable_field_map = {}
        
        # 检查数据源字段是否存在
        data_source_field = self.data_source
        if not data_source_field in data:
            try:
                # 直接从模型属性中查找字段
                if hasattr(self.model, data_source_field):
                    field_obj = getattr(self.model, data_source_field)
                    if isinstance(field_obj, Field) and field_obj.field_name:
                        data_source_field = field_obj.field_name
            except (AttributeError, KeyError):
                # 模型没有对应属性或字段
                pass
        
        # 确保数据源字段存在
        if data_source_field not in data:
            return data
        
        need_update = False
        source_value = data[data_source_field]
        if source_value:
            # 情况一：创建记录时
            if not original_data:
                need_update = True
            # 情况二：更新记录时，值有变化
            else:
                # 确定在 original_data 中使用的键名（字段名）
                original_key = data_source_field
                try:
                    # 直接从模型属性中查找字段
                    if hasattr(self.model, data_source_field):
                        field_obj = getattr(self.model, data_source_field)
                        if isinstance(field_obj, Field) and field_obj.field_name:
                            original_key = field_obj.field_name
                except (AttributeError, KeyError):
                    # 模型没有对应属性或字段
                    pass
                
                if original_key not in original_data:
                    need_update = True
                else:
                    # 深度比较子表数据内容
                    if not self._subtable_data_equal(source_value, original_data.get(original_key)):
                        need_update = True
        
        if not need_update:
            return data
        
        try:
            # 解析数据源为字典列表
            if isinstance(source_value, str):
                subtable_data_list = json.loads(source_value)
            elif isinstance(source_value, list):
                subtable_data_list = source_value
            else:
                return data
            
            # 确保是字典列表
            if not isinstance(subtable_data_list, list) or not all(isinstance(item, dict) for item in subtable_data_list):
                return data
            
            # 获取子表模型的冲突字段
            conflict_fields = getattr(self.subtable_model.Meta, 'conflict_fields', None)
            
            # 获取子表模型的主键字段
            subtable_pk_field = self.subtable_model.get_pk_field()
            try:
                subtable_pk_field_name = subtable_field_map[subtable_pk_field] if subtable_pk_field else None
            except KeyError:
                # 主键字段不在字段映射中
                subtable_pk_field_name = None
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
                        # field_name = field_obj.field_name

                        if follow_with in preprocessed_data:
                            code_value = preprocessed_data[follow_with]
                            relation_data = field_obj._query_relation_data(
                                code_value=code_value,
                                hap_conn=hap_conn
                            )
                            preprocessed_data[field_obj.field_name] = relation_data

                        else:
                            # 尝试从原始数据中获取
                            api_field = follow_with
                            try:
                                # 直接从子表模型属性中查找字段
                                if hasattr(self.subtable_model, follow_with):
                                    sub_field_obj = getattr(self.subtable_model, follow_with)
                                    if isinstance(sub_field_obj, Field) and sub_field_obj.field_name:
                                        api_field = sub_field_obj.field_name
                            except (AttributeError, KeyError):
                                # 子表模型没有对应属性或字段
                                pass
                            
                            if api_field in subtable_data:
                                preprocessed_data[field_obj.field_name] = subtable_data[api_field]
                    # TODO 若子表中出现其他复杂字段，需完善相应逻辑
                preprocessed_data_list.append(preprocessed_data)
            
            # 检查子表模型是否既没有 pk 也没有 conflict fields
            subtable_has_pk_or_conflict = bool(subtable_pk_field or conflict_fields)
            
            # 如果子表模型既没有 pk 也没有 conflict fields，先删除主表当前挂载的子表记录
            if not subtable_has_pk_or_conflict:
                # 获取主记录当前挂载的子表记录 row_id
                current_row_ids = []
                if attr_name in data:
                    current_row_ids = data[attr_name]
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
            from .data_objects import HapRowSet
            row_set = HapRowSet(models=[], model=self.subtable_model, hap_conn=hap_conn)
            
            # 执行 upsert 操作
            upserted_row_set = row_set.upsert(preprocessed_data_list)
            
            # 收集处理后的子表记录 row_id
            subtable_row_ids = []
            
            # 直接从 upsert 结果中获取所有记录的 row_id
            for model_instance in upserted_row_set.row_objects:
                if hasattr(model_instance, 'row_id'):
                    subtable_row_ids.append(model_instance.row_id)

            # 将子表记录的 row_id 挂载到当前主记录
            if subtable_row_ids:
                data[attr_name] = subtable_row_ids
            else:
                # 如果没有子表记录，清空主记录的子表字段
                data[attr_name] = []
        except Exception as e:
            # 添加错误日志，以便于调试
            import traceback
            logger.error_msg("处理子表字段时出错", f"处理子表字段时出错: {e}")
            logger.error_msg("错误详情", f"错误详情:\n{traceback.format_exc()}")

        return data
    
    def _subtable_data_equal(self, new_value, original_value) -> bool:
        """
        深度比较子表数据是否相同
        
        Args:
            new_value: 新的子表数据（可能是 JSON 字符串或列表）
            original_value: 原始的子表数据（可能是 JSON 字符串或列表）
            
        Returns:
            bool: 子表数据是否相同
        """
        try:
            # 解析 JSON 字符串
            if isinstance(new_value, str):
                new_data = json.loads(new_value)
            else:
                new_data = new_value
            
            if isinstance(original_value, str):
                original_data = json.loads(original_value)
            else:
                original_data = original_value
            
            # 比较数据类型
            if type(new_data) != type(original_data):
                return False
            
            # 比较列表长度
            if isinstance(new_data, list):
                if len(new_data) != len(original_data):
                    return False
                
                # 按顺序比较每个元素
                for new_item, original_item in zip(new_data, original_data):
                    if not self._deep_equal(new_item, original_item):
                        return False
                return True
            
            # 比较字典
            elif isinstance(new_data, dict):
                return self._deep_equal(new_data, original_data)
            
            # 比较其他类型
            else:
                return new_data == original_data
        except Exception:
            # 解析失败，认为数据不同
            return False
    
    def _deep_equal(self, obj1, obj2) -> bool:
        """
        深度比较两个对象是否相等
        
        Args:
            obj1: 第一个对象
            obj2: 第二个对象
            
        Returns:
            bool: 两个对象是否相等
        """
        if type(obj1) != type(obj2):
            return False
        
        if isinstance(obj1, dict):
            if len(obj1) != len(obj2):
                return False
            for key in obj1:
                if key not in obj2:
                    return False
                if not self._deep_equal(obj1[key], obj2[key]):
                    return False
            return True
        
        elif isinstance(obj1, list):
            if len(obj1) != len(obj2):
                return False
            for item1, item2 in zip(obj1, obj2):
                if not self._deep_equal(item1, item2):
                    return False
            return True
        
        else:
            return obj1 == obj2
