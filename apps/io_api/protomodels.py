# from enum import unique
from tortoise.models import Model as TortoiseBaseModel
from tortoise import fields


class TCalendar(TortoiseBaseModel):
    shiftdate = fields.DateField(source_field='ShiftDate', unique=True)  # Field name made lowercase.
    shiftno = fields.CharField(source_field='ShiftNo', max_length=4)  # Field name made lowercase.
    caprate = fields.FloatField(source_field='CapRate', description='机台利用率%')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_calendar'
        # abstract = True  # 设置为抽象模型，不直接关联特定数据库


class TCapReport(TortoiseBaseModel):
    id = fields.CharField(unique=True, max_length=64)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=255, blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    pointdate = fields.DateField(source_field='pointDate', blank=True, null=True)  # Field name made lowercase.
    setupsecsum = fields.CharField(source_field='SetupSecSum', max_length=64, blank=True, null=True)  # Field name made lowercase.
    setupqty = fields.IntField(source_field='SetupQty', blank=True, null=True)  # Field name made lowercase.
    processtimesum = fields.CharField(source_field='ProcessTimeSum', max_length=64, blank=True, null=True)  # Field name made lowercase.
    processqty = fields.IntField(source_field='ProcessQty', blank=True, null=True)  # Field name made lowercase.
    totalqty = fields.IntField(source_field='totalQty', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_cap_report'


class TCapacityday(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=255, blank=True, null=True)  # Field name made lowercase.
    weekno = fields.CharField(source_field='WeekNo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    startdate = fields.DateField(source_field='StartDate', blank=True, null=True)  # Field name made lowercase.
    starttime = fields.CharField(source_field='StartTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    enddate = fields.DateField(source_field='EndDate', blank=True, null=True)  # Field name made lowercase.
    endtime = fields.CharField(source_field='EndTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capacity = fields.CharField(source_field='Capacity', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free = fields.CharField(source_field='Free', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setup_sum = fields.CharField(source_field='Setup_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    process_sum = fields.CharField(source_field='Process_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capatotal = fields.CharField(source_field='CapaTotal', max_length=255, blank=True, null=True)  # Field name made lowercase.
    rate = fields.CharField(source_field='Rate', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost', blank=True, null=True)  # Field name made lowercase.
    worker = fields.CharField(source_field='Worker', max_length=255, blank=True, null=True)  # Field name made lowercase.
    shiftno = fields.CharField(source_field='ShiftNo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_capacityday'


class TCapacitymonth(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=255, blank=True, null=True)  # Field name made lowercase.
    workcentername = fields.CharField(source_field='WorkCenterName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    weekno = fields.CharField(source_field='WeekNo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    startdate = fields.DateField(source_field='StartDate', blank=True, null=True)  # Field name made lowercase.
    starttime = fields.CharField(source_field='StartTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    enddate = fields.DatetimeField(source_field='EndDate', blank=True, null=True)  # Field name made lowercase.
    endtime = fields.CharField(source_field='EndTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capacity = fields.CharField(source_field='Capacity', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free = fields.CharField(source_field='Free', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setup_sum = fields.CharField(source_field='Setup_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    process_sum = fields.CharField(source_field='Process_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capatotal = fields.CharField(source_field='CapaTotal', max_length=255, blank=True, null=True)  # Field name made lowercase.
    rate = fields.CharField(source_field='Rate', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost', blank=True, null=True)  # Field name made lowercase.
    worker = fields.CharField(source_field='Worker', max_length=255, blank=True, null=True)  # Field name made lowercase.
    
    class Meta:
        abstract = True
        table = 't_capacitymonth'


class TCapacityweek(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=255, blank=True, null=True)  # Field name made lowercase.
    workcentername = fields.CharField(source_field='WorkCenterName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    weekno = fields.CharField(source_field='WeekNo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    startdate = fields.DateField(source_field='StartDate', blank=True, null=True)  # Field name made lowercase.
    starttime = fields.CharField(source_field='StartTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    enddate = fields.DatetimeField(source_field='EndDate', blank=True, null=True)  # Field name made lowercase.
    endtime = fields.CharField(source_field='EndTime', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capacity = fields.CharField(source_field='Capacity', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free = fields.CharField(source_field='Free', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setup_sum = fields.CharField(source_field='Setup_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    process_sum = fields.CharField(source_field='Process_SUM', max_length=255, blank=True, null=True)  # Field name made lowercase.
    capatotal = fields.CharField(source_field='CapaTotal', max_length=255, blank=True, null=True)  # Field name made lowercase.
    rate = fields.CharField(source_field='Rate', max_length=255, blank=True, null=True)  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost', blank=True, null=True)  # Field name made lowercase.
    worker = fields.CharField(source_field='Worker', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_capacityweek'


class TCheckqty(TortoiseBaseModel):
    noid = fields.IntField(source_field='NOID', unique=True)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty', blank=True, null=True)  # Field name made lowercase.
    checktime = fields.DatetimeField(source_field='CheckTime', blank=True, null=True)  # Field name made lowercase.
    checkqty = fields.FloatField(source_field='CheckQty', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_checkqty'


class TCheckqtyRecord(TortoiseBaseModel):
    noid = fields.IntField(source_field='NOID', unique=True)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty', blank=True, null=True)  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DateField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    setuptime = fields.TimeField(source_field='SetupTime', blank=True, null=True)  # Field name made lowercase.
    checktime = fields.DatetimeField(source_field='CheckTime', blank=True, null=True)  # Field name made lowercase.
    checkqty = fields.FloatField(source_field='CheckQty', blank=True, null=True)  # Field name made lowercase.
    confirmqty = fields.FloatField(source_field='ConfirmQty', blank=True, null=True)  # Field name made lowercase.
    sysuser = fields.CharField(source_field='SysUser', max_length=32, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    systime = fields.DatetimeField(source_field='SysTime')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_checkqty_record'


class TConfirm(TortoiseBaseModel):
    noid = fields.IntField(source_field='NoID', unique=True)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=32)  # Field name made lowercase.
    recordqty = fields.FloatField(source_field='RecordQty')  # Field name made lowercase.
    recorddt = fields.DatetimeField(source_field='RecordDT', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=1, blank=True, null=True, description='Y:已提交/N：末提交')  # Field name made lowercase.
    sysuser = fields.CharField(source_field='SysUser', max_length=255, blank=True, null=True)  # Field name made lowercase.
    systime = fields.DatetimeField(source_field='SysTime', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_confirm'


class TConfirmmax(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey
    # vid = fields.IntField(primary_key=True)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=32)  # Field name made lowercase.
    confirmmax = fields.FloatField(source_field='ConfirmMax', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_confirmmax'
        unique_together = [("supplyno", "itemno")]

class TDemand(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTS/MTO')  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority')  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=32, blank=True, null=True, description='NEW/CRE/REL')  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty')  # Field name made lowercase.
    create_date = fields.DatetimeField(source_field='Create_Date', blank=True, null=True)  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date')  # Field name made lowercase.
    refno = fields.CharField(source_field='RefNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnerno = fields.CharField(source_field='PartnerNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnername = fields.CharField(source_field='PartnerName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    altgrp = fields.CharField(source_field='AltGrp', max_length=8, blank=True, null=True, description='替代组号')  # Field name made lowercase.
    ori_itemno = fields.CharField(source_field='Ori_ItemNo', max_length=4, blank=True, null=True)  # Field name made lowercase.
    ori_qty = fields.FloatField(source_field='Ori_Qty', blank=True, null=True)  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date', blank=True, null=True, auto_now_add=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp', auto_now=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_demand'
        unique_together = [("materialno", "demandno", "itemno")]


class TFieldname(TortoiseBaseModel):
    id = fields.IntField(unique=True)
    tablename = fields.CharField(max_length=255, blank=True, null=True)
    fieldname = fields.CharField(max_length=255, blank=True, null=True)
    title_cn = fields.CharField(max_length=255, blank=True, null=True)
    title_en = fields.CharField(max_length=255, blank=True, null=True)
    is_show = fields.IntField(blank=True, null=True)

    class Meta:
        abstract = True
        table = 't_fieldname'


class TForecast(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey
    # vid = fields.IntField(primary_key=True)
    region = fields.CharField(source_field='Region', max_length=32)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=6, blank=True, null=True)  # Field name made lowercase.
    m01 = fields.FloatField(source_field='M01', blank=True, null=True)  # Field name made lowercase.
    m02 = fields.FloatField(source_field='M02', blank=True, null=True)  # Field name made lowercase.
    m03 = fields.FloatField(source_field='M03', blank=True, null=True)  # Field name made lowercase.
    m04 = fields.FloatField(source_field='M04', blank=True, null=True)  # Field name made lowercase.
    m05 = fields.FloatField(source_field='M05', blank=True, null=True)  # Field name made lowercase.
    m06 = fields.FloatField(source_field='M06', blank=True, null=True)  # Field name made lowercase.
    m07 = fields.FloatField(source_field='M07', blank=True, null=True)  # Field name made lowercase.
    m08 = fields.FloatField(source_field='M08', blank=True, null=True)  # Field name made lowercase.
    m09 = fields.FloatField(source_field='M09', blank=True, null=True)  # Field name made lowercase.
    m10 = fields.FloatField(source_field='M10', blank=True, null=True)  # Field name made lowercase.
    m11 = fields.FloatField(source_field='M11', blank=True, null=True)  # Field name made lowercase.
    m12 = fields.FloatField(source_field='M12', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_forecast'
        unique_together = [("region", "materialno")]


class TForecastlog(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('Year', 'Region', 'project', 'MaterialNo', 'Type')
    # vid = fields.IntField(primary_key=True)
    year = fields.CharField(source_field='Year', max_length=4)  # Field name made lowercase.
    region = fields.CharField(source_field='Region', max_length=32)  # Field name made lowercase.
    project = fields.CharField(max_length=32)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=6)  # Field name made lowercase.
    m01 = fields.FloatField(source_field='M01', blank=True, null=True)  # Field name made lowercase.
    m02 = fields.FloatField(source_field='M02', blank=True, null=True)  # Field name made lowercase.
    m03 = fields.FloatField(source_field='M03', blank=True, null=True)  # Field name made lowercase.
    m04 = fields.FloatField(source_field='M04', blank=True, null=True)  # Field name made lowercase.
    m05 = fields.FloatField(source_field='M05', blank=True, null=True)  # Field name made lowercase.
    m06 = fields.FloatField(source_field='M06', blank=True, null=True)  # Field name made lowercase.
    m07 = fields.FloatField(source_field='M07', blank=True, null=True)  # Field name made lowercase.
    m08 = fields.FloatField(source_field='M08', blank=True, null=True)  # Field name made lowercase.
    m09 = fields.FloatField(source_field='M09', blank=True, null=True)  # Field name made lowercase.
    m10 = fields.FloatField(source_field='M10', blank=True, null=True)  # Field name made lowercase.
    m11 = fields.FloatField(source_field='M11', blank=True, null=True)  # Field name made lowercase.
    m12 = fields.FloatField(source_field='M12', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_forecastlog'
        unique_together = [("year", "region", "project", "materialno", "type")]


class TForecastlogv2(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('Year', 'Region', 'MaterialNo', 'Type')
    # vid = fields.IntField(primary_key=True)
    year = fields.CharField(source_field='Year', max_length=4)  # Field name made lowercase.
    region = fields.CharField(source_field='Region', max_length=32)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=6)  # Field name made lowercase.
    m01 = fields.FloatField(source_field='M01', blank=True, null=True)  # Field name made lowercase.
    m02 = fields.FloatField(source_field='M02', blank=True, null=True)  # Field name made lowercase.
    m03 = fields.FloatField(source_field='M03', blank=True, null=True)  # Field name made lowercase.
    m04 = fields.FloatField(source_field='M04', blank=True, null=True)  # Field name made lowercase.
    m05 = fields.FloatField(source_field='M05', blank=True, null=True)  # Field name made lowercase.
    m06 = fields.FloatField(source_field='M06', blank=True, null=True)  # Field name made lowercase.
    m07 = fields.FloatField(source_field='M07', blank=True, null=True)  # Field name made lowercase.
    m08 = fields.FloatField(source_field='M08', blank=True, null=True)  # Field name made lowercase.
    m09 = fields.FloatField(source_field='M09', blank=True, null=True)  # Field name made lowercase.
    m10 = fields.FloatField(source_field='M10', blank=True, null=True)  # Field name made lowercase.
    m11 = fields.FloatField(source_field='M11', blank=True, null=True)  # Field name made lowercase.
    m12 = fields.FloatField(source_field='M12', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_forecastlogv2'
        unique_together = [("year", "region", "materialno", "type")]


class TForecastsplit(TortoiseBaseModel):
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty', blank=True, null=True)  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date', blank=True, null=True)  # Field name made lowercase.
    itemid = fields.IntField(source_field='ItemID', unique=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_forecastsplit'


class TGroupcolor(TortoiseBaseModel):
    groupno = fields.CharField(source_field='GroupNo', unique=True, max_length=32)  # Field name made lowercase.
    grouptxt = fields.CharField(source_field='GroupTxt', max_length=255, blank=True, null=True)  # Field name made lowercase.
    color = fields.CharField(source_field='Color', max_length=16, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_groupcolor'


class TMatAlt(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('MaterialNo', 'GroupNo', 'ItemNo')
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    groupno = fields.CharField(source_field='GroupNo', max_length=8)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=4)  # Field name made lowercase.
    matalt = fields.CharField(source_field='MatAlt', max_length=64)  # Field name made lowercase.
    altqty = fields.FloatField(source_field='AltQty', blank=True, null=True)  # Field name made lowercase.
    grppri = fields.IntField(source_field='GrpPri', blank=True, null=True)  # Field name made lowercase.
    grprate = fields.DecimalField(source_field='GrpRate', max_digits=5, decimal_places=2, blank=True, null=True, description='%')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_alt'
        unique_together = [("materialno", "groupno", "itemno")]


class TMatGrp(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('GrpNo', 'VerNo')
    # vid = fields.IntField(primary_key=True)
    grpno = fields.CharField(source_field='GrpNo', max_length=6)  # Field name made lowercase.
    verno = fields.CharField(source_field='VerNo', max_length=4)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_grp'
        unique_together = [("grpno", "verno")]


class TMatVer(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=4)  # Field name made lowercase.
    lotfrom = fields.IntField(source_field='LotFrom', blank=True, null=True)  # Field name made lowercase.
    lotto = fields.IntField(source_field='LotTo', blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    refno = fields.CharField(source_field='RefNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    active = fields.CharField(source_field='Active', max_length=1, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_ver'
        unique_together = [("materialno", "matver")]


class TMatWc(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=4)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, description='工作中心，机台')  # Field name made lowercase.
    sortno = fields.IntField(source_field='SortNo', description='唯一')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixqty = fields.IntField(source_field='FixQty')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S=串行, F=并行')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp', auto_now=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_wc'
        unique_together = [("materialno", "matver", "itemno")]


class TMatWcBom(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    productno = fields.CharField(source_field='ProductNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=4)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    qty = fields.FloatField(source_field='Qty')  # Field name made lowercase.
    offsethour = fields.IntField(source_field='OffsetHour')  # Field name made lowercase.
    treeno = fields.IntField(source_field='TreeNo', blank=True, null=True)  # Field name made lowercase.
    mto = fields.CharField(source_field='MTO', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    scrap = fields.FloatField(source_field='Scrap', blank=True, null=True, description='%')  # Field name made lowercase.
    alt = fields.CharField(source_field='Alt', max_length=1, blank=True, null=True, description='Y/N是否是替代')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp', auto_now=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_wc_bom'
        unique_together = [("productno", "matver", "itemno", "materialno")]


class TMatWcBomNa(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('ProductNo', 'MatVer', 'WorkCenter', 'ItemNo', 'MaterialNo')
    # vid = fields.IntField(primary_key=True)
    productno = fields.CharField(source_field='ProductNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=4)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    qty = fields.FloatField(source_field='Qty')  # Field name made lowercase.
    offsethour = fields.IntField(source_field='OffsetHour')  # Field name made lowercase.
    treeno = fields.IntField(source_field='TreeNo', blank=True, null=True)  # Field name made lowercase.
    mto = fields.CharField(source_field='MTO', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    scrap = fields.FloatField(source_field='Scrap', blank=True, null=True, description='%')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_wc_bom_na'
        unique_together = [("productno", "matver", "workcenter", "itemno", "materialno")]


class TMatWcData(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(max_length=255, blank=True, null=True)
    workcenter = fields.CharField(max_length=255, blank=True, null=True)
    basesec = fields.IntField(blank=True, null=True)

    class Meta:
        abstract = True
        table = 't_mat_wc_data'


class TMatWcMold(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('MaterialNo', 'WorkCenter', 'MoldNo')
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64, description='产品')  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, description='机台')  # Field name made lowercase.
    moldno = fields.CharField(source_field='MoldNo', max_length=32)  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec', blank=True, null=True, description='UPH（Units Per Hour）每小时产量')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec', blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_wc_mold'
        unique_together = [("materialno", "workcenter", "moldno")]


class TMatWcSwitch(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('MaterialNo', 'WorkCenter')
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64, description='产品')  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, description='机台')  # Field name made lowercase.
    wbasesec = fields.IntField(source_field='WBaseSec')  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mat_wc_switch'
        unique_together = [("materialno", "workcenter")]


class TMaterial(TortoiseBaseModel):
    materialno = fields.CharField(source_field='MaterialNo', unique=True, max_length=64, description='物料')  # Field name made lowercase.
    description = fields.CharField(source_field='Description', max_length=128)  # Field name made lowercase.
    size = fields.CharField(source_field='Size', max_length=128, blank=True, null=True)  # Field name made lowercase.
    plant = fields.CharField(source_field='Plant', max_length=32, description='工厂')  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay')  # Field name made lowercase.
    expday = fields.IntField(source_field='ExpDay', blank=True, null=True)  # Field name made lowercase.
    grday = fields.IntField(source_field='GRDay')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    unit = fields.CharField(source_field='Unit', max_length=8, blank=True, null=True, description='KG/L/g')  # Field name made lowercase.
    price = fields.DecimalField(source_field='Price', max_digits=10, decimal_places=2, blank=True, null=True)  # Field name made lowercase.
    groupno = fields.CharField(source_field='GroupNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=1, blank=True, null=True)  # Field name made lowercase.
    phantom = fields.CharField(source_field='Phantom', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    phantommin = fields.IntField(source_field='PhantomMin', description='Phantom Offset Time(Minute)')  # Field name made lowercase.
    firmday = fields.IntField(source_field='FirmDay', blank=True, null=True)  # Field name made lowercase.
    daygap = fields.IntField(source_field='DayGap', blank=True, null=True, description='MTO Split')  # Field name made lowercase.
    candelay = fields.CharField(source_field='CanDelay', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    lotsize = fields.CharField(source_field='LotSize', max_length=2, blank=True, null=True, description='EX/FX/D1/D2/D3/D4/D5/D6/W1/W2/W3/W4/M1/M2/VB')  # Field name made lowercase.
    lotfix = fields.FloatField(source_field='LotFix', blank=True, null=True, description='Fixed LotSize')  # Field name made lowercase.
    lotmin = fields.FloatField(source_field='LotMin', blank=True, null=True, description='Minimum Lot Size')  # Field name made lowercase.
    lotmax = fields.FloatField(source_field='LotMax', blank=True, null=True, description='Maximum Lot Size')  # Field name made lowercase.
    lotround = fields.FloatField(source_field='LotRound', blank=True, null=True, description='Rounding value')  # Field name made lowercase.
    lotss = fields.FloatField(source_field='LotSS', blank=True, null=True, description='Safty Stock')  # Field name made lowercase.
    lotpoint = fields.FloatField(source_field='LotPoint', blank=True, null=True, description='trigger Point')  # Field name made lowercase.
    lottop = fields.FloatField(source_field='LotTop', blank=True, null=True, description='Top Value')  # Field name made lowercase.
    planitem = fields.CharField(source_field='PlanItem', max_length=32, blank=True, null=True, description='FC PlanItem, PlanGroup')  # Field name made lowercase.
    preday = fields.IntField(source_field='PreDay', blank=True, null=True, description='FC PreDay')  # Field name made lowercase.
    subday = fields.IntField(source_field='SubDay', blank=True, null=True, description='FC SubDay')  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date', auto_now_add=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp', auto_now=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_material'


class TMaterialData(TortoiseBaseModel):
    materialno = fields.CharField(source_field='MaterialNo', unique=True, max_length=64, description='物料')  # Field name made lowercase.
    description = fields.CharField(source_field='Description', max_length=128)  # Field name made lowercase.
    plant = fields.CharField(source_field='Plant', max_length=32, blank=True, null=True, description='工厂')  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay')  # Field name made lowercase.
    expday = fields.IntField(source_field='ExpDay', blank=True, null=True)  # Field name made lowercase.
    grday = fields.IntField(source_field='GRDay')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    unit = fields.CharField(source_field='Unit', max_length=8, blank=True, null=True, description='KG/L/g')  # Field name made lowercase.
    price = fields.DecimalField(source_field='Price', max_digits=10, decimal_places=2, blank=True, null=True)  # Field name made lowercase.
    groupno = fields.CharField(source_field='GroupNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=1, blank=True, null=True)  # Field name made lowercase.
    firmday = fields.IntField(source_field='FirmDay', blank=True, null=True)  # Field name made lowercase.
    daygap = fields.IntField(source_field='DayGap', blank=True, null=True, description='MTO Split')  # Field name made lowercase.
    candelay = fields.CharField(source_field='CanDelay', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    lotsize = fields.CharField(source_field='LotSize', max_length=2, blank=True, null=True, description='EX/FX/D1/D2/D3/D4/D5/D6/W1/W2/W3/W4/M1/M2/VB')  # Field name made lowercase.
    lotfix = fields.FloatField(source_field='LotFix', blank=True, null=True, description='Fixed LotSize')  # Field name made lowercase.
    lotmin = fields.FloatField(source_field='LotMin', blank=True, null=True, description='Minimum Lot Size')  # Field name made lowercase.
    lotmax = fields.FloatField(source_field='LotMax', blank=True, null=True, description='Maximum Lot Size')  # Field name made lowercase.
    lotround = fields.FloatField(source_field='LotRound', blank=True, null=True, description='Rounding value')  # Field name made lowercase.
    lotss = fields.FloatField(source_field='LotSS', blank=True, null=True, description='Safty Stock')  # Field name made lowercase.
    lotpoint = fields.FloatField(source_field='LotPoint', blank=True, null=True, description='trigger Point')  # Field name made lowercase.
    lottop = fields.FloatField(source_field='LotTop', blank=True, null=True, description='Top Value')  # Field name made lowercase.
    preday = fields.IntField(source_field='PreDay', blank=True, null=True, description='FC PreDay')  # Field name made lowercase.
    subday = fields.IntField(source_field='SubDay', blank=True, null=True, description='FC SubDay')  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date')  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_material_data'


class TMaterialNa(TortoiseBaseModel):
    materialno = fields.CharField(source_field='MaterialNo', unique=True, max_length=64, description='物料')  # Field name made lowercase.
    description = fields.CharField(source_field='Description', max_length=128)  # Field name made lowercase.
    plant = fields.CharField(source_field='Plant', max_length=32, blank=True, null=True, description='工厂')  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay')  # Field name made lowercase.
    expday = fields.IntField(source_field='ExpDay', blank=True, null=True)  # Field name made lowercase.
    grday = fields.IntField(source_field='GRDay')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    unit = fields.CharField(source_field='Unit', max_length=8, blank=True, null=True, description='KG/L/g')  # Field name made lowercase.
    price = fields.DecimalField(source_field='Price', max_digits=10, decimal_places=2, blank=True, null=True)  # Field name made lowercase.
    groupno = fields.CharField(source_field='GroupNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=1, blank=True, null=True)  # Field name made lowercase.
    phantom = fields.CharField(source_field='Phantom', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    phantommin = fields.IntField(source_field='PhantomMin', blank=True, null=True, description='Phantom Offset Time(Minute)')  # Field name made lowercase.
    firmday = fields.IntField(source_field='FirmDay', blank=True, null=True)  # Field name made lowercase.
    daygap = fields.IntField(source_field='DayGap', blank=True, null=True, description='MTO Split')  # Field name made lowercase.
    candelay = fields.CharField(source_field='CanDelay', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    lotsize = fields.CharField(source_field='LotSize', max_length=2, blank=True, null=True, description='EX/FX/D1/D2/D3/D4/D5/D6/W1/W2/W3/W4/M1/M2/VB')  # Field name made lowercase.
    lotfix = fields.FloatField(source_field='LotFix', blank=True, null=True, description='Fixed LotSize')  # Field name made lowercase.
    lotmin = fields.FloatField(source_field='LotMin', blank=True, null=True, description='Minimum Lot Size')  # Field name made lowercase.
    lotmax = fields.FloatField(source_field='LotMax', blank=True, null=True, description='Maximum Lot Size')  # Field name made lowercase.
    lotround = fields.FloatField(source_field='LotRound', blank=True, null=True, description='Rounding value')  # Field name made lowercase.
    lotss = fields.FloatField(source_field='LotSS', blank=True, null=True, description='Safty Stock')  # Field name made lowercase.
    lotpoint = fields.FloatField(source_field='LotPoint', blank=True, null=True, description='trigger Point')  # Field name made lowercase.
    lottop = fields.FloatField(source_field='LotTop', blank=True, null=True, description='Top Value')  # Field name made lowercase.
    planitem = fields.CharField(source_field='PlanItem', max_length=32, blank=True, null=True, description='FC PlanItem, PlanGroup')  # Field name made lowercase.
    preday = fields.IntField(source_field='PreDay', blank=True, null=True, description='FC PreDay')  # Field name made lowercase.
    subday = fields.IntField(source_field='SubDay', blank=True, null=True, description='FC SubDay')  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date')  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_material_na'


class TMold(TortoiseBaseModel):
    moldno = fields.CharField(source_field='MoldNo', unique=True, max_length=32)  # Field name made lowercase.
    moldname = fields.CharField(source_field='MoldName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=8, blank=True, null=True, description="'注塑','冲压','压铸','夹具'")  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=8, blank=True, null=True, description="'空闲','生产中','维修中','报废'")  # Field name made lowercase.
    moldnum = fields.IntField(source_field='MoldNum', blank=True, null=True, description='模具穴数')  # Field name made lowercase.
    qty = fields.IntField(source_field='Qty', blank=True, null=True, description='模具台数')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_mold'


class TNamemapping(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('No', 'Lang')
    # vid = fields.IntField(primary_key=True)
    no = fields.CharField(source_field='No', max_length=12)  # Field name made lowercase.
    name = fields.CharField(source_field='Name', max_length=255, blank=True, null=True)  # Field name made lowercase.
    lang = fields.CharField(source_field='Lang', max_length=2)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_namemapping'
        unique_together = [("no", "lang")]


class TNonWorkdt(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('WorkCenter', 'StartTime', 'EndTime')
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    starttime = fields.DatetimeField(source_field='StartTime')  # Field name made lowercase.
    endtime = fields.DatetimeField(source_field='EndTime')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_non_workdt'
        unique_together = [("workcenter", "starttime", "endtime")]


class TOrderstatus(TortoiseBaseModel):
    orderno = fields.CharField(source_field='OrderNo', unique=True, max_length=64)  # Field name made lowercase.
    orderstatus = fields.CharField(source_field='OrderStatus', max_length=64)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderstatus'


class TOrderwc(TortoiseBaseModel):
    orderno = fields.CharField(source_field='OrderNo', unique=True, max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    sortno = fields.IntField(source_field='SortNo', blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    moldno = fields.CharField(source_field='MoldNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fix = fields.CharField(source_field='Fix', max_length=1, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    baseqty = fields.IntField(source_field='BaseQty')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S/F')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='MEMO', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderwc'


class TOrderwcBackup(TortoiseBaseModel):
    orderno = fields.CharField(source_field='OrderNo', unique=True, max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    sortno = fields.IntField(source_field='SortNo', blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    moldno = fields.CharField(source_field='MoldNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fix = fields.CharField(source_field='Fix', max_length=1, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    baseqty = fields.IntField(source_field='BaseQty')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S/F')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='MEMO', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderwc_backup'


class TOrderwcLog(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('LogNo', 'OrderNo')
    # vid = fields.IntField(primary_key=True)
    userid = fields.CharField(source_field='UserID', max_length=40)  # Field name made lowercase.
    logno = fields.IntField(source_field='LogNo')  # Field name made lowercase.
    orderno = fields.CharField(source_field='OrderNo', max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=32)  # Field name made lowercase.
    sortno = fields.IntField(source_field='SortNo', blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fix = fields.CharField(source_field='Fix', max_length=1, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    baseqty = fields.IntField(source_field='BaseQty')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S/F')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='MEMO', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderwc_log'
        unique_together = [("logno", "orderno")]


class TOrderwcOverlap(TortoiseBaseModel):
    orderno = fields.CharField(source_field='OrderNo', unique=True, max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sortno = fields.CharField(source_field='SortNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fix = fields.CharField(source_field='Fix', max_length=1, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    baseqty = fields.IntField(source_field='BaseQty')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S/F')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='MEMO', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderwc_overlap'


class TOrderwcReturn(TortoiseBaseModel):
    orderno = fields.CharField(source_field='OrderNo', unique=True, max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=32)  # Field name made lowercase.
    sortno = fields.CharField(source_field='SortNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    moldno = fields.CharField(source_field='MoldNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fix = fields.CharField(source_field='Fix', max_length=1, blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    baseqty = fields.IntField(source_field='BaseQty')  # Field name made lowercase.
    basesec = fields.IntField(source_field='BaseSec')  # Field name made lowercase.
    fixsec = fields.IntField(source_field='FixSec')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    sf = fields.CharField(source_field='SF', max_length=1, blank=True, null=True, description='S/F')  # Field name made lowercase.
    offsetsec = fields.IntField(source_field='OffSetSec', blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='MEMO', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_orderwc_return'


class TPeg(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNO', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=64)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64)  # Field name made lowercase.
    s_supplyno = fields.CharField(source_field='S_SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    s_itemno = fields.CharField(source_field='S_ItemNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    s_type = fields.CharField(source_field='S_Type', max_length=64, blank=True, null=True)  # Field name made lowercase.
    pegging = fields.FloatField(source_field='Pegging', blank=True, null=True)  # Field name made lowercase.
    balance = fields.FloatField(source_field='Balance', blank=True, null=True)  # Field name made lowercase.
    refno = fields.CharField(source_field='RefNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    create_time = fields.DatetimeField(blank=True, null=True)
    user_name = fields.CharField(max_length=64, blank=True, null=True)

    class Meta:
        abstract = True
        table = 't_peg'


class TPir(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('MaterialNo', 'VendorNo')
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    vendorno = fields.CharField(source_field='VendorNo', max_length=64)  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay', blank=True, null=True)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    quota = fields.CharField(source_field='Quota', max_length=3, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_pir'
        unique_together = [("materialno", "vendorno")]


class TPlangroup(TortoiseBaseModel):
    planitem = fields.CharField(source_field='PlanItem', unique=True, max_length=32)  # Field name made lowercase.
    planitemname = fields.CharField(source_field='PlanItemName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    plangroup = fields.CharField(source_field='PlanGroup', max_length=32)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_plangroup'


class TPlanlog(TortoiseBaseModel):
    planno = fields.IntField(source_field='PlanNo', unique=True)  # Field name made lowercase.
    plantype = fields.CharField(source_field='PlanType', max_length=16)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    dt_begin = fields.DatetimeField(source_field='DT_Begin')  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End')  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start')  # Field name made lowercase.
    planinterval = fields.IntField(source_field='PlanInterval', blank=True, null=True)  # Field name made lowercase.
    ratestring = fields.CharField(source_field='RateString', max_length=20, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_planlog'


class TPlanner(TortoiseBaseModel):
    planner = fields.CharField(source_field='Planner', unique=True, max_length=8)  # Field name made lowercase.
    plannertxt = fields.CharField(source_field='PlannerTxt', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=1, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_planner'


class TPlanresult(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('PlanNo', 'OrderNo')
    # vid = fields.IntField(primary_key=True)
    planno = fields.IntField(source_field='PlanNo')  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.
    orderno = fields.CharField(source_field='OrderNo', max_length=64)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    groupno = fields.CharField(source_field='GroupNo', max_length=32, blank=True, null=True)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority', blank=True, null=True)  # Field name made lowercase.
    orderqty = fields.FloatField(source_field='OrderQty')  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost', blank=True, null=True)  # Field name made lowercase.
    dt_start = fields.DatetimeField(source_field='DT_Start', blank=True, null=True)  # Field name made lowercase.
    dt_end = fields.DatetimeField(source_field='DT_End', blank=True, null=True)  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    delay_day = fields.IntField(source_field='Delay_Day', blank=True, null=True)  # Field name made lowercase.
    early_day = fields.IntField(source_field='Early_Day', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_planresult'
        unique_together = [("planno", "orderno")]


class TPriority(TortoiseBaseModel):
    priortyno = fields.CharField(source_field='PriortyNo', unique=True, max_length=16)  # Field name made lowercase.
    priorityname = fields.CharField(source_field='PriorityName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_priority'


class TReport(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    orderno = fields.CharField(source_field='OrderNo', max_length=64)  # Field name made lowercase.
    product = fields.CharField(source_field='Product', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32, blank=True, null=True)  # Field name made lowercase.
    order_qty = fields.FloatField(source_field='Order_Qty')  # Field name made lowercase.
    order_date = fields.DatetimeField(source_field='Order_Date')  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    material_desc = fields.CharField(source_field='Material_DESC', max_length=128, blank=True, null=True)  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', blank=True, null=True, description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    mtype = fields.CharField(source_field='MType', max_length=1, blank=True, null=True)  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay', blank=True, null=True)  # Field name made lowercase.
    leaddate = fields.DateField(source_field='LeadDate', blank=True, null=True)  # Field name made lowercase.
    offsethour = fields.IntField(source_field='OffSetHour', blank=True, null=True)  # Field name made lowercase.
    rate = fields.FloatField(source_field='Rate', blank=True, null=True)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=4)  # Field name made lowercase.
    dtype = fields.CharField(source_field='DType', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, blank=True, null=True)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTS/MTO')  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty')  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date')  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date', blank=True, null=True)  # Field name made lowercase.
    aging_date = fields.DatetimeField(source_field='Aging_Date', blank=True, null=True)  # Field name made lowercase.
    req_lead_day = fields.IntField(source_field='Req_Lead_Day', blank=True, null=True)  # Field name made lowercase.
    due_date = fields.IntField(source_field='Due_Date', blank=True, null=True)  # Field name made lowercase.
    pegging = fields.FloatField(source_field='Pegging', blank=True, null=True)  # Field name made lowercase.
    balance = fields.FloatField(source_field='Balance', blank=True, null=True)  # Field name made lowercase.
    delay_hour = fields.BigIntField(source_field='Delay_Hour', blank=True, null=True)  # Field name made lowercase.
    pegging_sum = fields.FloatField(source_field='Pegging_SUM', blank=True, null=True)  # Field name made lowercase.
    pegging_result = fields.FloatField(source_field='Pegging_Result', blank=True, null=True)  # Field name made lowercase.
    hvtime = fields.CharField(source_field='HvTime', max_length=3, db_collation='utf8mb4_0900_ai_ci')  # Field name made lowercase.
    orderstatus = fields.CharField(source_field='OrderStatus', max_length=1, db_collation='utf8mb4_0900_ai_ci')  # Field name made lowercase.
    create_date = fields.DatetimeField(blank=True, null=True)
    user_name = fields.CharField(max_length=64, blank=True, null=True)

    class Meta:
        abstract = True
        table = 't_report'


class TSetuptime(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('SetupNo', 'PreGroup', 'SubGroup')
    # vid = fields.IntField(primary_key=True)
    setupno = fields.CharField(source_field='SetupNo', max_length=4)  # Field name made lowercase.
    pregroup = fields.CharField(source_field='PreGroup', max_length=32)  # Field name made lowercase.
    subgroup = fields.CharField(source_field='SubGroup', max_length=32)  # Field name made lowercase.
    setupsec = fields.IntField(source_field='SetupSec')  # Field name made lowercase.
    setupcost = fields.IntField(source_field='SetupCost')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_setuptime'
        unique_together = [("setupno", "pregroup", "subgroup")]


class TShiftdate(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('WorkCenter', 'ShiftDate')
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    shiftdate = fields.DateField(source_field='ShiftDate')  # Field name made lowercase.
    shiftno = fields.CharField(source_field='ShiftNo', max_length=4)  # Field name made lowercase.
    capnum = fields.IntField(source_field='CapNum')  # Field name made lowercase.
    caprate = fields.FloatField(source_field='CapRate')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_shiftdate'
        unique_together = [("workcenter", "shiftdate")]


class TShifttime(TortoiseBaseModel):
    noid = fields.IntField(source_field='NoID', unique=True)  # Field name made lowercase.
    shiftno = fields.CharField(source_field='ShiftNo', max_length=4)  # Field name made lowercase.
    starttime = fields.TimeField(source_field='StartTime')  # Field name made lowercase.
    endtime = fields.TimeField(source_field='EndTime')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_shifttime'


class TSoPln(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=4)  # Field name made lowercase.
    dtype = fields.CharField(source_field='DType', max_length=64)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTS/MTO')  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority')  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    description = fields.CharField(source_field='Description', max_length=128, blank=True, null=True)  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', blank=True, null=True, description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    create_time = fields.DatetimeField(source_field='Create_Time', blank=True, null=True)  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty')  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date')  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date', blank=True, null=True)  # Field name made lowercase.
    pegging = fields.FloatField(source_field='Pegging', blank=True, null=True)  # Field name made lowercase.
    balance = fields.FloatField(source_field='Balance', blank=True, null=True)  # Field name made lowercase.
    delay_hour = fields.BigIntField(source_field='Delay_Hour', blank=True, null=True)  # Field name made lowercase.
    pegging_sum = fields.FloatField(source_field='Pegging_SUM', blank=True, null=True)  # Field name made lowercase.
    pegging_result = fields.FloatField(source_field='Pegging_Result', blank=True, null=True)  # Field name made lowercase.
    orderstatus = fields.CharField(source_field='OrderStatus', max_length=9, blank=True, null=True)  # Field name made lowercase.
    create_date = fields.DatetimeField(blank=True, null=True)
    user_name = fields.CharField(max_length=64, blank=True, null=True)
    refno = fields.CharField(source_field='RefNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnerno = fields.CharField(source_field='PartnerNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnername = fields.CharField(source_field='PartnerName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_so_pln'


class TSort(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('WorkCenter', 'SortName')
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    sortno = fields.IntField(source_field='SortNo', description='1,2,3')  # Field name made lowercase.
    sortname = fields.CharField(source_field='SortName', max_length=32, description='T_SortField')  # Field name made lowercase.
    direction = fields.CharField(source_field='Direction', max_length=4, blank=True, null=True, description='ASC/DES')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_sort'
        unique_together = [("workcenter", "sortname")]


class TSortfield(TortoiseBaseModel):
    sortname = fields.CharField(source_field='SortName', unique=True, max_length=32)  # Field name made lowercase.
    sortdesc = fields.CharField(source_field='SortDesc', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_sortfield'


class TSqlcheck(TortoiseBaseModel):
    noid = fields.IntField(source_field='NoID', unique=True)  # Field name made lowercase.
    name = fields.CharField(source_field='Name', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sqltext = fields.CharField(source_field='SQLText', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_sqlcheck'


class TSupply(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32, blank=True, null=True)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=6)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTO/MTS')  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority')  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=32, blank=True, null=True, description='Release, Confirmation')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty')  # Field name made lowercase.
    create_date = fields.DatetimeField(source_field='Create_Date', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date')  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    avail_end_date = fields.DatetimeField(source_field='Avail_End_Date', blank=True, null=True)  # Field name made lowercase.
    batchno = fields.CharField(source_field='BatchNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    vendorno = fields.CharField(source_field='VendorNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnerno = fields.CharField(source_field='PartnerNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnername = fields.CharField(source_field='PartnerName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date', blank=True, null=True, auto_now_add=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp', auto_now=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_supply'
        unique_together = [("materialno", "supplyno")]


class TSupplyNa(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('MaterialNo', 'SupplyNo')
    # vid = fields.IntField(primary_key=True)
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32, blank=True, null=True)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=64)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTO/MTS')  # Field name made lowercase.
    priority = fields.IntField(source_field='Priority')  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=32, blank=True, null=True, description='Release, Confirmation')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty')  # Field name made lowercase.
    create_date = fields.DatetimeField(source_field='Create_Date', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date')  # Field name made lowercase.
    dt_req = fields.DatetimeField(source_field='DT_Req', blank=True, null=True)  # Field name made lowercase.
    avail_end_date = fields.DatetimeField(source_field='Avail_End_Date', blank=True, null=True)  # Field name made lowercase.
    batchno = fields.CharField(source_field='BatchNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    vendorno = fields.CharField(source_field='VendorNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnerno = fields.CharField(source_field='PartnerNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    partnername = fields.CharField(source_field='PartnerName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free1 = fields.CharField(source_field='Free1', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free2 = fields.CharField(source_field='Free2', max_length=255, blank=True, null=True)  # Field name made lowercase.
    free3 = fields.CharField(source_field='Free3', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    sys_date = fields.DatetimeField(source_field='Sys_Date', blank=True, null=True)  # Field name made lowercase.
    sys_user = fields.CharField(source_field='Sys_User', max_length=32, blank=True, null=True)  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_supply_na'
        unique_together = [("materialno", "supplyno")]


class TSupplyconfirmqty(TortoiseBaseModel):
    noid = fields.IntField(source_field='NoID', unique=True)  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32)  # Field name made lowercase.
    confirmqty = fields.FloatField(source_field='ConfirmQty')  # Field name made lowercase.
    sys_stamp = fields.DatetimeField(source_field='Sys_Stamp')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_supplyconfirmqty'


class TSyslog(TortoiseBaseModel):
    idno = fields.IntField(source_field='IDNo', unique=True)  # Field name made lowercase.
    timeid = fields.DatetimeField(source_field='TimeID')  # Field name made lowercase.
    userid = fields.CharField(source_field='UserID', max_length=40)  # Field name made lowercase.
    action = fields.CharField(source_field='Action', max_length=255)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_syslog'


class TSyspara(TortoiseBaseModel):
    paraid = fields.CharField(source_field='ParaID', unique=True, max_length=32)  # Field name made lowercase.
    paravalue = fields.CharField(source_field='ParaValue', max_length=32, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_syspara'


class TTempAbc(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    abc = fields.CharField(source_field='ABC', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_temp_abc'


class TTimepara(TortoiseBaseModel):
    timeno = fields.CharField(source_field='TimeNo', unique=True, max_length=8)  # Field name made lowercase.
    timename = fields.CharField(source_field='TimeName', max_length=8)  # Field name made lowercase.
    beginday = fields.IntField(source_field='BeginDay', blank=True, null=True)  # Field name made lowercase.
    endday = fields.IntField(source_field='EndDay', blank=True, null=True)  # Field name made lowercase.
    startday = fields.IntField(source_field='StartDay', blank=True, null=True)  # Field name made lowercase.
    starttime = fields.TimeField(source_field='StartTime', blank=True, null=True)  # Field name made lowercase.
    finishday = fields.IntField(source_field='FinishDay', blank=True, null=True)  # Field name made lowercase.
    finishtime = fields.TimeField(source_field='FinishTime', blank=True, null=True)  # Field name made lowercase.
    scheday = fields.IntField(source_field='ScheDay', blank=True, null=True)  # Field name made lowercase.
    schetime = fields.TimeField(source_field='ScheTime', blank=True, null=True)  # Field name made lowercase.
    zoomnum = fields.IntField(source_field='ZoomNum', blank=True, null=True)  # Field name made lowercase.
    initial = fields.CharField(source_field='Initial', max_length=1, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.
    workcenter = fields.TextField(source_field='WorkCenter', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_timepara'


class TTreeso(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    orderno = fields.CharField(source_field='OrderNo', max_length=64)  # Field name made lowercase.
    product = fields.CharField(source_field='Product', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32, blank=True, null=True)  # Field name made lowercase.
    order_qty = fields.FloatField(source_field='Order_Qty')  # Field name made lowercase.
    order_date = fields.DatetimeField(source_field='Order_Date')  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    material_desc = fields.CharField(source_field='Material_DESC', max_length=128, blank=True, null=True)  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', blank=True, null=True, description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    mtype = fields.CharField(source_field='MType', max_length=1, blank=True, null=True)  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay', blank=True, null=True)  # Field name made lowercase.
    leaddate = fields.DateField(source_field='LeadDate', blank=True, null=True)  # Field name made lowercase.
    offsethour = fields.IntField(source_field='OffSetHour', blank=True, null=True)  # Field name made lowercase.
    rate = fields.FloatField(source_field='Rate', blank=True, null=True)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=4)  # Field name made lowercase.
    dtype = fields.CharField(source_field='DType', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, blank=True, null=True)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTS/MTO')  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty')  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date')  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date', blank=True, null=True)  # Field name made lowercase.
    aging_date = fields.DatetimeField(source_field='Aging_Date', blank=True, null=True)  # Field name made lowercase.
    req_lead_day = fields.IntField(source_field='Req_Lead_Day', blank=True, null=True)  # Field name made lowercase.
    due_date = fields.IntField(source_field='Due_Date', blank=True, null=True)  # Field name made lowercase.
    pegging = fields.FloatField(source_field='Pegging', blank=True, null=True)  # Field name made lowercase.
    balance = fields.FloatField(source_field='Balance', blank=True, null=True)  # Field name made lowercase.
    delay_hour = fields.BigIntField(source_field='Delay_Hour', blank=True, null=True)  # Field name made lowercase.
    pegging_sum = fields.FloatField(source_field='Pegging_SUM', blank=True, null=True)  # Field name made lowercase.
    pegging_result = fields.FloatField(source_field='Pegging_Result', blank=True, null=True)  # Field name made lowercase.
    hvtime = fields.CharField(source_field='HvTime', max_length=3, blank=True, null=True)  # Field name made lowercase.
    orderstatus = fields.CharField(source_field='OrderStatus', max_length=9, blank=True, null=True)  # Field name made lowercase.
    create_date = fields.DatetimeField(blank=True, null=True)
    user_name = fields.CharField(max_length=64, blank=True, null=True)
    topno = fields.CharField(source_field='TopNO', max_length=64, blank=True, null=True)  # Field name made lowercase.
    treeno = fields.IntField(source_field='TreeNo', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_treeso'


class TType(TortoiseBaseModel):
    type = fields.CharField(source_field='Type', unique=True, max_length=8)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=2, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_type'


class TVendor(TortoiseBaseModel):
    vendorno = fields.CharField(source_field='VendorNo', unique=True, max_length=64)  # Field name made lowercase.
    vendorname = fields.CharField(source_field='VendorName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    contacter = fields.CharField(source_field='Contacter', max_length=255, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=255, blank=True, null=True)  # Field name made lowercase.
    phone = fields.CharField(source_field='Phone', max_length=255, blank=True, null=True)  # Field name made lowercase.
    email = fields.CharField(source_field='Email', max_length=255, blank=True, null=True)  # Field name made lowercase.
    web = fields.CharField(source_field='Web', max_length=255, blank=True, null=True)  # Field name made lowercase.
    address = fields.CharField(source_field='Address', max_length=255, blank=True, null=True)  # Field name made lowercase.
    status = fields.CharField(source_field='Status', max_length=255, blank=True, null=True)  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_vendor'


class TWorkcenter(TortoiseBaseModel):
    workcenter = fields.CharField(source_field='WorkCenter', unique=True, max_length=32)  # Field name made lowercase.
    workcentername = fields.CharField(source_field='WorkCenterName', max_length=255, blank=True, null=True)  # Field name made lowercase.
    pri_wc = fields.IntField(source_field='Pri_WC', blank=True, null=True, description='Planning时，多个WorkCenter的优先级选定')  # Field name made lowercase.
    bottleneck = fields.CharField(source_field='Bottleneck', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    sortno = fields.CharField(source_field='SortNo', max_length=4, blank=True, null=True)  # Field name made lowercase.
    plant = fields.CharField(source_field='Plant', max_length=32, blank=True, null=True)  # Field name made lowercase.
    location = fields.CharField(source_field='Location', max_length=32, blank=True, null=True)  # Field name made lowercase.
    finite = fields.CharField(source_field='Finite', max_length=1, blank=True, null=True, description='Y/N')  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=32, blank=True, null=True)  # Field name made lowercase.
    capnum = fields.IntField(source_field='CapNum', blank=True, null=True)  # Field name made lowercase.
    capmax = fields.IntField(source_field='CapMax', blank=True, null=True)  # Field name made lowercase.
    worker = fields.FloatField(source_field='Worker', blank=True, null=True, description='工时')  # Field name made lowercase.
    setupno = fields.CharField(source_field='SetupNo', max_length=6, blank=True, null=True, description='切换组')  # Field name made lowercase.
    grpno = fields.CharField(source_field='GrpNo', max_length=6, blank=True, null=True, description='同类')  # Field name made lowercase.
    memo = fields.CharField(source_field='Memo', max_length=255, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_workcenter'


class TWorkcenterCheckpoint(TortoiseBaseModel):
    # pk = fields.CompositePrimaryKey('WorkCenter', 'CheckTime')
    # vid = fields.IntField(primary_key=True)
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32)  # Field name made lowercase.
    checktime = fields.TimeField(source_field='CheckTime')  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 't_workcenter_checkpoint'
        unique_together = [("workcenter", "checktime")]


class TWorkcenteruser(TortoiseBaseModel):
    username = fields.CharField(unique=True, max_length=255, description='用户名')
    workcenter = fields.CharField(max_length=1255, blank=True, null=True, description='分配工作中心')

    class Meta:
        abstract = True
        table = 't_workcenteruser'


class TmpReport(TortoiseBaseModel):
    # vid = fields.IntField(primary_key=True)
    orderno = fields.CharField(source_field='OrderNo', max_length=64)  # Field name made lowercase.
    product = fields.CharField(source_field='Product', max_length=64)  # Field name made lowercase.
    matver = fields.CharField(source_field='MatVer', max_length=32, blank=True, null=True)  # Field name made lowercase.
    order_qty = fields.FloatField(source_field='Order_Qty')  # Field name made lowercase.
    order_date = fields.DatetimeField(source_field='Order_Date')  # Field name made lowercase.
    materialno = fields.CharField(source_field='MaterialNo', max_length=64)  # Field name made lowercase.
    material_desc = fields.CharField(source_field='Material_DESC', max_length=128, blank=True, null=True)  # Field name made lowercase.
    planner = fields.CharField(source_field='Planner', max_length=64, blank=True, null=True)  # Field name made lowercase.
    fifo = fields.IntField(source_field='FIFO', blank=True, null=True, description='Y-FIFO ,N-最近原则')  # Field name made lowercase.
    abc = fields.CharField(source_field='ABC', max_length=8, blank=True, null=True)  # Field name made lowercase.
    mtype = fields.CharField(source_field='MType', max_length=1, blank=True, null=True)  # Field name made lowercase.
    leadday = fields.IntField(source_field='LeadDay', blank=True, null=True)  # Field name made lowercase.
    leaddate = fields.DateField(source_field='LeadDate', blank=True, null=True)  # Field name made lowercase.
    offsethour = fields.IntField(source_field='OffSetHour', blank=True, null=True)  # Field name made lowercase.
    alt = fields.CharField(source_field='Alt', max_length=1, blank=True, null=True, description='Y/N是否是替代')  # Field name made lowercase.
    rate = fields.FloatField(source_field='Rate', blank=True, null=True)  # Field name made lowercase.
    demandno = fields.CharField(source_field='DemandNo', max_length=64)  # Field name made lowercase.
    itemno = fields.CharField(source_field='ItemNo', max_length=4)  # Field name made lowercase.
    dtype = fields.CharField(source_field='DType', max_length=64)  # Field name made lowercase.
    workcenter = fields.CharField(source_field='WorkCenter', max_length=32, blank=True, null=True)  # Field name made lowercase.
    category = fields.CharField(source_field='Category', max_length=32, blank=True, null=True, description='MTS/MTO')  # Field name made lowercase.
    req_qty = fields.FloatField(source_field='Req_Qty')  # Field name made lowercase.
    req_date = fields.DatetimeField(source_field='Req_Date')  # Field name made lowercase.
    supplyno = fields.CharField(source_field='SupplyNo', max_length=64, blank=True, null=True)  # Field name made lowercase.
    type = fields.CharField(source_field='Type', max_length=64, blank=True, null=True, description='PL/MO')  # Field name made lowercase.
    avail_qty = fields.FloatField(source_field='Avail_Qty', blank=True, null=True)  # Field name made lowercase.
    avail_date = fields.DatetimeField(source_field='Avail_Date', blank=True, null=True)  # Field name made lowercase.
    aging_date = fields.DatetimeField(source_field='Aging_Date', blank=True, null=True)  # Field name made lowercase.
    req_lead_day = fields.IntField(source_field='Req_Lead_Day', blank=True, null=True)  # Field name made lowercase.
    due_date = fields.IntField(source_field='Due_Date', blank=True, null=True)  # Field name made lowercase.
    pegging = fields.FloatField(source_field='Pegging', blank=True, null=True)  # Field name made lowercase.
    balance = fields.FloatField(source_field='Balance', blank=True, null=True)  # Field name made lowercase.
    delay_hour = fields.IntField(source_field='Delay_Hour', blank=True, null=True)  # Field name made lowercase.
    altgrp = fields.CharField(source_field='AltGrp', max_length=8, blank=True, null=True, description='替代组号')  # Field name made lowercase.
    ori_itemno = fields.CharField(source_field='Ori_ItemNo', max_length=4, blank=True, null=True)  # Field name made lowercase.
    ori_qty = fields.FloatField(source_field='Ori_Qty', blank=True, null=True)  # Field name made lowercase.
    pegging_sum = fields.FloatField(source_field='Pegging_SUM', blank=True, null=True)  # Field name made lowercase.
    sku_qty = fields.FloatField(source_field='SKU_Qty', blank=True, null=True)  # Field name made lowercase.
    pegging_result = fields.FloatField(source_field='Pegging_Result', blank=True, null=True)  # Field name made lowercase.
    hvtime = fields.CharField(source_field='HvTime', max_length=3, db_collation='utf8mb4_0900_ai_ci')  # Field name made lowercase.
    orderstatus = fields.CharField(source_field='OrderStatus', max_length=1, db_collation='utf8mb4_0900_ai_ci')  # Field name made lowercase.
    create_date = fields.DatetimeField(blank=True, null=True)
    user_name = fields.CharField(max_length=64, blank=True, null=True)

    class Meta:
        abstract = True
        table = 'tmp_report'


class TmpWorkcenterSwitch(TortoiseBaseModel):
    workcenter = fields.CharField(source_field='WorkCenter', unique=True, max_length=32)  # Field name made lowercase.

    class Meta:
        abstract = True
        table = 'tmp_workcenter_switch'
