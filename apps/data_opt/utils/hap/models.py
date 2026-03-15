"""
模型基类
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Type
from tortoise.models import Model as TortoiseBaseModel

# from ._base import ModelType
from .fields import Field, StrField, NumField
from .utils import (
    HapUtils, AdaptiveTimeout, EnhancedRetryStrategy, TokenBucket, DecimalEncoder, HapApiMonitor,
    StringInternPool, LightweightRow, ObjectPool, ConnectionPoolWarmer, SmartBatchSizeCalculator,
    AdaptiveRateController, hap_async_timer
)


class Model:
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


    @classmethod
    def create_from_tortoise(cls, tortoise_model: TortoiseBaseModel, model_name: str) -> Type['Model']:
        """根据 Tortoise 模型生成 HAP 模型
        
        Args:
            tortoise_model: Tortoise ORM 模型类
            model_name: HAP 模型名称
            
        Returns:
            Type[Model]: 创建的 HAP 模型类
        """
        from tortoise.fields import (
            CharField, IntField, FloatField, DecimalField,
            DateField, DatetimeField, TimeField, BooleanField,
            TextField, UUIDField, JSONField
        )
        
        fields_dict = {}
        pk_field_name = None
        
        for field_name, tortoise_field in tortoise_model._meta.fields_map.items():
            source_field = getattr(tortoise_field, 'source_field', None) or field_name
            description = getattr(tortoise_field, 'description', None)
            is_pk = getattr(tortoise_field, 'pk', False)
            
            if is_pk:
                pk_field_name = field_name
            
            if isinstance(tortoise_field, (CharField, TextField, UUIDField)):
                hap_field = StrField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            elif isinstance(tortoise_field, (IntField, FloatField, DecimalField)):
                hap_field = NumField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            elif isinstance(tortoise_field, (DateField, DatetimeField, TimeField)):
                hap_field = StrField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            elif isinstance(tortoise_field, BooleanField):
                hap_field = StrField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            elif isinstance(tortoise_field, JSONField):
                hap_field = StrField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            else:
                hap_field = StrField(
                    field_name=source_field,
                    description=description,
                    pk=is_pk
                )
            
            fields_dict[field_name] = hap_field
        
        meta_attrs = {
            'worksheet_id': '',
            'conflict_fields': None,
            'cache': None
        }
        
        if pk_field_name:
            meta_attrs['conflict_fields'] = [pk_field_name]
        
        Meta = type('Meta', (), meta_attrs)
        
        model_attrs = {
            'Meta': Meta,
            '__module__': cls.__module__,
        }
        model_attrs.update(fields_dict)
        
        hap_model = type(model_name, (Model,), model_attrs)
        
        return hap_model
