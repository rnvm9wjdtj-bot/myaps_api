from datetime import datetime
from typing import Literal, Optional#, List, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator#, ValidationError

from config import forcustomer as fc


class AcceptMaterial(BaseModel):
    materialno: str = Field(..., alias=fc.t_material.get("MaterialNo", "materialno"), description="料号")
    description: str = Field(..., alias=fc.t_material.get("Description", "description"), description="物料名称")
    size: str = Field(None, alias=fc.t_material.get("Size", "size"), description="规格")
    plant: str = Field(fc.default_plant, alias=fc.t_material.get("Plant", "plant"), description='工厂')
    planner: str = Field(fc.default_planner, alias=fc.t_material.get("Planner", "planner"), description="计划员")
    fifo: int = Field(fc.default_fifo, alias=fc.t_material.get("FIFO", "fifo"), ge=0, le=1, description='1-FIFO 0-最近原则')
    leadday: int = Field(alias=fc.t_material.get("LeadDay", "leadday"), ge=0, description="交期（天）")
    expday: int = Field(fc.default_expday, alias=fc.t_material.get("ExpDay", "expday"), ge=0, description="保质期（天）")
    grday: int = Field(alias=fc.t_material.get("GRDay", "grday"), ge=0, description="收货质检（天）")
    abc: Literal["A", "B", "C"] = Field(alias=fc.t_material.get("ABC", "abc"), description="ABC分类")
    unit: str = Field(alias=fc.t_material.get("Unit", "unit"), description='单位')
    price: Decimal = Field(fc.default_price, alias=fc.t_material.get("Price", "price"), description="价格")
    groupno: str = Field(..., alias=fc.t_material.get("GroupNo", "groupno"), description="型号")
    type: Literal["E", "F"] = Field(... if fc.myaps_is_pro else None, alias=fc.t_material.get("type", "type"), description="物料类型  E-自制件 F-采购件")
    phantom: Literal["N", "Y"] = Field(fc.default_phantom, alias=fc.t_material.get("Phantom", "phantom"), description='虚拟件')
    phantommin: int = Field(fc.default_phantommin, alias=fc.t_material.get("PhantomMin", "phantommin"), ge=0, description='虚拟时间(Minute)')
    firmday: int = Field(fc.default_firmday, alias=fc.t_material.get("FirmDay", "firmday"), ge=0, description="固定天数")
    daygap: int = Field(fc.default_daygap, alias=fc.t_material.get("DayGap", "daygap"), ge=0, description='MTO拆分天数')
    candelay: Literal["N", "Y"] = Field(fc.default_candelay, alias=fc.t_material.get("CanDelay", "candelay"), description='可否延迟')
    lotsize: Literal["EX", "FX", "D1", "D2", "D3", "D4", "D5", "D6", "W1", "W2", "W3", "W4", "M1", "M2", "VB"] = Field(fc.default_lotsize, alias=fc.t_material.get("LotSize", "lotsize"), max_length=2, description='批量')
    lotfix: float = Field(fc.default_lotfix, alias=fc.t_material.get("LotFix", "lotfix"), ge=0, description='固定批')
    lotmin: float = Field(fc.default_lotmin, alias=fc.t_material.get("LotMin", "lotmin"), ge=0, description='最小批')
    lotmax: float = Field(fc.default_lotmax, alias=fc.t_material.get("LotMax", "lotmax"), ge=0, description='最大批')
    lotround: float = Field(fc.default_lotround, alias=fc.t_material.get("LotRound", "lotround"), ge=0, description='取整')
    lotss: float = Field(fc.default_lotss, alias=fc.t_material.get("LotSS", "lotss"), ge=0, description='安全库存')
    lotpoint: float = Field(fc.default_lotpoint, alias=fc.t_material.get("LotPoint", "lotpoint"), ge=0, description='重订货点')
    lottop: float = Field(fc.default_lottop, alias=fc.t_material.get("LotTop", "lottop"), ge=0, description='最大库存点')
    planitem: str = Field(None, alias=fc.t_material.get("PlanItem", "planitem"), description='产品组')
    preday: int = Field(fc.default_preday, alias=fc.t_material.get("PreDay", "preday"), ge=0, description='向前冲销(天)')
    subday: int = Field(fc.default_subday, alias=fc.t_material.get("SubDay", "subday"), ge=0, description='向后冲销(天)')
    memo: str = Field(None,alias=fc.t_material.get("Memo", "memo"),  description='备注')
    # free1: str = Field(alias='Free1', max_length=255)
    # free2: str = Field(alias='Free2', max_length=255)
    # free3: str = Field(alias='Free3', max_length=255)
    
    @field_validator("leadday")
    def leadday_valid(cls, v, values):
        if v is None:
            v = fc.default_leadday_e if values.get("type") == "E" else fc.default_leadday_f
        return v

    @field_validator("grday")
    def grday_valid(cls, v, values):
        if v is None:
            v = fc.default_grday_e if values.get("type") == "E" else fc.default_grday_f
        return v

    @field_validator("abc")
    def abc_valid(cls, v, values):
        if v is None:
            v = "A" if values.get("type") == "E" else "B"
        return v

    class Config:
        title = "验证规则 - 物料"
        


