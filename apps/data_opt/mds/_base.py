"""
数据清洗模块基础配置和公共工具函数
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Type, Callable
from enum import Enum

from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields


# ==============================================
# 状态枚举定义
# ==============================================

class StagingStatus(str, Enum):
    """缓冲表数据状态"""
    PENDING = ("pending", "待处理", "warning")
    COMPLIANCE_PASS = ("compliance_pass", "合规通过", "info")
    COMPLIANCE_ERROR = ("compliance_error", "合规错误", "danger")
    RELATION_PASS = ("relation_pass", "关联通过", "success")
    RELATION_ERROR = ("relation_error", "关联错误", "warning")
    APPROVED = ("approved", "已审批", "primary")
    SYNCED = ("synced", "已同步", "secondary")

    def __new__(cls, value, label, color):
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        obj.color = color
        return obj
    
    def __str__(self):
        return self._value_

    @classmethod
    def from_legacy(cls, legacy_status: str) -> 'StagingStatus':
        """从旧状态转换到新状态"""
        mapping = {
            'validated': cls.RELATION_PASS,
            'rejected': cls.RELATION_ERROR,
        }
        return mapping.get(legacy_status, cls(legacy_status))
    
    @classmethod
    def get_meta(cls, value: str) -> Optional[Dict[str, str]]:
        """根据值获取元数据"""
        for status in cls:
            if status.value == value:
                return {
                    "value": status.value,
                    "label": status.label,
                    "color": status.color
                }
        return None


class ErrorType(str, Enum):
    """错误类型枚举"""
    REQUIRED_FIELD = "required_field"    # 必填字段缺失
    INVALID_ENUM = "invalid_enum"        # 枚举值非法
    INVALID_TYPE = "invalid_type"       # 类型错误
    INVALID_RANGE = "invalid_range"      # 数值范围错误
    INVALID_LENGTH = "invalid_length"    # 字符串长度超限
    FK_NOT_FOUND = "fk_not_found"        # 外键引用不存在
    DUPLICATE_KEY = "duplicate_key"     # 主键重复
    BUSINESS_RULE = "business_rule"      # 业务规则违反


# ==============================================
# 基础模型定义
# ==============================================

class StagingBaseModel(TortoiseBaseModel):
    """缓冲表基础模型"""
    _staging_id = fields.IntField(primary_key=True, description="缓冲表主键")
    _source_system = fields.CharField(max_length=32, description="来源系统", default="unknown")
    _source_id = fields.CharField(max_length=128, null=True, description="源数据ID")
    _status = fields.CharEnumField(StagingStatus, default=StagingStatus.PENDING, description="处理状态")
    _error_msg = fields.TextField(null=True, description="错误信息JSON")
    _transform_rules = fields.TextField(null=True, description="应用的转换规则JSON")
    _retry_count = fields.IntField(default=0, description="重试次数")
    _createtime = fields.DatetimeField(auto_now_add=True, description="创建时间")
    _updatetime = fields.DatetimeField(auto_now=True, description="更新时间")
    _synced_id = fields.CharField(max_length=128, null=True, description="同步后正式表ID")
    _synced_time = fields.DatetimeField(null=True, description="同步时间")

    class Meta:
        abstract = True


# ==============================================
# 工具函数
# ==============================================

NONE_AND_EMPTY = {None, ""}


def get_field_map(model_class: Type[TortoiseBaseModel]) -> Dict[str, str]:
    """
    获取模型的字段映射：Python字段名(小写) -> 数据库字段名(大驼峰)
    
    Args:
        model_class: Tortoise ORM 模型类
        
    Returns:
        字段映射字典
    """
    field_map = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        field_map[field.model_field_name] = db_col_name
    return field_map


def extract_defaults_from_schema(schema_class) -> Dict[str, Any]:
    """
    自动提取Schema中所有有默认值的字段
    
    Args:
        schema_class: Pydantic Schema类
        
    Returns:
        字段名到默认值的映射字典
    """
    return {
        field_name: field_info.default
        for field_name, field_info in schema_class.model_fields.items()
        if field_info.default is not None 
        and str(field_info.default) != 'PydanticUndefined'
    }


def extract_required_fields(schema_class) -> List[Tuple[str, str]]:
    """
    自动提取Schema中所有必填字段（没有默认值的字段）
    
    Args:
        schema_class: Pydantic Schema类
        
    Returns:
        必填字段列表 [(field_name, description), ...]
    """
    required_fields = []
    for field_name, field_info in schema_class.model_fields.items():
        if field_name.startswith('_'):
            continue
        
        # Pydantic 正确判断：使用 is_required() 方法
        # Field(None) 表示可选字段（可以为None），不是必填
        is_required = field_info.is_required()
        
        if is_required:
            description = field_info.description or field_name
            required_fields.append((field_name, description))
    
    return required_fields


def extract_enum_fields(schema_class) -> Dict[str, Tuple[str, set]]:
    """
    从Schema自动提取所有枚举字段及其允许值

    Args:
        schema_class: Pydantic Schema类

    Returns:
        枚举字段字典 {field_name: (description, set of valid values)}
    """
    enum_fields = {}

    for field_name, field_info in schema_class.model_fields.items():
        annotation = field_info.annotation

        if field_name.startswith('_'):
            continue

        if isinstance(annotation, type) and issubclass(annotation, Enum):
            enum_values = {e.value for e in annotation}
            description = field_info.description or field_name
            enum_fields[field_name] = (description, enum_values)

    return enum_fields


def extract_range_fields(schema_class) -> Dict[str, Tuple[str, Any, Any, Any, Any]]:
    """
    从Schema自动提取所有带范围约束的字段及其范围

    Args:
        schema_class: Pydantic Schema类

    Returns:
        范围字段字典 {field_name: (description, ge, gt, le, lt)}
    """
    range_fields = {}

    for field_name, field_info in schema_class.model_fields.items():
        if field_name.startswith('_'):
            continue

        ge = getattr(field_info, 'ge', None)
        gt = getattr(field_info, 'gt', None)
        le = getattr(field_info, 'le', None)
        lt = getattr(field_info, 'lt', None)

        if ge is not None or gt is not None or le is not None or lt is not None:
            description = field_info.description or field_name
            range_fields[field_name] = (description, ge, gt, le, lt)

    return range_fields


def extract_max_length_fields(schema_class) -> Dict[str, Tuple[str, int]]:
    """
    从Schema自动提取所有带max_length约束的字段

    Args:
        schema_class: Pydantic Schema类

    Returns:
        最大长度字段字典 {field_name: (description, max_length)}
    """
    max_length_fields = {}

    for field_name, field_info in schema_class.model_fields.items():
        if field_name.startswith('_'):
            continue

        max_length = getattr(field_info, 'max_length', None)
        if max_length is not None:
            description = field_info.description or field_name
            max_length_fields[field_name] = (description, max_length)

    return max_length_fields


def extract_business_keys_from_model(model_class: Type[TortoiseBaseModel]) -> List[str]:
    """
    从正式表模型自动提取业务主键
    
    优先级：
    1. 主键字段（pk）
    2. unique_together 约束
    3. unique=True 的字段
    
    Args:
        model_class: 正式表模型类（如 TMaterial）
    
    Returns:
        业务主键字段列表
    """
    pk_field = model_class._meta.pk
    if pk_field and pk_field.model_field_name != 'id':
        return [pk_field.model_field_name]
    
    meta = getattr(model_class, '_meta', None)
    if meta:
        unique_together = getattr(meta, 'unique_together', None)
        if unique_together and len(unique_together) > 0:
            return list(unique_together[0])
    
    for field_name, field in model_class._meta.fields_map.items():
        if getattr(field, 'unique', False):
            return [field_name]
    
    return []


def extract_display_name_from_model(model_class: Type[TortoiseBaseModel]) -> str:
    """
    从模型自动提取显示名称
    
    从 table_description 中提取，去掉"数据缓冲表"或"缓冲表"后缀
    
    Args:
        model_class: 模型类（如 TMaterialStaging）
    
    Returns:
        显示名称
    """
    meta = getattr(model_class, '_meta', None)
    if meta:
        table_description = getattr(meta, 'table_description', None)
        if table_description:
            display_name = table_description
            display_name = display_name.replace("数据缓冲表", "")
            display_name = display_name.replace("缓冲表", "")
            return display_name.strip()
    
    class_name = model_class.__name__
    if class_name.startswith("T") and class_name.endswith("Staging"):
        return class_name[1:-7]
    
    return class_name





def convert_record_to_lowercase(record_dict: Dict, model_class) -> Dict:
    """
    将记录的字段名从数据库格式(大驼峰)转换为API格式(小写)
    同时过滤掉APS系统内部使用的字段
    
    Args:
        record_dict: 记录字典
        model_class: 模型类
    
    Returns:
        转换后的字典（字段名为小写，已过滤内部字段）
    """
    INTERNAL_FIELDS = {'memo', 'sys_user', 'sys_date', 'sys_stamp'}
    
    reverse_field_map = {}
    for field in model_class._meta.fields_map.values():
        db_col_name = field.source_field if field.source_field else field.model_field_name
        reverse_field_map[db_col_name] = field.model_field_name
    
    result = {}
    for key, value in record_dict.items():
        python_field = reverse_field_map.get(key, key)
        if python_field in INTERNAL_FIELDS:
            continue
        result[python_field] = value
    
    return result


def create_error_record(
    staging_id: int, 
    error_type: ErrorType, 
    field: str, 
    value: Any, 
    message: str
) -> Dict:
    """创建错误记录"""
    return {
        "staging_id": staging_id,
        "error_type": error_type.value,
        "error_field": field,
        "error_value": str(value) if value is not None else None,
        "error_message": message
    }


def get_suggestion(error_type: ErrorType) -> str:
    """根据错误类型获取修复建议"""
    suggestions = {
        ErrorType.REQUIRED_FIELD: "请补充必填字段值",
        ErrorType.INVALID_ENUM: "请填写合法的枚举值",
        ErrorType.INVALID_TYPE: "请修正字段类型",
        ErrorType.INVALID_RANGE: "请修正数值范围",
        ErrorType.INVALID_LENGTH: "请修正字符串长度",
        ErrorType.FK_NOT_FOUND: "请先导入关联的主数据，或检查引用值是否正确",
        ErrorType.DUPLICATE_KEY: "请检查是否存在重复数据",
        ErrorType.BUSINESS_RULE: "请检查业务规则约束",
    }
    return suggestions.get(error_type, "请检查数据正确性")


# ==============================================
# 表处理顺序常量
# ==============================================

TABLE_PROCESS_ORDER = [
    "t_material",
    "t_workcenter",
    "t_mold",
    "t_mat_ver",
    "t_mat_wc",
    "t_mat_wc_bom",
    "t_mat_wc_mold",
]


# ==============================================
# 内部字段常量
# ==============================================

# APS系统内部使用字段，不对外暴露
INTERNAL_FIELDS = {'memo', 'sys_user', 'sys_date', 'sys_stamp'}

# 排除的字段（插入时跳过）
EXCLUDE_FIELDS = ['_createtime', '_updatetime', 'sys_date', 'sys_stamp']


def extract_all_fields(schema_class, model_class, config: Dict = None) -> List[Dict[str, Any]]:
    """
    从Schema和Model提取完整的字段元数据
    
    Args:
        schema_class: Pydantic Schema类
        model_class: Tortoise Model类
        config: 表配置字典（用于提取外键信息）
    
    Returns:
        字段元数据列表
    """
    fields = []
    
    if not schema_class or not model_class:
        return fields
    
    # 获取字段映射
    field_map = get_field_map(model_class)
    
    # 外键信息映射（从配置中提取）
    foreign_key_map = {}
    if config:
        for fk in config.get("foreign_keys", []):
            foreign_key_map[fk.get("field")] = fk
    
    # 提取业务字段
    for field_name, field_info in schema_class.model_fields.items():
        if field_name.startswith('_'):
            continue
            
        # 判断字段类型
        annotation = field_info.annotation
        data_type = 'string'
        
        # 判断数据类型
        if isinstance(annotation, type):
            if issubclass(annotation, (int, float)):
                data_type = 'number'
            elif issubclass(annotation, Enum):
                data_type = 'enum'
            elif 'datetime' in str(annotation):
                data_type = 'datetime'
            elif 'date' in str(annotation):
                data_type = 'date'
            elif 'bool' in str(annotation):
                data_type = 'boolean'
        
        # 获取枚举选项
        enum_options = None
        if data_type == 'enum' and hasattr(annotation, 'get_options'):
            enum_options = annotation.get_options()
        
        # 判断是否必填
        is_required = field_info.is_required()
        
        # 获取范围约束
        ge = getattr(field_info, 'ge', None)
        gt = getattr(field_info, 'gt', None)
        le = getattr(field_info, 'le', None)
        lt = getattr(field_info, 'lt', None)
        
        # 获取最大长度
        max_length = getattr(field_info, 'max_length', None)
        
        # 获取描述
        description = field_info.description or field_name
        
        # 获取外键信息
        foreign_key_to = None
        if field_name in foreign_key_map:
            foreign_key_to = foreign_key_map[field_name].get("model", None).__name__ if foreign_key_map[field_name].get("model") else None
        
        # 构建字段元数据
        field_meta = {
            "field": field_name,
            "title": description,
            "description": description,
            "data_type": data_type,
            "is_required": is_required,
            "is_internal": False,
            "readOnly": False,
            "enum_options": enum_options,
            "range_constraint": {
                "ge": ge,
                "gt": gt,
                "le": le,
                "lt": lt
            },
            "max_length": max_length,
            "display_order": len(fields) + 1,
            "foreign_key_to": foreign_key_to
        }
        
        fields.append(field_meta)
    
    # 添加内部字段
    internal_fields_config = {
        '_staging_id', '_source_system', '_source_id', '_status',
        '_error_msg', '_transform_rules', '_retry_count',
        '_createtime', '_updatetime', '_synced_id', '_synced_time'
    }
    
    for field_name in internal_fields_config:
        if field_name in model_class._meta.fields_map:
            field = model_class._meta.fields_map[field_name]
            fields.append({
                "field": field_name,
                "title": field.description or field_name,
                "description": field.description or field_name,
                "data_type": 'string',
                "is_required": False,
                "is_internal": True,
                "readOnly": True,
                "enum_options": None,
                "range_constraint": None,
                "max_length": None,
                "display_order": len(fields) + 1,
                "foreign_key_to": None
            })
    
    return fields


def generate_validation_rules_doc(table_key: str, config: Dict) -> Dict[str, Any]:
    """
    生成完整的校验规则文档
    
    Args:
        table_key: 表配置键（如 "t_material"）
        config: 表配置字典（来自 STAGING_TABLE_CONFIG）
    
    Returns:
        结构化的校验规则文档
    """
    schema_class = config.get('schema')
    model_class = config.get('model')
    proto_model = config.get('proto_model')
    
    doc = {
        "table_name": extract_display_name_from_model(model_class),
        "table_key": table_key,
        "fields": [],
        
        "required_fields": [],
        "enum_fields": [],
        "range_fields": [],
        "max_length_fields": [],
        "business_rules": [],
        "foreign_keys": [],
        "business_keys": []
    }
    
    # 完整字段元数据
    if schema_class and model_class:
        doc["fields"] = extract_all_fields(schema_class, model_class, config)
    
    # 向后兼容：添加旧结构的字段（防止旧代码报错）
    if doc["fields"]:
        # 添加 range 字段（兼容旧代码）
        for field in doc["fields"]:
            if "range_constraint" in field:
                field["range"] = field["range_constraint"]
    
    # 必填字段
    if schema_class:
        required_fields = extract_required_fields(schema_class)
        doc["required_fields"] = [
            {"field": field, "description": desc}
            for field, desc in required_fields
        ]
        
        # 枚举字段
        enum_fields = extract_enum_fields(schema_class)
        doc["enum_fields"] = [
            {"field": field, "description": desc, "allowed_values": list(values)}
            for field, (desc, values) in enum_fields.items()
        ]
        
        # 范围字段
        range_fields = extract_range_fields(schema_class)
        doc["range_fields"] = [
            {"field": field, "description": desc, "ge": ge, "gt": gt, "le": le, "lt": lt}
            for field, (desc, ge, gt, le, lt) in range_fields.items()
        ]
        
        # 最大长度字段
        max_length_fields = extract_max_length_fields(schema_class)
        doc["max_length_fields"] = [
            {"field": field, "description": desc, "max_length": max_length}
            for field, (desc, max_length) in max_length_fields.items()
        ]
    
    # 外键约束
    foreign_keys = config.get('foreign_keys', [])
    doc["foreign_keys"] = [
        {"field": fk.get("field"), "description": f"引用 {fk.get('field')} 必须存在于正式表"}
        for fk in foreign_keys
    ]
    
    # 业务规则
    business_rules = config.get('business_rules', [])
    doc["business_rules"] = [
        {"name": rule.get("name", ""), "description": rule.get("description", "")}
        for rule in business_rules
    ]
    
    # 业务主键
    if proto_model:
        doc["business_keys"] = extract_business_keys_from_model(proto_model)
    
    # 状态元数据（阶段二新增）
    doc["status_meta"] = [
        {
            "value": status.value,
            "label": status.label,
            "color": status.color
        }
        for status in StagingStatus
    ]
    
    return doc


# ==============================================
# 业务规则引擎（阶段四新增）
# ==============================================

class BusinessRule:
    """
    业务规则基类
    
    用于配置化的业务规则校验，支持简单规则零代码配置。
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        validate_func: Callable[[Dict[str, Any]], bool],
        error_message: str,
        error_type: ErrorType = None
    ):
        """
        初始化业务规则
        
        Args:
            name: 规则名称
            description: 规则描述
            validate_func: 校验函数，返回 True 表示违反规则
            error_message: 错误消息
            error_type: 错误类型（默认 BUSINESS_RULE）
        """
        self.name = name
        self.description = description
        self.validate_func = validate_func
        self.error_message = error_message
        self.error_type = error_type or ErrorType.BUSINESS_RULE
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        校验数据
        
        Args:
            data: 待校验数据
        
        Returns:
            是否违反规则（True 表示违反）
        """
        try:
            return self.validate_func(data)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"业务规则执行异常: {self.name}, {e}")
            return False
    
    def create_error(self, staging_id: int) -> Dict[str, Any]:
        """创建错误记录"""
        return {
            "staging_id": staging_id,
            "error_type": self.error_type.value,
            "error_field": self.name,
            "error_value": None,
            "error_message": self.error_message
        }


def create_comparison_rule(
    field_a: str,
    field_b: str,
    comparator: str,
    error_message: str
) -> BusinessRule:
    """
    创建比较规则
    
    Args:
        field_a: 字段A
        field_b: 字段B
        comparator: 比较运算符 (">", ">=", "<", "<=", "==")
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        a = data.get(field_a)
        b = data.get(field_b)
        if a is None or b is None:
            return False
        
        if comparator == ">":
            return a > b
        if comparator == ">=":
            return a >= b
        if comparator == "<":
            return a < b
        if comparator == "<=":
            return a <= b
        if comparator == "==":
            return a == b
        return False
    
    return BusinessRule(
        name=f"{field_a}_{comparator}_{field_b}",
        description=f"{field_a} {comparator} {field_b}",
        validate_func=validate,
        error_message=error_message
    )


