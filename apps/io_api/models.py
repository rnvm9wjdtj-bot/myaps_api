from tortoise import fields

from . import protomodels as pm



class TMaterial(pm.TMaterial):
    materialno = fields.CharField(source_field='MaterialNo', primary_key=True, max_length=64, description='物料')

    class Meta:
        managed = False
        abstract = False
        table = "t_material"



class TWorkcenter(pm.TWorkcenter):
    workcenter = fields.CharField(source_field='WorkCenter', primary_key=True, max_length=32)

    class Meta:
        managed = False
        abstract = False
        table = "t_workcenter"



class TMatWc(pm.TMatWc):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc"
        unique_together = [("materialno", "matver", "itemno")]



class TMatVer(pm.TMatVer):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_ver"
        unique_together = [("materialno", "matver")]



class TMatWcBom(pm.TMatWcBom):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc_bom"
        unique_together = [("productno", "matver", "itemno", "materialno")]



class TSupply(pm.TSupply):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_supply"
        unique_together = [("materialno", "supplyno")]



class TDemand(pm.TDemand):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_demand"
        unique_together = [("materialno", "demandno", "itemno")]



class TMold(pm.TMold):
    moldno = fields.CharField(source_field='MoldNo', primary_key=True, max_length=32)

    class Meta:
        managed = False
        abstract = False
        table = "t_mold"



class TMatWcMold(pm.TMatWcMold):
    vid = fields.IntField(primary_key=True)

    class Meta:
        managed = False
        abstract = False
        table = "t_mat_wc_mold"
        unique_together = [("materialno", "workcenter", "moldno")]