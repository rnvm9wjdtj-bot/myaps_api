from enum import unique
from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields

from config.settings import THIS_DB_NAME
from apps.io_api import protomodels as pm


class DataOptBaseModel(TortoiseBaseModel):
    oid = fields.IntField(description="源数据主键")
    id = fields.IntField(primary_key=True, autoincrement=True, description="主键")

    class Meta:
        abstract = True



class TMaterial(pm.TMaterial, DataOptBaseModel):
    
    class Meta:
        database = THIS_DB_NAME
        table = "opt_material"