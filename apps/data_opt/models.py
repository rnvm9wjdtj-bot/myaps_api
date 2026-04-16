from enum import unique
from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields

from core.settings import THIS_DB_NAME
from apps.io_api import protomodels as pm



class Storage(TortoiseBaseModel):
    id = fields.IntField(primary_key=True, description="主键")
    namespace = fields.CharField(max_length=64, description="命名空间")
    item = fields.CharField(max_length=256, description="项")
    content = fields.TextField(description="内容")
    remark = fields.TextField(null=True, description="备注")

    class Meta:
        database = THIS_DB_NAME
        table = "a_storage"



class DataOptBaseModel(TortoiseBaseModel):
    _oid = fields.CharField(max_length=64, description="源数据主键")
    _id = fields.IntField(primary_key=True, description="主键")
    _createtime = fields.DatetimeField(auto_now_add=True, description="创建时间")
    _updatetime = fields.DatetimeField(auto_now=True, description="更新时间")
    _syncstatus = fields.IntField(default=0, description="同步状态")
    _synctime = fields.DatetimeField(null=True, description="同步时间")
    _sysprompt = fields.TextField(null=True, description="系统提示")

    class Meta:
        abstract = True


class OptMaterial(DataOptBaseModel, pm.ProtoMaterial):
    class Meta:
        database = THIS_DB_NAME
        table = "opt_material"
        # 如果不希望ORM自动创建此表，取消下面这行的注释
        # managed = False