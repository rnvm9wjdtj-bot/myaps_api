from datetime import datetime
from typing import Optional, Dict, Any

from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields

from core.settings import THIS_DB_NAME, TIMEZONE_NAME
from apps.io_api import protomodels as pm
from ._base import StagingStatus, StagingBaseModel


class TMaterialStaging(StagingBaseModel, pm.ProtoMaterial):
    """物料缓冲表"""
    class Meta:
        table = "t_material_staging"
        table_description = "物料数据缓冲表"


class TWorkcenterStaging(StagingBaseModel, pm.ProtoWorkcenter):
    """工作中心缓冲表"""
    class Meta:
        table = "t_workcenter_staging"
        table_description = "工作中心数据缓冲表"


class TMatVerStaging(StagingBaseModel, pm.ProtoMatVer):
    """产线版本缓冲表"""
    class Meta:
        table = "t_mat_ver_staging"
        table_description = "产线版本数据缓冲表"


class TMatWcStaging(StagingBaseModel, pm.ProtoMatWc):
    """工艺路线缓冲表"""
    class Meta:
        table = "t_mat_wc_staging"
        table_description = "工艺路线数据缓冲表"


class TMatWcBomStaging(StagingBaseModel, pm.ProtoMatWcBom):
    """物料清单缓冲表"""
    class Meta:
        table = "t_mat_wc_bom_staging"
        table_description = "物料清单数据缓冲表"


class TMoldStaging(StagingBaseModel, pm.ProtoMold):
    """模具缓冲表"""
    class Meta:
        table = "t_mold_staging"
        table_description = "模具数据缓冲表"


class TMatWcMoldStaging(StagingBaseModel, pm.ProtoMatWcMold):
    """机台模具关联缓冲表"""
    class Meta:
        table = "t_mat_wc_mold_staging"
        table_description = "机台模具关联数据缓冲表"


class ValidationError(TortoiseBaseModel):
    """校验错误记录表"""
    id = fields.IntField(primary_key=True)
    staging_table = fields.CharField(max_length=64, description="缓冲表名")
    staging_id = fields.IntField(description="缓冲表记录ID")
    error_type = fields.CharField(max_length=32, description="错误类型")
    error_field = fields.CharField(max_length=64, description="错误字段")
    error_value = fields.TextField(null=True, description="错误值")
    error_message = fields.TextField(description="错误描述")
    suggestion = fields.TextField(null=True, description="修复建议")
    createtime = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:
        table = "t_validation_error"
        indexes = [("staging_table", "staging_id")]


class TransformRule(TortoiseBaseModel):
    """数据转换规则配置表"""
    id = fields.IntField(primary_key=True)
    rule_name = fields.CharField(max_length=64, unique=True, description="规则名称")
    source_system = fields.CharField(max_length=32, description="来源系统")
    target_table = fields.CharField(max_length=64, description="目标表")
    field_mappings = fields.TextField(description="字段映射JSON")
    default_values = fields.TextField(null=True, description="默认值JSON")
    value_mappings = fields.TextField(null=True, description="枚举值映射JSON")
    validation_rules = fields.TextField(null=True, description="校验规则JSON")
    is_active = fields.BooleanField(default=True, description="是否启用")
    priority = fields.IntField(default=0, description="优先级")
    description = fields.TextField(null=True, description="规则描述")
    createtime = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updatetime = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "t_transform_rule"
