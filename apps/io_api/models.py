from tortoise import fields
# from tortoise.signals import post_save

from globalobjects.db_manager import db_managers
from cache import ProjectDefaultValues as pdv
from . import protomodels as pm
# from apps.io_api.schemas import Values as pdv


class TMaterial(pm.ProtoMaterial):
    materialno = fields.CharField(source_field='MaterialNo', primary_key=True, max_length=64, description='物料')

    class Meta:
        managed = False
        abstract = False
        table = "t_material"

    @classmethod
    async def create(cls, using_db, update_fields=None, force_create=False, force_update=False, *args, **kwargs):
        if pdv.auto_matver and kwargs.get("type") == "E":
            await TMatVer.create_if_not_exists(db_name=using_db.connection_name, materialno=kwargs.get("materialno"))
        return await super().create(using_db=using_db, update_fields=update_fields, force_create=force_create, force_update=force_update, *args, **kwargs)



class TWorkcenter(pm.ProtoWorkcenter):
    workcenter = fields.CharField(source_field='WorkCenter', primary_key=True, max_length=32)

    class Meta:
        managed = False
        abstract = False
        table = "t_workcenter"



class TMatWc(pm.ProtoMatWc):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc"
        # unique_together = [("materialno", "matver", "itemno")]
        unique_together = pm.ProtoMatWc.Meta.unique_together



class TMatVer(pm.ProtoMatVer):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_ver"
        # unique_together = [("materialno", "matver")]
        unique_together = pm.ProtoMatVer.Meta.unique_together

    @classmethod
    async def create_if_not_exists(cls, db_name: str, materialno: str, matver: str = None, lotfrom: int = None, lotto: int = None, priority: int = None):
        """
        若不存在则创建
        """
        
        # 设置默认值
        if matver is None:
            matver = pdv.MATVER
        if lotfrom is None:
            lotfrom = pdv.MATVER_LOTFROM
        if lotto is None:
            lotto = pdv.MATVER_LOTTO
        if priority is None:
            priority = pdv.MATVER_PRIORITY
            
        db_manager = db_managers.get(db_name)
        db_manager._bulk_upsert_orm(
            model_class=cls,
            data_list=[{
                "materialno": materialno,
                "matver": matver,
                "lotfrom": lotfrom,
                "lotto": lotto,
                "priority": priority,
                "active": "Y"
            }])



class TMatWcBom(pm.ProtoMatWcBom):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc_bom"
        # unique_together = [("productno", "matver", "itemno", "materialno")]
        unique_together = pm.ProtoMatWcBom.Meta.unique_together



class TSupply(pm.ProtoSupply):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_supply"
        # unique_together = [("materialno", "supplyno")]
        unique_together = pm.ProtoSupply.Meta.unique_together



class TOrderwc(pm.ProtoOrderwc):
    orderno = fields.CharField(source_field='OrderNo', primary_key=True, max_length=64)

    class Meta:
        managed = False
        abstract = False
        table = "t_orderwc"



class TDemand(pm.ProtoDemand):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_demand"
        # unique_together = [("materialno", "demandno", "itemno")]
        unique_together = pm.ProtoDemand.Meta.unique_together



class TMold(pm.ProtoMold):
    moldno = fields.CharField(source_field='MoldNo', primary_key=True, max_length=32)

    class Meta:
        managed = False
        abstract = False
        table = "t_mold"



class TMatWcMold(pm.ProtoMatWcMold):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc_mold"
        # unique_together = [("materialno", "workcenter", "moldno", "itemno")]
        unique_together = pm.ProtoMatWcMold.Meta.unique_together



class TConfirm(pm.ProtoConfirm):
    # noid = fields.IntField(primary_key=True, auto=True, source_field='NoID')

    class Meta:
        managed = False
        abstract = False
        table = "t_confirm"



def get_table_model_mapping():
    """
    获取当前模块中所有非抽象类、有Meta属性、有table属性的类，
    并将其映射关系存储在TABLE_MODEL_MAPPING中
    """
    import inspect
    import sys
    # 获取当前模块
    current_module = sys.modules[__name__]
    table_model_mapping = {
        'v_supply_mo': None,#TSupply,
        'v_orderwc': None,
        'v_matdailyqtyreport': None,
    }
    # 遍历当前模块中的所有属性
    for name in dir(current_module):
        
        cls = getattr(current_module, name)
        # 检查是否是类、是否有Meta属性、是否有table属性、是否不是抽象类
        if (inspect.isclass(cls) and 
            hasattr(cls, "Meta") and 
            hasattr(cls.Meta, "table") and 
            not cls.Meta.abstract):
            table_model_mapping[cls.Meta.table] = cls
    return table_model_mapping

# 动态生成表与模型的映射关系
TABLE_MODEL_MAPPING = get_table_model_mapping()