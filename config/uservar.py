myaps_is_pro = True     # MyAPS是否专业版

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

auto_matver = True  # 是否自动生成物料版本号
example_matver = "V1"  # 示例物料版本号
default_lot_from = 0
default_lotto = 9999999
default_priority = 0
default_itemno = 'A001'
# workcenter_sort = {'SP-01':'A150','SP-02':'A160','JP-01':'B110','JP-02':'B120','JP-03':'B130','JP-04':'B140','JP-05':'B150','JP-06':'B160','JP-07':'B170','JP-08':'B180','JP-09':'B190','JP-10':'B200','JP-11':'B210','GJ-01':'C110','GJ-02':'C120','GJ-03':'C130','GJ-04':'C140','A-01':'DA01','A-02':'DA02','A-03':'DA03','A-04':'DA04','A-05':'DA05','A-06':'DA06','A-07':'DA07','B-01':'DB01','B-02':'DB02','B-03':'DB03','B-04':'DB04','B-05':'DB05','B-06':'DB06','B-07':'DB07','B-08':'DB08','B-09':'DB09','B-10':'DB10','C-01':'DC01','C-02':'DC02','C-03':'DC03','C-04':'DC04','C-05':'DC05','C-06':'DC06','C-07':'DC07','C-08':'DC08','C-09':'DC09','C-10':'DC10','C-11':'DC11','C-12':'DC12','C-13':'DC13','C-14':'DC14','C-15':'DC15','C-16':'DC16','D-01':'DD01','D-02':'DD02','D-03':'DD03','D-04':'DD04','D-05':'DD05','D-06':'DD06','D-07':'DD07','D-08':'DD08','D-09':'DD09','D-10':'DD10','D-11':'DD11','E-01':'DE01','E-02':'DE02','E-03':'DE03','E-04':'DE04','E-05':'DE05','E-06':'DE06','E-07':'DE07','E-08':'DE08','E-09':'DE09','E-10':'DE10','F-01':'DF01','F-02':'DF02','F-03':'DF03','F-04':'DF04','F-05':'DF05','F-06':'DF06','F-07':'DF07','F-08':'DF08','G-01':'DG01','G-02':'DG02','G-03':'DG03','G-04':'DG04','G-05':'DG05','ZDX-01':'E110','ZDX-02':'E120','ZDX-03':'E130','ZDX-04':'E140','ZDX-05':'E150','ZDX-06':'E160','ZDX-07':'E170','ZDX-08':'E180','ZDX-09':'E190','ZDX-10':'E200','ZDX-11':'E210','YZ-01':'E220','XM-01':'E230','XM-02':'E240','XM-03':'E250','XM-04':'E260','GZX-01':'E270','GZX-02':'E280','GZX-03':'E290','GZX-04':'E300','GZX-05':'E310','GZX-06':'E320','YZ-06':'E330','NTFX-01':'E340','DLS-01':'E350','YZ-20':'E360','HJ-01':'E370','YM-01':'E380','GZ-02':'E390','PM-01':'E400','TM-01':'E410','BZ-01':'E420','BZ-02':'E430','PQ-01':'E440'}


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

t_mold = {
    "MoldNo": "moldno",
    "MoldName": "moldname",
    "Type": "type",
    "Status": "status",
    "MoldNum": "moldnum",
    "Qty": "qty",
    "Memo": "memo",
}

t_mat_wc_mold = {
    "MaterialNo": "materialno",
    "WorkCenter": "workcenter",
    "MoldNo": "moldno",
    "BaseSec": "basesec",
    "Bottleneck": "bottleneck",
    "Priority": "priority",
    "Memo": "memo",
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
    "Color": "color",
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
