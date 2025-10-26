from tortoise import fields

from . import protomodels as pm



class TMaterial(pm.ProtoMaterial):
    materialno = fields.CharField(source_field='MaterialNo', primary_key=True, max_length=64, description='物料')

    class Meta:
        managed = False
        abstract = False
        table = "t_material"



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