class AcceptWorkcenter(BaseModel):
    workcenter: str = Field(..., alias=fc.t_workcenter.get("WorkCenter", "workcenter"), max_length=32, description="工作中心代码")
    workcentername: str = Field(..., alias=fc.t_workcenter.get("WorkCenterName", "workcentername"), max_length=255, description="工作中心名称")
    pri_wc: int = Field(None, alias=fc.t_workcenter.get("Pri_Wc", "pri_wc"), description='优先级')
    bottleneck: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("Bottleneck", "bottleneck"), max_length=1, description='瓶颈')
    sortno: str = Field(None, alias=fc.t_workcenter.get("SortNo", "sortno"), max_length=4, description="序号")
    plant: str = Field(None, alias=fc.t_workcenter.get("Plant", "plant"), max_length=32, description="工厂")
    location: str = Field(None, alias=fc.t_workcenter.get("Location", "location"), max_length=32, description="车间")
    finite: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("Finite", "finite"), max_length=1, description='有限')
    type: Literal["N", "Y"] = Field(None, alias=fc.t_workcenter.get("Type", "type"), max_length=32, description="首页显示")
    capnum: int = Field(None, alias=fc.t_workcenter.get("CapNum", "capnum"), gt=0, description="默认机台数")
    capmax: int = Field(None, alias=fc.t_workcenter.get("CapMax", "capmax"), gt=0, description="最大机台数")
    worker: float = Field(None, alias=fc.t_workcenter.get("Worker", "worker"), ge=0, description='工时')
    setupno: str = Field(None, alias=fc.t_workcenter.get("SetupNo", "setupno"), max_length=6, description='切换组别')
    grpno: str = Field(None, alias=fc.t_workcenter.get("GrpNo", "grpno"), max_length=6, description='同组号')
    memo: str = Field(None, alias=fc.t_workcenter.get("Memo", "memo"), max_length=255, description="备注")
    
    class Config:
        title = "验证规则 - 工作中心"



class AcceptMatWc(BaseModel):
    materialno: str = Field(..., alias=fc.t_mat_wc.get("MaterialNo", "materialno"), max_length=64, description='料号')
    matver: str = Field(fc.default_matver, alias=fc.t_mat_wc.get("MatVer", "matver"), max_length=4, description='产线版本')
    itemno: str = Field(..., alias=fc.t_mat_wc.get("ItemNo", "itemno"), max_length=6, description='工序项目')
    workcenter: str = Field(..., alias=fc.t_mat_wc.get("WorkCenter", "workcenter"), max_length=32, description='工作中心')
    sortno: int = Field(..., alias=fc.t_mat_wc.get("SortNo", "sortno"), ge=0, description='序号')
    basesec: int = Field(..., alias=fc.t_mat_wc.get("BaseSec", "basesec"), ge=0, description='节拍T/T(秒/100)')
    fixqty: int = Field(0, alias=fc.t_mat_wc.get("FixQty", "fixqty"), ge=0, description='额定量')
    fixsec: int = Field(0, alias=fc.t_mat_wc.get("FixSec", "fixsec"), ge=0, description='额定时间(秒)')
    sf: Literal["S", "F"] = Field("F", alias=fc.t_mat_wc.get("SF", "sf"), max_length=1, description='并行S/串行F')
    offsetsec: int = Field(0, alias=fc.t_mat_wc.get("OffsetSec", "offsetsec"), description='偏置+/-(秒)')
    memo: str = Field(None, alias=fc.t_mat_wc.get("Memo", "memo"), max_length=255, description='备注')

    class Config:
        title = "验证规则 - 工序"



