"""
数据清洗模块
包含字段校验、关联校验、数据转换等功能
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple, Type
from enum import Enum

from tortoise import Tortoise
from tortoise.models import Model

from ._base import (
    StagingStatus, ErrorType, NONE_AND_EMPTY,
    get_field_map, extract_defaults_from_schema, extract_required_fields,
    extract_enum_fields, extract_range_fields, extract_max_length_fields,
    extract_business_keys_from_model, extract_display_name_from_model,
    BusinessRule, create_comparison_rule, create_range_rule, 
    create_positive_rule, create_not_equal_rule,
)
from .staging_models import (
    ValidationError, TransformRule,
    TMaterialStaging, TWorkcenterStaging, TMatVerStaging,
    TMatWcStaging, TMatWcBomStaging, TMoldStaging, TMatWcMoldStaging,
)
from apps.io_api.models import (
    TMaterial, TWorkcenter, TMatVer, TMatWc, TMatWcBom, TMold, TMatWcMold
)
from apps.io_api.schemas import AcceptMaterial, AcceptWorkcenter, AcceptMatVer, AcceptMatWc, AcceptMatWcBom, AcceptMold, AcceptMatWcMold
from globalobjects import logger as log_config, globalconst as gc, ProjectDefaultValues as pdv

logger = log_config.get_logger(__name__)


# ==============================================
# 业务规则校验函数（保留：有特殊外键存在校验）
# ==============================================

async def validate_material_type_e_rules(cleaner, data, staging_id):
    """物料业务规则校验：自制件必须有工艺路线、BOM和产线版本"""
    if data.get("type") != gc.EfEnum.E.value:
        return []

    errors = []
    materialno = data.get("materialno")
    if materialno:
        # 校验工艺路线存在（从缓冲表查找）
        mat_wc_exists = await TMatWcStaging.filter(materialno=materialno).exists()
        if not mat_wc_exists:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.BUSINESS_RULE, 
                ["materialno", "type"],
                materialno, "自制件必须有工艺路线"
            ))
        # 校验BOM存在（从缓冲表查找）
        bom_exists = await TMatWcBomStaging.filter(productno=materialno).exists()
        if not bom_exists:
            errors.append(cleaner._create_error(
                staging_id, ErrorType.BUSINESS_RULE, 
                ["materialno", "type"],
                materialno, "自制件必须有BOM"
            ))
        # 校验产线版本存在（从缓冲表查找）
        matver_exists = await TMatVerStaging.filter(materialno=materialno).exists()
        if not matver_exists:
            if pdv.auto_matver:
                # 自动生成产线版本
                await TMatVerStaging.create(
                    materialno=materialno,
                    matver=pdv.MATVER,
                    lotfrom=pdv.MATVER_LOTFROM,
                    lotto=pdv.MATVER_LOTTO,
                    priority=pdv.MATVER_PRIORITY,
                    _source_system="SYS_AUTO",
                )
            else:
                errors.append(cleaner._create_error(
                    staging_id, ErrorType.BUSINESS_RULE, 
                    ["materialno", "type"],
                    materialno, "自制件必须有产线版本"
                ))
    return errors


# async def validate_mat_wc_rules(cleaner, data, staging_id):
#     """工艺路线业务规则校验：外键存在校验"""
#     errors = []
#     if data.get("materialno") and data.get("matver"):
#         exists = await TMatVer.filter(materialno=data["materialno"], matver=data["matver"]).exists()
#         if not exists:
#             errors.append(cleaner._create_error(
#                 staging_id, ErrorType.FK_NOT_FOUND, "matver",
#                 f"{data['materialno']}/{data['matver']}", "关联的产线版本不存在"
#             ))
#     return errors


# async def validate_mat_wc_bom_rules(cleaner, data, staging_id):
#     """物料清单业务规则校验：外键存在校验"""
#     errors = []
#     # productno/materialno 比较已用 config_rules 替代
#     if data.get("productno") and data.get("matver"):
#         exists = await TMatVer.filter(materialno=data["productno"], matver=data["matver"]).exists()
#         if not exists:
#             errors.append(cleaner._create_error(
#                 staging_id, ErrorType.FK_NOT_FOUND, "matver",
#                 f"{data['productno']}/{data['matver']}", "关联的产线版本不存在"
#             ))
#     if data.get("productno") and data.get("matver") and data.get("itemno"):
#         exists = await TMatWc.filter(
#             materialno=data["productno"], 
#             matver=data["matver"], 
#             itemno=data["itemno"]
#         ).exists()
#         if not exists:
#             errors.append(cleaner._create_error(
#                 staging_id, ErrorType.FK_NOT_FOUND, "itemno",
#                 f"{data['productno']}/{data['matver']}/{data['itemno']}", "关联的工序不存在"
#             ))
#     # qty 和 scrap 范围已用 config_rules 替代
#     return errors


# async def validate_mat_wc_mold_rules(cleaner, data, staging_id):
#     """机台模具关联业务规则校验：外键存在校验"""
#     errors = []
#     if data.get("materialno") and data.get("workcenter") and data.get("itemno"):
#         exists = await TMatWc.filter(
#             materialno=data["materialno"],
#             workcenter=data["workcenter"],
#             itemno=data["itemno"]
#         ).exists()
#         if not exists:
#             errors.append(cleaner._create_error(
#                 staging_id, ErrorType.FK_NOT_FOUND, "itemno",
#                 f"{data['materialno']}/{data['workcenter']}/{data['itemno']}", "关联的工艺路线不存在"
#             ))
#     return errors


STAGING_TABLE_CONFIG = {
    "t_material": {
        "schema": AcceptMaterial,
        "model": TMaterialStaging,
        "proto_model": TMaterial,
        "foreign_keys": [],
        "display_name": "物料",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_material(data, staging_id),
        "config_rules": [
            create_comparison_rule("lotmin", "lotmax", ">", "最小批量不能大于最大批量"),
        ],
        "business_rules": [
            {
                "name": "E类型物料校验",
                "description": "E类型物料必须存在工艺路线和BOM",
                "validator": validate_material_type_e_rules,
            }
        ],
    },

    "t_workcenter": {
        "schema": AcceptWorkcenter,
        "model": TWorkcenterStaging,
        "proto_model": TWorkcenter,
        "foreign_keys": [],
        "display_name": "工作中心",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_workcenter(data, staging_id),
    },

    "t_mat_ver": {
        "schema": AcceptMatVer,
        "model": TMatVerStaging,
        "proto_model": TMatVer,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterialStaging,
                "value_field": "materialno",
                "label_field": "description"
            },
        ],
        "display_name": "产线版本",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_ver(data, staging_id),
        "config_rules": [
            create_comparison_rule("lotfrom", "lotto", ">", "批量下限不能大于批量上限"),
        ],
    },

    "t_mat_wc": {
        "schema": AcceptMatWc,
        "model": TMatWcStaging,
        "proto_model": TMatWc,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterialStaging,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "workcenter",
                "model": TWorkcenterStaging,
                "value_field": "workcenter",
                "label_field": "workcentername"
            },
            {
                "field": "matver",
                "model": TMatVerStaging,
                "display_name": "产线版本",
                "conditions": [
                    {"local": "materialno", "foreign": "materialno"},
                    {"local": "matver", "foreign": "matver"}
                ]
            },
        ],
        "display_name": "工序",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc(data, staging_id),
        "business_rules": [
            # {
            #     "name": "复合外键校验（物料+版本）",
            #     "description": "关联的产线版本必须存在",
            #     "validator": validate_mat_wc_rules,
            # }
        ],
    },

    "t_mat_wc_bom": {
        "schema": AcceptMatWcBom,
        "model": TMatWcBomStaging,
        "proto_model": TMatWcBom,
        "foreign_keys": [
            {
                "field": "productno",
                "model": TMaterialStaging,
                "value_field": "materialno",
                "label_field": "description",
                "display_name": "父项物料"
            },
            {
                "field": "materialno",
                "model": TMaterialStaging,
                "value_field": "materialno",
                "label_field": "description",
                "display_name": "子项物料"
            },
            {
                "field": "matver",
                "model": TMatVerStaging,
                "display_name": "产线版本",
                "conditions": [
                    {"local": "productno", "foreign": "materialno"},
                    {"local": "matver", "foreign": "matver"}
                ]
            },
            {
                "field": "itemno",
                "model": TMatWcStaging,
                "display_name": "工序号",
                "conditions": [
                    {"local": "productno", "foreign": "materialno"},
                    {"local": "itemno", "foreign": "itemno"}
                ]
            },
        ],
        "display_name": "BOM",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc_bom(data, staging_id),
        "business_rules": [],
        "config_rules": [
            create_not_equal_rule("productno", "materialno", "父件和子件不能为同一物料"),
            create_positive_rule("qty", "用量必须大于0"),
            create_range_rule("scrap", 0, 100, "损耗率必须在0-100之间"),
        ],
    },

    "t_mold": {
        "schema": AcceptMold,
        "model": TMoldStaging,
        "proto_model": TMold,
        "foreign_keys": [],
        "display_name": "模具",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mold(data, staging_id),
        "config_rules": [
            create_range_rule("moldnum", 1, 9999, "模具穴数必须≥1"),
            create_range_rule("qty", 1, 9999, "模具台数必须≥1"),
        ],
    },

    "t_mat_wc_mold": {
        "schema": AcceptMatWcMold,
        "model": TMatWcMoldStaging,
        "proto_model": TMatWcMold,
        "foreign_keys": [
            {
                "field": "materialno",
                "model": TMaterialStaging,
                "value_field": "materialno",
                "label_field": "description"
            },
            {
                "field": "workcenter",
                "model": TWorkcenterStaging,
                "value_field": "workcenter",
                "label_field": "workcentername"
            },
            {
                "field": "moldno",
                "model": TMoldStaging,
                "value_field": "moldno",
                "label_field": "moldname"
            },
            {
                "field": "itemno",
                "model": TMatWcStaging,
                "display_name": "工艺路线",
                "conditions": [
                    {"local": "materialno", "foreign": "materialno"},
                    {"local": "workcenter", "foreign": "workcenter"},
                    {"local": "itemno", "foreign": "itemno"}
                ]
            },
        ],
        "display_name": "机台模具关联",
        "validator": lambda cleaner, data, staging_id: cleaner.validate_mat_wc_mold(data, staging_id),
        "business_rules": [
            # {
            #     "name": "复合外键校验（物料+工作中心+工序）",
            #     "description": "关联的工艺路线必须存在",
            #     "validator": validate_mat_wc_mold_rules,
            # }
        ],
    },
}


def initialize_table_config():
    """延迟初始化表配置（等待Tortoise连接建立后调用）"""
    for table_key, config in STAGING_TABLE_CONFIG.items():
        # 使用 db_table 而不是 table，兼容Tortoise不同状态
        meta = config["model"]._meta
        config["table_name"] = getattr(meta, 'db_table', getattr(meta, 'table', table_key + '_staging'))
        config["defaults"] = extract_defaults_from_schema(config["schema"])
        # 只有未手动配置 business_keys 时才自动提取
        if "business_keys" not in config:
            config["business_keys"] = extract_business_keys_from_model(config["proto_model"])


STAGING_MODEL_MAPPING = {
    table_key: config["model"] 
    for table_key, config in STAGING_TABLE_CONFIG.items()
}

# 标记是否已初始化
_config_initialized = False


def ensure_config_initialized():
    """确保配置已初始化"""
    global _config_initialized
    if not _config_initialized:
        initialize_table_config()
        _config_initialized = True


def get_schema_defaults(table_name: str) -> Dict[str, Any]:
    """获取指定表的默认值配置（延迟获取）"""
    ensure_config_initialized()
    return STAGING_TABLE_CONFIG.get(table_name, {}).get("defaults", {})


def fill_defaults(table_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    填充默认值：对于NULL或空字符串的字段，使用schemas.py中定义的默认值填充
    
    Args:
        table_name: 表名
        data: 原始数据字典
        
    Returns:
        填充后的数据字典
    """
    defaults = get_schema_defaults(table_name)
    
    result = data.copy()
    
    schema_class = STAGING_TABLE_CONFIG.get(table_name, {}).get("schema")
    if not schema_class:
        return data
    
    # 遍历所有字段，填充默认值
    for field_name, field_info in schema_class.model_fields.items():
        current_value = result.get(field_name)
        
        # 如果当前值是 None 或空字符串
        if current_value in NONE_AND_EMPTY:
            # 优先使用 SCHEMA_DEFAULTS 中的默认值
            if field_name in defaults and defaults[field_name] is not None:
                result[field_name] = defaults[field_name]
                logger.debug(f"填充默认值: {table_name}.{field_name} = {defaults[field_name]}")
            else:
                # 根据 Field 定义获取默认值
                field_default = field_info.default
                
                # 如果 Field 默认值不是 None 且不是 PydanticUndefined
                if field_default is not None and str(field_default) != 'PydanticUndefined':
                    result[field_name] = field_default
                    logger.debug(f"填充字段默认值: {table_name}.{field_name} = {field_default}")
                # 对于可选的字符串字段，填充空字符串
                elif field_name in ['size', 'planitem', 'memo', 'free1', 'free2', 'free3']:
                    result[field_name] = ""
                    logger.debug(f"填充空字符串: {table_name}.{field_name} = ''")
                # 对于可选的数值字段，填充 0
                elif field_name in ['lotmin', 'lotmax']:
                    result[field_name] = 0.0
                    logger.debug(f"填充零值: {table_name}.{field_name} = 0.0")
    
    return result