def create_range_rule(
    field_name: str,
    min_val: Any,
    max_val: Any,
    error_message: str
) -> BusinessRule:
    """
    创建范围规则
    
    Args:
        field_name: 字段名
        min_val: 最小值（包含）
        max_val: 最大值（包含）
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        val = data.get(field_name)
        if val is None:
            return False
        return val < min_val or val > max_val
    
    return BusinessRule(
        name=f"{field_name}_range",
        description=f"{field_name} 在 {min_val}-{max_val} 之间",
        validate_func=validate,
        error_message=error_message,
        error_type=ErrorType.INVALID_RANGE
    )


def create_positive_rule(field_name: str, error_message: str) -> BusinessRule:
    """
    创建正数规则
    
    Args:
        field_name: 字段名
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        val = data.get(field_name)
        if val is None:
            return False
        return val <= 0
    
    return BusinessRule(
        name=f"{field_name}_positive",
        description=f"{field_name} 必须大于 0",
        validate_func=validate,
        error_message=error_message,
        error_type=ErrorType.INVALID_RANGE
    )


def create_not_equal_rule(
    field_a: str,
    field_b: str,
    error_message: str
) -> BusinessRule:
    """
    创建不等规则
    
    Args:
        field_a: 字段A
        field_b: 字段B
        error_message: 错误描述
    
    Returns:
        BusinessRule 实例
    """
    def validate(data: Dict[str, Any]) -> bool:
        a = data.get(field_a)
        b = data.get(field_b)
        if a is None or b is None:
            return False
        return a == b
    
    return BusinessRule(
        name=f"{field_a}_ne_{field_b}",
        description=f"{field_a} != {field_b}",
        validate_func=validate,
        error_message=error_message
    )
