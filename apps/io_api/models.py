from tortoise import fields
from tortoise.signals import post_save

from . import protomodels as pm
from config.projectconst import DefaultValue
from .common import common_write



class TMaterial(pm.ProtoMaterial):
    materialno = fields.CharField(source_field='MaterialNo', primary_key=True, max_length=64, description='物料')

    class Meta:
        managed = False
        abstract = False
        table = "t_material"

    @classmethod
    async def create(cls, using_db, update_fields=None, force_create=False, force_update=False, *args, **kwargs):
        if DefaultValue.auto_matver and kwargs.get("type") == "E":
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
        unique_together = [("materialno", "matver", "itemno")]



class TMatVer(pm.ProtoMatVer):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_ver"
        unique_together = [("materialno", "matver")]

    @classmethod
    async def create_if_not_exists(cls, db_name: str, materialno: str, matver: str = DefaultValue.MATVER, lotfrom: int = DefaultValue.MATVER_LOTFROM, lotto: int = DefaultValue.MATVER_LOTTO, priority: int = DefaultValue.MATVER_PRIORITY):
        """
        若不存在则创建
        """
        await common_write(db_name=db_name, mdl=cls, data=[{
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
        unique_together = [("productno", "matver", "itemno", "materialno")]



class TSupply(pm.ProtoSupply):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_supply"
        unique_together = [("materialno", "supplyno")]

    # async def delete(self, using_db: str):
    #     """
    #     若删除的实例为MO或PL则同步删除工序
    #     """
    #     result = await super().delete(using_db=using_db)
    #     if self.type in ["MO", "PL"]:
    #         await TOrderwc.del_by_supply(using_db, self.materialno, self.supplyno)
    #     return result


class TOrderwc(pm.ProtoOrderwc):
    orderno = fields.CharField(source_field='OrderNo', primary_key=True, max_length=64)

    class Meta:
        managed = False
        abstract = False
        table = "t_orderwc"

    # @classmethod
    # async def del_by_supply(cls, using_db: str, materialno: str, supplyno: str):
    #     """
    #     删除supply关联的工序
    #     """
    #     cls.filter(
    #         materialno=materialno,
    #         supplyno=supplyno
    #     ).delete(using_db=using_db)



class TDemand(pm.ProtoDemand):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_demand"
        unique_together = [("materialno", "demandno", "itemno")]



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
        unique_together = [("materialno", "workcenter", "moldno")]



class TConfirm(pm.ProtoConfirm):
    noid = fields.IntField(primary_key=True, source_field='NoID')

    class Meta:
        managed = False
        abstract = False
        table = "t_confirm"
