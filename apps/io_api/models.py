from tortoise import fields
from tortoise.signals import post_save

from . import protomodels as pm
from config import uservar as uv
from .common import common_write



class TMaterial(pm.ProtoMaterial):
    materialno = fields.CharField(source_field='MaterialNo', primary_key=True, max_length=64, description='物料')

    class Meta:
        managed = False
        abstract = False
        table = "t_material"

    async def save(self, using_db, update_fields=None, force_create=False, force_update=False):
        if uv.auto_matver and self.type == "E":
            await TMatVer.create_if_not_exists(db_name=using_db.connection_name, materialno=self.materialno)
        return await super().save(using_db=using_db, update_fields=update_fields, force_create=force_create, force_update=force_update)

    # @post_save
    # @classmethod
    # async def post_save_handler(cls, sender, instance, using_db, update_fields) -> None:
    #     # 只处理TMaterial类型的保存事件
    #     if sender == TMaterial and instance.type == "E" and uv.auto_matver:
    #         await TMatVer.create_if_not_exists(db_name=using_db.connection_name, materialno=instance.materialno)



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
    async def create_if_not_exists(cls, db_name: str, materialno: str, matver: str = uv.example_matver, lotfrom: int = uv.default_lot_from, lotto: int = uv.default_lotto, priority: int = uv.default_priority):
        """
        若不存在则创建
        """
        await common_write(db_name=db_name, mdl=TMatVer, data=[{
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