class AcceptMatVer(BaseModel):
    materialno: str = Field(..., alias=fc.t_mat_ver.get("MaterialNo", "materialno"), max_length=64, description='料号')
    matver: str = Field(fc.default_matver, alias=fc.t_mat_ver.get("MatVer", "matver"), max_length=4, description='产线版本号')
    lotfrom: int = Field(0, alias=fc.t_mat_ver.get("LotFrom", "lotfrom"), description='批量起点')
    lotto: int = Field(9999999, alias=fc.t_mat_ver.get("LotTo", "lotto"), description='批量终点')
    priority: int = Field(1, alias=fc.t_mat_ver.get("Priority", "priority"), description='优先级')
    refno: str = Field(None, alias=fc.t_mat_ver.get("RefNo", "refno"), max_length=64, description='MTO订单号/认证线')
    active: Literal["N", "Y"] = Field("Y", alias=fc.t_mat_ver.get("Active", "active"), max_length=1, description='生效')
    memo: str = Field(None, alias=fc.t_mat_ver.get("Memo", "memo"), max_length=255, description='备注')

    class Config:
        title = "验证规则 - 产线版本"



class AcceptMatWcBom(BaseModel):
    productno: str = Field(..., alias=fc.t_mat_wc_bom.get("ProductNo", "productno"), max_length=64, description='产品料号')
    matver: str = Field(fc.default_matver, alias=fc.t_mat_wc_bom.get("MatVer", "matver"), max_length=4, description='产线版本')
    itemno: str = Field(..., alias=fc.t_mat_wc_bom.get("ItemNo", "itemno"), max_length=6, description='工序项目')
    materialno: str = Field(..., alias=fc.t_mat_wc_bom.get("MaterialNo", "materialno"), max_length=64, description='子件料号')
    qty: float = Field(..., alias=fc.t_mat_wc_bom.get("Qty", "qty"), ge=0, description='')
    offsethour: int = Field(0, alias=fc.t_mat_wc_bom.get("OffsetHour", "offsethour"), description='偏置+/-(小时)')
    treeno: int = Field(None, alias=fc.t_mat_wc_bom.get("TreeNo", "treeno"), description='')
    mto: Literal["N", "Y"] = Field("N", alias=fc.t_mat_wc_bom.get("MTO", "mto"), max_length=1, description='Y/N')
    scrap: float = Field(0, alias=fc.t_mat_wc_bom.get("Scrap", "scrap"), description='%')
    alt: Literal["N", "Y"] = Field("N", alias=fc.t_mat_wc_bom.get("Alt", "alt"), max_length=1, description='Y/N是否是替代')
    memo: str = Field(None, alias=fc.t_mat_wc_bom.get("Memo", "memo"), max_length=255, description='备注')

    class Config:
        title = "验证规则 - 工序BOM"


