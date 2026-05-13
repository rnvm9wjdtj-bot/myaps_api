from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum

from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields

from core.settings import THIS_DB_NAME
from apps.io_api import protomodels as pm


class StagingStatus(str, Enum):
    """缓冲表数据状态"""
    PENDING = "pending"        # 待处理
    VALIDATED = "validated"    # 校验通过
    APPROVED = "approved"      # 已审批
    REJECTED = "rejected"      # 校验失败/拒绝
    SYNCED = "synced"          # 已同步到正式表


class StagingBaseModel(TortoiseBaseModel):
    """缓冲表基础模型"""
    _staging_id = fields.IntField(primary_key=True, description="缓冲表主键")
    _source_system = fields.CharField(max_length=32, description="来源系统", default="unknown")
    _source_id = fields.CharField(max_length=128, null=True, description="源数据ID")
    _status = fields.CharEnumField(StagingStatus, default=StagingStatus.PENDING, description="处理状态")
    _error_msg = fields.TextField(null=True, description="错误信息JSON")
    _transform_rules = fields.TextField(null=True, description="应用的转换规则JSON")
    _retry_count = fields.IntField(default=0, description="重试次数")
    _createtime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="创建时间")
    _updatetime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="更新时间")
    _synced_id = fields.CharField(max_length=128, null=True, description="同步后正式表ID")
    _synced_time = fields.DatetimeField(null=True, description="同步时间")

    class Meta:
        abstract = True


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
    createtime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="创建时间")

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
    createtime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="创建时间")
    updatetime = fields.DatetimeField(default=lambda: datetime.now(timezone.utc), description="更新时间")

    class Meta:
        table = "t_transform_rule"


STAGING_MODEL_MAPPING = {
    "t_material": TMaterialStaging,
    "t_workcenter": TWorkcenterStaging,
    "t_mat_ver": TMatVerStaging,
    "t_mat_wc": TMatWcStaging,
    "t_mat_wc_bom": TMatWcBomStaging,
    "t_mold": TMoldStaging,
    "t_mat_wc_mold": TMatWcMoldStaging,
}
