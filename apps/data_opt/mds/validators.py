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