class DataCleaner:
    """数据清洗器"""

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.errors: List[Dict] = []
    
    def validate_required_from_schema(self, errors: List[Dict], staging_id: int, 
                                      data: Dict, schema_class) -> bool:
        """
        从Schema自动提取并校验所有必填字段
        
        Args:
            errors: 错误列表
            staging_id: 缓冲表记录ID
            data: 待校验数据
            schema_class: Pydantic Schema类
            
        Returns:
            是否所有必填字段都通过校验
        """
        required_fields = extract_required_fields(schema_class)
        
        all_valid = True
        for field_name, description in required_fields:
            # 从description中提取中文描述（去掉括号等内容）
            display_name = description.split('（')[0].split('(')[0] if description else field_name
            
            value = data.get(field_name)
            # 正确的空值判断：只有当值为 None、空字符串或不存在时才认为是空
            # 注意：0 和 0.0 是有效的数值，不应该被认为是空
            if value is None or value == "":
                errors.append(self._create_error(
                    staging_id, ErrorType.REQUIRED_FIELD,
                    field_name, None, f"{display_name}不能为空"
                ))
                all_valid = False
        
        return all_valid
    
    def validate_enums_from_schema(self, errors: List[Dict], staging_id: int,
                                   data: Dict, schema_class) -> bool:
        """
        从Schema自动提取并校验所有枚举字段

        Args:
            errors: 错误列表
            staging_id: 缓冲表记录ID
            data: 待校验数据
            schema_class: Pydantic Schema类

        Returns:
            是否所有枚举字段都通过校验
        """
        enum_fields = extract_enum_fields(schema_class)

        all_valid = True
        for field_name, (description, valid_values) in enum_fields.items():
            value = data.get(field_name)
            if value is not None and value not in valid_values:
                display_name = description.split('（')[0].split('(')[0] if description else field_name
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_ENUM,
                    field_name, value, f"{display_name}必须为: {', '.join(sorted(valid_values))}"
                ))
                all_valid = False

        return all_valid

    def validate_ranges_from_schema(self, errors: List[Dict], staging_id: int,
                                     data: Dict, schema_class) -> bool:
        """
        从Schema自动提取并校验所有范围约束字段

        Args:
            errors: 错误列表
            staging_id: 缓冲表记录ID
            data: 待校验数据
            schema_class: Pydantic Schema类

        Returns:
            是否所有范围字段都通过校验
        """
        range_fields = extract_range_fields(schema_class)

        all_valid = True
        for field_name, (description, ge, gt, le, lt) in range_fields.items():
            value = data.get(field_name)
            if value is None:
                continue

            display_name = description.split('（')[0].split('(')[0] if description else field_name

            if ge is not None and value < ge:
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_RANGE,
                    field_name, value, f"{display_name}不能小于{ge}"
                ))
                all_valid = False

            if gt is not None and value <= gt:
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_RANGE,
                    field_name, value, f"{display_name}必须大于{gt}"
                ))
                all_valid = False

            if le is not None and value > le:
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_RANGE,
                    field_name, value, f"{display_name}不能大于{le}"
                ))
                all_valid = False

            if lt is not None and value >= lt:
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_RANGE,
                    field_name, value, f"{display_name}必须小于{lt}"
                ))
                all_valid = False

        return all_valid

    def validate_max_lengths_from_schema(self, errors: List[Dict], staging_id: int, data: Dict, schema_class) -> bool:
        """
        从Schema自动提取并校验所有字符串长度约束字段

        Args:
            errors: 错误列表
            staging_id: 缓冲表记录ID
            data: 待校验数据
            schema_class: Pydantic Schema类

        Returns:
            是否所有长度字段都通过校验
        """
        max_length_fields = extract_max_length_fields(schema_class)

        all_valid = True
        for field_name, (description, max_length) in max_length_fields.items():
            value = data.get(field_name)
            if value is None:
                continue

            if isinstance(value, str) and len(value) > max_length:
                display_name = description.split('（')[0].split('(')[0] if description else field_name
                errors.append(self._create_error(
                    staging_id, ErrorType.INVALID_LENGTH,
                    field_name, len(value), f"{display_name}长度不能超过{max_length}个字符，当前长度{len(value)}"
                ))
                all_valid = False

        return all_valid

    async def validate_foreign_keys_from_config(self, errors: List[Dict], staging_id: int,
                                                data: Dict, table_key: str) -> bool:
        """
        根据配置自动校验所有外键约束

        Args:
            errors: 错误列表
            staging_id: 缓冲表记录ID
            data: 待校验数据
            table_key: 表配置键（如 "t_mat_wc"）

        Returns:
            是否所有外键校验都通过
        """
        config = STAGING_TABLE_CONFIG.get(table_key)
        if not config or not config.get("foreign_keys"):
            return True

        all_valid = True
        for fk_config in config["foreign_keys"]:
            field_name = fk_config["field"]
            model_class = fk_config["model"]
            display_name = fk_config.get("display_name") or extract_display_name_from_model(model_class)
            conditions = fk_config.get("conditions")

            if conditions:
                # ========== 多维约束校验 ==========
                # 检查所有条件字段都有值
                all_fields_present = True
                condition_values = {}
                for cond in conditions:
                    local_field = cond["local"]
                    local_value = data.get(local_field)
                    if not local_value:
                        all_fields_present = False
                        break
                    condition_values[cond["foreign"]] = local_value

                if all_fields_present:
                    # 构建查询条件
                    exists = await model_class.filter(**condition_values).exists()
                    if not exists:
                        # 构建错误信息，显示所有条件值
                        error_value_parts = [f"{data.get(cond['local'])}" for cond in conditions]
                        error_value = "/".join(error_value_parts)
                        errors.append(self._create_error(
                            staging_id, ErrorType.FK_NOT_FOUND,
                            field_name, error_value, f"关联的{display_name}不存在"
                        ))
                        all_valid = False
            else:
                # ========== 单约束校验（保持向后兼容） ==========
                value_field = fk_config.get("value_field", field_name)
                value = data.get(field_name)
                if value:
                    exists = await model_class.filter(**{value_field: value}).exists()
                    if not exists:
                        errors.append(self._create_error(
                            staging_id, ErrorType.FK_NOT_FOUND,
                            field_name, value, f"关联的{display_name}不存在"
                        ))
                        all_valid = False

        return all_valid

    async def validate_from_config(self, table_key: str, data: Dict[str, Any], staging_id: int = None) -> List[Dict]:
        """
        根据配置自动执行所有标准校验

        Args:
            table_key: 表配置键（如 "t_material"）
            data: 待校验数据
            staging_id: 缓冲表记录ID

        Returns:
            错误列表
        """
        errors = []
        config = STAGING_TABLE_CONFIG.get(table_key)
        if not config:
            return errors

        schema_class = config["schema"]

        # 1. 从Schema自动提取并校验所有必填字段
        self.validate_required_from_schema(errors, staging_id, data, schema_class)

        # 2. 从Schema自动提取并校验所有枚举字段
        self.validate_enums_from_schema(errors, staging_id, data, schema_class)

        # 3. 从Schema自动提取并校验所有范围约束字段
        self.validate_ranges_from_schema(errors, staging_id, data, schema_class)

        # 4. 从Schema自动提取并校验所有字符串长度约束字段
        self.validate_max_lengths_from_schema(errors, staging_id, data, schema_class)

        # 5. 从配置自动提取并校验所有外键约束
        await self.validate_foreign_keys_from_config(errors, staging_id, data, table_key)

        # 6. 重复检查
        is_unique, dup_errors = await self.check_duplicate(table_key, data, staging_id)
        errors.extend(dup_errors)

        # 7. 执行业务规则校验（保留：有特殊外键存在校验）
        for rule in config.get("business_rules", []):
            rule_errors = await rule["validator"](self, data, staging_id)
            errors.extend(rule_errors)

        # 8. 执行配置化规则校验
        for rule in config.get("config_rules", []):
            if rule.validate(data):
                errors.append(rule.create_error(staging_id))

        return errors

    async def check_duplicate(self, table_name: str, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """检测缓冲表中是否存在重复数据"""
        from tortoise import Tortoise
        
        config = STAGING_TABLE_CONFIG.get(table_name, {})
        pk_fields = config.get("business_keys", [])
        if not pk_fields:
            return True, []
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            return True, []
        
        conditions = {}
        field_map = get_field_map(staging_model)
        
        for pk in pk_fields:
            value = data.get(pk)
            if value is not None and value != '':
                conditions[pk] = value
        
        if not conditions:
            return True, []
        
        table_name_staging = f"{table_name}_staging"
        conn = Tortoise.get_connection(self.db_name)
        
        try:
            where_clauses = []
            params = []
            for pk, value in conditions.items():
                db_col = field_map.get(pk, pk)
                where_clauses.append(f'"{db_col}" = ${len(params) + 1}')
                params.append(value)
            
            if staging_id:
                where_clauses.append(f'"_staging_id" != ${len(params) + 1}')
                params.append(staging_id)
            
            query = f'SELECT COUNT(*) as cnt FROM "{table_name_staging}" WHERE {" AND ".join(where_clauses)}'
            result = await conn.execute_query(query, tuple(params))
            count = result[1][0]["cnt"] if result[1] else 0
            
            if count > 0:
                pk_values = "/".join([str(data.get(pk, "")) for pk in pk_fields])
                pk_fields_str = "/".join(pk_fields)
                return False, [self._create_error(
                    staging_id, ErrorType.DUPLICATE_KEY,
                    pk_fields_str, pk_values,
                    f"缓冲表中已存在相同记录（主键：{pk_values}）"
                )]
            return True, []
        except Exception as e:
            logger.error(f"检测重复失败: {str(e)}")
            return True, []

    async def validate_material(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验物料数据"""
        errors = await self.validate_from_config("t_material", data, staging_id)
        return len(errors) == 0, errors

    async def validate_workcenter(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验工作中心数据"""
        errors = await self.validate_from_config("t_workcenter", data, staging_id)
        return len(errors) == 0, errors

    async def validate_mat_ver(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验产线版本数据"""
        errors = await self.validate_from_config("t_mat_ver", data, staging_id)
        return len(errors) == 0, errors

    async def validate_mat_wc(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验工艺路线数据"""
        errors = await self.validate_from_config("t_mat_wc", data, staging_id)
        return len(errors) == 0, errors

    async def validate_mat_wc_bom(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验物料清单数据"""
        errors = await self.validate_from_config("t_mat_wc_bom", data, staging_id)
        return len(errors) == 0, errors

    async def validate_mold(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验模具数据"""
        errors = await self.validate_from_config("t_mold", data, staging_id)
        return len(errors) == 0, errors

    async def validate_mat_wc_mold(self, data: Dict[str, Any], staging_id: int = None) -> Tuple[bool, List[Dict]]:
        """校验机台模具关联数据"""
        errors = await self.validate_from_config("t_mat_wc_mold", data, staging_id)
        return len(errors) == 0, errors

    def _create_error(self, staging_id: int, error_type: ErrorType, field, 
                      value: Any, message: str) -> Dict:
        """创建错误记录
        
        Args:
            staging_id: 缓冲表记录ID
            error_type: 错误类型
            field: 错误字段名（字符串或字段列表）
            value: 错误字段值
            message: 错误描述
        """
        error = {
            "staging_id": staging_id,
            "error_type": error_type.value,
            "error_value": str(value) if value is not None else None,
            "error_message": message
        }
        # 支持单字段或多字段
        if isinstance(field, list):
            error["error_fields"] = field
            error["error_field"] = field[0] if field else None
        else:
            error["error_field"] = field
        return error

    async def save_errors(self, staging_table: str, errors: List[Dict]):
        """保存错误记录"""
        from .staging_models import ValidationError
        
        if not errors:
            return
        
        try:
            error_objs = []
            for err in errors:
                error_objs.append(ValidationError(
                    staging_table=staging_table,
                    staging_id=err.get("staging_id"),
                    error_type=err["error_type"],
                    error_field=err["error_field"],
                    error_value=err.get("error_value"),
                    error_message=err["error_message"],
                    suggestion=self._get_suggestion(err["error_type"])
                ))
            
            await ValidationError.bulk_create(error_objs)
        except Exception as e:
            import traceback
            logger.error(f"保存错误记录失败: {str(e)}")
            logger.error(traceback.format_exc())

    def _get_suggestion(self, error_type: ErrorType) -> str:
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


class DataTransformer:
    """数据转换器"""

    def __init__(self):
        self.rules_cache: Dict[str, TransformRule] = {}

    async def load_rules(self, source_system: str, target_table: str) -> Optional[TransformRule]:
        """加载转换规则"""
        cache_key = f"{source_system}_{target_table}"
        if cache_key not in self.rules_cache:
            rule = await TransformRule.filter(
                source_system=source_system,
                target_table=target_table,
                is_active=True
            ).first()
            self.rules_cache[cache_key] = rule
        return self.rules_cache.get(cache_key)

    async def transform(self, data: Dict[str, Any], source_system: str, target_table: str) -> Dict[str, Any]:
        """执行数据转换"""
        rule = await self.load_rules(source_system, target_table)
        if not rule:
            return data

        result = {}

        if rule.field_mappings:
            field_mappings = json.loads(rule.field_mappings)
            for target_field, source_field in field_mappings.items():
                if isinstance(source_field, str):
                    result[target_field] = data.get(source_field)
                elif isinstance(source_field, dict):
                    result[target_field] = self._extract_nested(data, source_field)

        if rule.default_values:
            default_values = json.loads(rule.default_values)
            for field, default_val in default_values.items():
                if result.get(field) is None:
                    result[field] = default_val

        if rule.value_mappings:
            value_mappings = json.loads(rule.value_mappings)
            for field, mapping in value_mappings.items():
                if result.get(field) in mapping:
                    result[field] = mapping[result[field]]

        return result

    def _extract_nested(self, data: Dict, mapping: Dict) -> Any:
        """提取嵌套字段值"""
        path = mapping.get("path", "")
        default = mapping.get("default")
        
        value = data
        for key in path.split("."):
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return default
        
        return value if value is not None else default


class StagingProcessor:
    """缓冲表处理器"""

    # 校验器和目标模型已整合到 STAGING_TABLE_CONFIG 中，这里保留空字典作为兼容层
    VALIDATORS = {}
    TARGET_MODELS = {}

    def __init__(self, db_name: str):
        self.db_name = db_name
        self.cleaner = DataCleaner(db_name)
        self.transformer = DataTransformer()

    async def process_staging(self, table_name: str, batch_size: int = 100, use_transaction: bool = True, max_batches: int = 100) -> Dict[str, int]:
        """处理缓冲表数据（校验前先填充默认值，循环处理直到没有pending记录）
        
        Args:
            table_name: 表名
            batch_size: 每批处理数量
            use_transaction: 是否使用事务
            max_batches: 最大批次数（防止无限循环）
        """
        from tortoise import Tortoise
        
        staging_model = STAGING_MODEL_MAPPING.get(table_name)
        if not staging_model:
            raise ValueError(f"未知的缓冲表: {table_name}")

        stats = {
            "relation_pass": 0, 
            "relation_error": 0, 
            "compliance_error": 0, 
            "synced": 0, 
            "filled": 0
        }
        
        conn = Tortoise.get_connection(self.db_name)
        table_name_staging = f"{table_name}_staging"
        
        field_map = get_field_map(staging_model)
        
        batch_count = 0
        while batch_count < max_batches:
            try:
                query = f'SELECT * FROM "{table_name_staging}" WHERE "_status" = $1 LIMIT $2'
                result = await conn.execute_query(query, ("pending", batch_size))
                pending_records = result[1] if result[1] else []
            except Exception as e:
                logger.error(f"查询pending记录失败: {str(e)}")
                break
            
            if not pending_records:
                break
            
            batch_count += 1
            logger.info(f"处理第{batch_count}批，共{len(pending_records)}条记录")
            
            # 清空这批记录的旧错误信息（防止旧错误影响新校验结果）
            staging_ids = [record["_staging_id"] for record in pending_records]
            placeholders = ", ".join(["$" + str(i + 1) for i in range(len(staging_ids))])
            clear_error_query = f'UPDATE "{table_name_staging}" SET "_error_msg" = NULL WHERE "_staging_id" IN ({placeholders})'
            await conn.execute_query(clear_error_query, tuple(staging_ids))
            logger.debug(f"已清空{len(staging_ids)}条记录的旧错误信息")
            
            for raw_record in pending_records:
                record_dict = dict(raw_record)
                staging_id = record_dict["_staging_id"]
                
                try:
                    data = {}
                    for python_field, db_field in field_map.items():
                        if python_field.startswith('_'):
                            continue
                        value = record_dict.get(db_field)
                        data[python_field] = value
                    
                    logger.info(f"[校验] staging_id={staging_id}, 开始校验")
                    
                    filled_data = fill_defaults(table_name, data)
                    
                    is_valid, errors = await self._validate(table_name, staging_id, filled_data)
                    
                    logger.info(f"[校验] staging_id={staging_id}, 结果: is_valid={is_valid}, errors={len(errors)}")
                    
                    # 检查是否有填充的字段（与原始数据不同）
                    filled_fields = []
                    for key, filled_value in filled_data.items():
                        original_value = data.get(key)
                        if original_value in NONE_AND_EMPTY and filled_value not in NONE_AND_EMPTY:
                            filled_fields.append(key)
                    
                    if is_valid:
                        # 构建更新语句：更新状态和填充后的字段
                        if filled_fields:
                            set_clauses = ['"_status" = $1']
                            update_values = ["relation_pass"]
                            for i, field_name in enumerate(filled_fields):
                                db_field = field_map.get(field_name, field_name)
                                set_clauses.append(f'"{db_field}" = ${i + 2}')
                                update_values.append(filled_data[field_name])
                            set_clauses_str = ", ".join(set_clauses)
                            update_query = f'UPDATE "{table_name_staging}" SET {set_clauses_str} WHERE "_staging_id" = ${len(update_values) + 1}'
                            update_values.append(staging_id)
                            await conn.execute_query(update_query, tuple(update_values))
                            logger.debug(f"已更新填充字段: {filled_fields}")
                            stats["filled"] = stats.get("filled", 0) + 1
                        else:
                            update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1 WHERE "_staging_id" = $2'
                            await conn.execute_query(update_query, ("relation_pass", staging_id))
                        stats["relation_pass"] += 1
                    else:
                        error_json = json.dumps(errors, ensure_ascii=False)
                        
                        # 区分错误类型：检查是否包含外键关联错误
                        has_fk_error = any(error.get("error_type") == "fk_not_found" for error in errors)
                        if has_fk_error:
                            status = "relation_error"
                            stats["relation_error"] += 1
                        else:
                            # 其他错误都是合规错误
                            status = "compliance_error"
                            stats["compliance_error"] = (stats.get("compliance_error") or 0) + 1
                        
                        # 更新状态、错误信息，以及填充的字段
                        if filled_fields:
                            set_clauses = ['"_status" = $1', '"_error_msg" = $2']
                            update_values = [status, error_json]
                            for i, field_name in enumerate(filled_fields):
                                db_field = field_map.get(field_name, field_name)
                                set_clauses.append(f'"{db_field}" = ${i + 3}')
                                update_values.append(filled_data[field_name])
                            set_clauses_str = ", ".join(set_clauses)
                            update_query = f'UPDATE "{table_name_staging}" SET {set_clauses_str} WHERE "_staging_id" = ${len(update_values) + 1}'
                            update_values.append(staging_id)
                            await conn.execute_query(update_query, tuple(update_values))
                            logger.debug(f"校验失败但已更新填充字段: {filled_fields}")
                        else:
                            update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                            await conn.execute_query(update_query, (status, error_json, staging_id))
                        await self.cleaner.save_errors(table_name, errors)
                        
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    logger.error(f"处理记录失败 [{table_name}] _staging_id={staging_id}:")
                    logger.error(error_trace)
                    error_json = json.dumps([{
                        "staging_id": staging_id,
                        "error_type": "process_error",
                        "error_field": None,
                        "error_value": None,
                        "error_message": f"处理异常: {str(e)}\n\n堆栈:\n{error_trace[:500]}"
                    }], ensure_ascii=False)
                    try:
                        # 处理异常属于合规错误
                        update_query = f'UPDATE "{table_name_staging}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                        await conn.execute_query(update_query, ("compliance_error", error_json, staging_id))
                        stats["compliance_error"] = (stats.get("compliance_error") or 0) + 1
                    except Exception as e2:
                        logger.error(f"更新错误状态失败: {str(e2)}")

        logger.info(f"校验完成: relation_pass={stats['relation_pass']}, relation_error={stats.get('relation_error', 0)}, compliance_error={stats.get('compliance_error', 0)}, batches={batch_count}")
        return stats

    async def sync_to_production(
        self, table_name: str, batch_size: int = 100, 
        max_retries: int = 3, use_transaction: bool = True,
        mode: str = "incremental", target_db: str = None,
        update_status: bool = True, skip_truncate: bool = False) -> Dict[str, int]:
        """同步到正式表（复用自有API的db_bupsert）
        
        Args:
            table_name: 表名
            batch_size: 每批同步数量
            max_retries: 最大重试次数
            use_transaction: 是否使用事务
            mode: 同步模式
                - incremental: 仅同步校验通过的记录
                - refresh: 清空正式表后同步全部记录
            target_db: 目标账套名，为空则使用 MYAPS_MAIN_DB
            update_status: 是否更新缓冲表状态为synced（刷新模式多账套时可能需要设为False）
            skip_truncate: 刷新模式分批调用时，后续批次跳过 TRUNCATE
        """
        from tortoise import Tortoise
        from core.settings import THIS_DB_NAME, MYAPS_MAIN_DB
        from apps.io_api.utils.db_operation import db_bupsert

        
        # 从统一配置中获取模型（避免重复定义）
        config = STAGING_TABLE_CONFIG.get(table_name)
        if not config:
            raise ValueError(f"未知的表: {table_name}")
        
        staging_model = config.get("model")
        target_model = config.get("proto_model")
        
        if not staging_model or not target_model:
            raise ValueError(f"表配置不完整: {table_name}")
        
        target_db_name = target_db if target_db else MYAPS_MAIN_DB
        stats = {"synced": 0, "failed": 0, "skipped": 0, "target_db": target_db_name, "synced_staging_ids": []}

        pg_conn = Tortoise.get_connection(THIS_DB_NAME)
        staging_table_name = staging_model._meta.db_table
        target_table_name = target_model._meta.db_table
        
        if mode == "refresh" and not skip_truncate:
            mysql_conn = Tortoise.get_connection(target_db_name)
            truncate_query = f'TRUNCATE TABLE `{target_table_name}`'
            await mysql_conn.execute_query(truncate_query)
            logger.info(f"已清空正式表: {target_table_name} (账套: {target_db_name})")
        
        # 统一使用 batch_size 分批查询
        # 允许 relation_pass 和 sync_error 状态的数据进行同步
        query = f'SELECT * FROM "{staging_table_name}" WHERE "_status" IN ($1, $2) AND ("_retry_count" IS NULL OR "_retry_count" < $3) LIMIT $4'
        result = await pg_conn.execute_query(query, ("relation_pass", "sync_error", max_retries, batch_size))
        records_to_sync = result[1] if result[1] else []
        
        # 检查各状态数量分布
        status_check = await pg_conn.execute_query(
            f'SELECT "_status", COUNT(*) as cnt FROM "{staging_table_name}" WHERE "_status" IN ($1, $2) GROUP BY "_status"',
            ("relation_pass", "sync_error")
        )
        status_dist = {row["_status"]: row["cnt"] for row in status_check[1]} if status_check[1] else {}
        
        logger.info(f"同步查询: 表={staging_table_name}, 状态=relation_pass/sync_error, 重试<{max_retries}, 批次={batch_size}, 找到{len(records_to_sync)}条记录, 状态分布={status_dist}")
        
        if not records_to_sync:
            return stats

        # 从统一配置中获取Schema（避免重复定义）
        config = STAGING_TABLE_CONFIG.get(table_name)
        if not config:
            stats["skipped"] = len(records_to_sync)
            return stats
        
        schema_class = config.get("schema")
        if not schema_class:
            stats["skipped"] = len(records_to_sync)
            return stats

        staging_field_map = get_field_map(staging_model)

        data_list = []
        staging_ids = []
        
        # 记录每条数据的冲突键，用于追踪去重
        from apps.io_api.utils.db_operation import DbManager
        model_key = DbManager._get_conflict_fields(target_model)
        conflict_key_to_staging_ids = {}  # 冲突键 -> staging_id 列表
        
        for raw_record in records_to_sync:
            record_dict = dict(raw_record)
            staging_id = record_dict.get("_staging_id")
            
            data = {}
            for python_field, db_field in staging_field_map.items():
                if python_field.startswith('_'):
                    continue
                value = record_dict.get(db_field)
                data[python_field] = value
            
            # 填充默认值（关键步骤）
            data = fill_defaults(table_name, data)
            
            # 计算冲突键
            conflict_key = tuple(data.get(field) for field in model_key) if model_key else None
            if conflict_key:
                if conflict_key not in conflict_key_to_staging_ids:
                    conflict_key_to_staging_ids[conflict_key] = []
                conflict_key_to_staging_ids[conflict_key].append(staging_id)
            
            try:
                schema_obj = schema_class(**data)
                data_list.append(schema_obj)
                staging_ids.append(staging_id)
            except Exception as e:
                logger.error(f"Schema转换失败 [{table_name}] _staging_id={staging_id}: {str(e)}")
                retry_count = (record_dict.get("_retry_count") or 0) + 1
                error_json = json.dumps([{
                    "staging_id": staging_id,
                    "error_type": "schema_error",
                    "error_field": None,
                    "error_value": None,
                    "error_message": f"Schema转换失败: {str(e)}"
                }], ensure_ascii=False)
                
                try:
                    update_query = f'UPDATE "{staging_table_name}" SET "_retry_count" = $1, "_error_msg" = $2, "_status" = $3 WHERE "_staging_id" = $4'
                    await pg_conn.execute_query(update_query, (retry_count, error_json, "sync_error", staging_id))
                except Exception as update_err:
                    logger.error(f"更新失败记录状态时出错: {update_err}")
                
                stats["failed"] = (stats.get("failed") or 0) + 1
        
        # 检查是否有重复的冲突键
        duplicate_keys = {k: v for k, v in conflict_key_to_staging_ids.items() if len(v) > 1}
        if duplicate_keys:
            logger.warning(f"发现重复的冲突键 [{table_name}]: {len(duplicate_keys)}个")
            for conflict_key, ids in duplicate_keys.items():
                logger.warning(f"  冲突键={conflict_key}, staging_ids={ids}")

        if not data_list:
            logger.warning(f"同步跳过 [{table_name}]: data_list为空，无有效数据可同步")
            return stats

        logger.info(f"准备同步 [{table_name}] 账套={target_db_name}: {len(data_list)}条数据, staging_ids={staging_ids[:5]}...")

        try:
            result = await db_bupsert(
                db_names=target_db_name,
                model_or_tablename=table_name,
                data_list=data_list,
                use_orm_or_sql="sql"
            )
            
            logger.info(f"db_bupsert结果 [{table_name}]: success={result.success}, message={result.message}, meta={result.meta}")
            
            synced_count = result.affected_rows or 0
            created_count = result.meta.get('created_rows', 0) or 0
            updated_count = result.meta.get('updated_rows', 0) or 0
            distinct_total = result.meta.get('distinct_total', 0) or 0
            
            stats["synced"] = synced_count
            stats["created"] = created_count
            stats["updated"] = updated_count
            
            logger.info(f"同步统计 [{table_name}]: affected={synced_count}, created={created_count}, updated={updated_count}, distinct={distinct_total}, staging_ids={len(staging_ids)}")
            
            # 计算实际成功同步的 staging_ids
            synced_staging_ids = []
            dedup_staging_ids = []
            
            if distinct_total < len(staging_ids):
                # 存在去重
                for conflict_key, ids in conflict_key_to_staging_ids.items():
                    if len(ids) > 1:
                        dedup_staging_ids.extend(ids[:-1])
                
                if dedup_staging_ids:
                    logger.error(f"数据去重 [{table_name}]: 输入{len(staging_ids)}条, 去重后{distinct_total}条, 丢弃{len(dedup_staging_ids)}条, staging_ids={dedup_staging_ids}")
                
                synced_staging_ids = [sid for sid in staging_ids if sid not in dedup_staging_ids]
            else:
                # 无去重
                synced_staging_ids = list(staging_ids)
            
            stats["synced_staging_ids"] = synced_staging_ids
            stats["dedup_staging_ids"] = dedup_staging_ids
            
            if update_status:
                synced_time = datetime.now(timezone.utc)
                
                # 标记去重失败的记录
                if dedup_staging_ids:
                    for staging_id in dedup_staging_ids:
                        error_json = json.dumps([{
                            "staging_id": staging_id,
                            "error_type": "duplicate_key",
                            "error_field": None,
                            "error_value": None,
                            "error_message": f"数据重复：存在相同主键的记录，被去重丢弃"
                        }], ensure_ascii=False)
                        update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_error_msg" = $2 WHERE "_staging_id" = $3'
                        await pg_conn.execute_query(update_query, ("sync_error", error_json, staging_id))
                
                # 标记成功同步的记录
                if synced_staging_ids:
                    for staging_id in synced_staging_ids:
                        update_query = f'UPDATE "{staging_table_name}" SET "_status" = $1, "_synced_time" = $2 WHERE "_staging_id" = $3'
                        await pg_conn.execute_query(update_query, ("synced", synced_time, staging_id))
                    
                    logger.info(f"已标记同步成功 [{table_name}]: {len(synced_staging_ids)}条")
            
            if result.has_errors:
                logger.warning(f"同步部分失败 [{table_name}] 账套={target_db_name}: {result.message}")
                stats["failed"] += len(data_list) - (synced_count or 0)
            
        except Exception as e:
            import traceback
            logger.error(f"推送失败 [{table_name}] 账套={target_db_name}: {str(e)}")
            logger.error(traceback.format_exc())
            stats["failed"] = len(data_list)
            for staging_id in staging_ids:
                retry_count = 1
                error_json = json.dumps([{
                    "staging_id": staging_id,
                    "error_type": "sync_error",
                    "error_field": None,
                    "error_value": None,
                    "error_message": f"推送失败: {str(e)}"
                }], ensure_ascii=False)
                update_query = f'UPDATE "{staging_table_name}" SET "_retry_count" = $1, "_error_msg" = $2, "_status" = $3 WHERE "_staging_id" = $4'
                await pg_conn.execute_query(update_query, (retry_count, error_json, "sync_error", staging_id))

        return stats

    async def _validate(self, table_name: str, staging_id: int, data: Dict) -> Tuple[bool, List[Dict]]:
        """执行校验"""
        # 从统一配置中获取校验器
        config = STAGING_TABLE_CONFIG.get(table_name)
        if config:
            validator = config.get("validator")
            if validator:
                return await validator(self.cleaner, data, staging_id)
        return True, []

    def _record_to_dict(self, record: Model, exclude_staging_fields: bool = False) -> Dict[str, Any]:
        """将模型记录转换为字典"""
        data = {}
        for field_name in record._meta.fields_map:
            if exclude_staging_fields and field_name.startswith("_"):
                continue
            data[field_name] = getattr(record, field_name)
        return data
