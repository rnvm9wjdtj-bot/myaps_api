myaps_is_pro = True     # myaps是否专业版

# 主数据默认值
# 物料
default_plant = "1600"   # 默认工厂
default_planner = "haida"   # 默认计划员
default_fifo = 1   # 默认FIFO原则
default_leadday_e = 10  # 自制件默认提前期
default_leadday_f = 1  # 采购件默认提前期
default_expday = 365  # 默认保质期
default_price = 0  # 默认价格
default_grday_e = 0
default_grday_f = 1
default_phantom = 'N'
default_phantommin = 0
default_firmday = 0
default_daygap = 1
default_candelay = 'Y'
default_lotsize = 'EX'  # 默认批次大小
default_lotfix = 0  # 默认固定批
default_lotmin = 0  # 默认最小批
default_lotmax = 0  # 默认最大批
default_lotround = 0  # 默认取整
default_lotss = 0  # 默认安全库存
default_lotpoint = 0  # 默认重订货点
default_lottop = 0  # 默认最大库存点
default_preday = 999  # 默认向前冲销(天)
default_subday = 999  # 默认向后冲销(天)



default_matver = 'V1'


# 前后端字段映射关系，某些客户可能需要
#  {数据库字段: 客户字段}
t_material = {
    "MaterialNo": "materialno",
    "Description": "description",
    "Size": "size",
    "Unit": "unit",
    "Price": "price",
    "Remark": "remark",
}

t_workcenter = {
    "WorkCenter": "workcenter",
}

t_mat_wc = {

}

t_mat_ver = {

}

t_mat_wc_bom = {

}

t_supply = {

}

t_demand = {

}

v_supply_mo = {
    "MaterialNo": "materialno",
    "Description": "description",
    "Planner": "planner",
    "GroupNo": "groupno",
    "PlanItem": "planitem",
    "FIFO": "fifo",
    "ABC": "abc",
    "ExpDay": "expday",
    "GRDay": "grday",
    "Phantom": "phantom",
    "PhantomMin": "phantommin",
    "SupplyNo": "supplyno",
    "ItemNo": "itemno",
    "MatVer": "matver",
    "Type": "type",
    "Category": "category",
    "Status": "status",
    "Priority": "priority",
    "Avail_Qty": "avail_qty",
    "Delay_Hour": "delay_hour",
    "Create_Date": "create_date",
    "DT_OrdStart": "dt_ordstart",
    "DT_OrdEnd": "dt_ordend",
    "OrdTime": "ordtime",
    "Avail_Date": "avail_date",
    "Avail_End_Date": "avail_end_date",
    "DT_Req": "dt_req",
    "Req_Date": "req_date",
    "RemainTime": "remaintime",
    "VendorNo": "vendorno",
    "Memo": "memo",
    "Sys_Stamp": "sys_stamp",
}

v_orderwc = {
    "OrderNo": "orderno",
    "SupplyNo": "supplyno",
    "ItemNo": "itemno",
    "MatVer": "matver",
    "MaterialNo": "materialno",
    "Description": "description",
    "WorkCenter": "workcenter",
    "MoldNo": "moldno",
    "SortNo": "sortno",
    "Bottleneck": "bottleneck",
    "GroupNo": "groupno",
    "Fix": "fix",
    "Type": "type",
    "Category": "category",
    "Priority": "priority",
    "S_Priority": "s_priority",
    "Status": "status",
    "OrderQty": "orderqty",
    "ConfirmQty": "confirmqty",
    "OriginalQty": "originalqty",
    "BaseQty": "baseqty",
    "BaseSec": "basesec",
    "FixSec": "fixsec",
    "SF": "sf",
    "OffSetSec": "offsetsec",
    "SetupCost": "setupcost",
    "SetupSec": "setupsec",
    "ABC": "abc",
    "Delay_Hour": "delay_hour",
    "SetupTime": "setuptime",
    "DT_Start": "dt_start",
    "DT_End": "dt_end",
    "ProcessTime": "processtime",
    "DT_Req": "dt_req",
    "Req_Date": "req_date",
    "RemainTime": "remaintime",
    "VendorNo": "vendorno",
    "MEMO": "memo",
    "Sys_Stamp": "sys_stamp"
}

v_matdailyqtyreport = {
    "MaterialNo": "materialno",
    "Description": "description",
    "Size": "size",
    "Type": "type",
    "ABC": "abc",
    "Planner": "planner",
    "Name": "name",
    "StockQty": "stockqty",
    "DateStr": "datestr",
    "TotalDemand": "total_demand",
    "TotalSupply": "totalsupply",
    "DailyBalance": "dailybalance",
    "CumulativeBalance": "cumulativebalance",
}