class AcceptSupply(BaseModel):
    materialno: str = Field(..., alias=fc.t_supply.get("MaterialNo", "materialno"), max_length=64, description='料号')
    supplyno: str = Field(..., alias=fc.t_supply.get("SupplyNo", "supplyno"), max_length=64, description='供应单号')
    matver: Optional[str] = Field(None, alias=fc.t_supply.get("MatVer", "matver"), max_length=32, description='产线版本')
    itemno: str = Field(None, alias=fc.t_supply.get("ItemNo", "itemno"), max_length=6, description='项目号')
    type: Literal["PL", "MO", "ST", "PO"] = Field("MO", alias=fc.t_supply.get("Type", "type"), max_length=64, description='类型 PL-生产计划 MO-生产工单 ST-库存 PO-采购订单')
    category: Literal["MTO", "MTS"] = Field(None, alias=fc.t_supply.get("Category", "category"), max_length=32, description='分类(MTO/MTS)')
    priority: int = Field(1, alias=fc.t_supply.get("Priority", "priority"), description='优先级')
    status: Literal["NEW", "CRE", "SCH", "REL", "PNF", "CMP"] = Field(None, alias=fc.t_supply.get("Status", "status"), max_length=32, description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    avail_qty: float = Field(..., alias=fc.t_supply.get("Avail_Qty", "avail_qty"), ge=0, description='可用数量')
    create_date: Optional[str] = Field(None, alias=fc.t_supply.get("Create_Date", "create_date"), description='创建日期')
    avail_date: str = Field(..., alias=fc.t_supply.get("Avail_Date", "avail_date"), description='可用日期 / 开工日期')
    dt_req: Optional[str] = Field(..., alias=fc.t_supply.get("DT_Req", "dt_req"), description='需求日期 / 完工日期')
    avail_end_date: Optional[str] = Field(None, alias=fc.t_supply.get("Avail_End_Date", "avail_end_date"), description='可用结束日期')
    batchno: Optional[str] = Field(None, alias=fc.t_supply.get("BatchNo", "batchno"), max_length=64, description='批次号')
    vendorno: Optional[str] = Field(None, alias=fc.t_supply.get("VendorNo", "vendorno"), max_length=64, description='供应商编号')
    partnerno: Optional[str] = Field(None, alias=fc.t_supply.get("PartnerNo", "partnerno"), max_length=64, description='合作商编号')
    partnername: Optional[str] = Field(None, alias=fc.t_supply.get("PartnerName", "partnername"), max_length=255, description='合作商名称')
    # free1: Optional[str] = Field(None, alias=fc.t_supply.get("free1", "free1"), max_length=255, description='自由字段1')
    # free2: Optional[str] = Field(None, alias=fc.t_supply.get("free2", "free2"), max_length=255, description='自由字段2')
    # free3: Optional[str] = Field(None, alias=fc.t_supply.get("free3", "free3"), max_length=255, description='自由字段3')
    memo: Optional[str] = Field(None, alias=fc.t_supply.get("Memo", "memo"), max_length=255, description='备注')
    # sys_date: Optional[str] = Field(None, alias=fc.t_supply.get("sys_date", "sys_date"), description='系统日期')
    # sys_user: Optional[str] = Field(None, alias=fc.t_supply.get("sys_user", "sys_user"), max_length=32, description='系统用户')
    # sys_stamp: Optional[str] = Field(None, alias=fc.t_supply.get("sys_stamp", "sys_stamp"), description='系统时间戳')

    class Config:
        title = "验证规则 - 供应"


class AcceptDemand(BaseModel):
    materialno: str = Field(..., alias=fc.t_demand.get("MaterialNo", "materialno"), max_length=64, description='料号')
    demandno: str = Field(..., alias=fc.t_demand.get("DemandNo", "demandno"), max_length=64, description='需求单号')
    itemno: str = Field(..., alias=fc.t_demand.get("ItemNo", "itemno"), max_length=6, description='项目号')
    type: Literal["SO", "DM", "RS", "FC", "SS"] = Field("SO", alias=fc.t_demand.get("Type", "type"), max_length=64, description='类型 SO-销售订单 DM-计划需求 RS-工单预留 FC-预测 SS-安全库存')
    category: Literal["MTO", "MTS"] = Field(None, alias=fc.t_demand.get("Category", "category"), max_length=32, description='分类(MTO/MTS)')
    priority: int = Field(..., alias=fc.t_demand.get("Priority", "priority"), description='优先级')
    workcenter: str = Field(..., alias=fc.t_demand.get("WorkCenter", "workcenter"), max_length=32, description='工作中心')
    status: Literal["NEW", "CRE", "SCH", "REL", "PNF", "CMP"] = Field(None, alias=fc.t_demand.get("Status", "status"), max_length=32, description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    req_qty: float = Field(..., alias=fc.t_demand.get("Req_Qty", "req_qty"), gt=0, description='需求数量')
    # create_date: Optional[str] = Field(None, alias=fc.t_demand.get("Create_Date", "create_date"), description='创建日期')
    req_date: datetime = Field(..., alias=fc.t_demand.get("Req_Date", "req_date"), description='需求日期')
    refno: Optional[str] = Field(None, alias=fc.t_demand.get("RefNo", "refno"), max_length=64, description='MTO订单号')
    partnerno: Optional[str] = Field(None, alias=fc.t_demand.get("PartnerNo", "partnerno"), max_length=64, description='合作商编号')
    partnername: Optional[str] = Field(None, alias=fc.t_demand.get("PartnerName", "partnername"), max_length=255, description='合作商名称')
    # altgrp: Optional[str] = Field(None, alias=fc.t_demand.get("AltGrp", "altgrp"), max_length=64, description='替代组')
    # ori_itemno: Optional[str] = Field(None, alias=fc.t_demand.get("Ori_ItemNo", "ori_itemno"), max_length=6, description='原始项目号')
    ori_qty: Optional[float] = Field(None, alias=fc.t_demand.get("Ori_Qty", "ori_qty"), ge=0, description='原始需求数量')
    memo: Optional[str] = Field(None, alias=fc.t_demand.get("Memo", "memo"), max_length=255, description='备注')

    class Config:
        title = "验证规则 - 需求"
