from datetime import datetime
import enum
from typing import Literal, Optional#, List, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator#, ValidationError

from config import uservar as uv, globalconst as gc


class AcceptMaterial(BaseModel):
    materialno: str = Field(..., alias=uv.t_material.get("MaterialNo", "materialno"), description="料号", example="M001")
    description: str = Field(..., alias=uv.t_material.get("Description", "description"), description="物料名称", example="测试物料A")
    size: str = Field(None, alias=uv.t_material.get("Size", "size"), description="规格", example="100x100mm")
    plant: str = Field(..., alias=uv.t_material.get("Plant", "plant"), example=uv.default_plant, description='工厂')
    planner: str = Field(uv.default_planner, alias=uv.t_material.get("Planner", "planner"), description="计划员", example="张三")
    fifo: int = Field(uv.default_fifo, alias=uv.t_material.get("FIFO", "fifo"), ge=0, le=1, description='1-FIFO 0-最近原则')
    leadday: int = Field(alias=uv.t_material.get("LeadDay", "leadday"), ge=0, description="交期（天）", example=7)
    expday: int = Field(uv.default_expday, alias=uv.t_material.get("ExpDay", "expday"), ge=0, description="保质期（天）", example=365)
    grday: int = Field(alias=uv.t_material.get("GRDay", "grday"), ge=0, description="收货质检（天）", example=1)
    abc: str = Field(alias=uv.t_material.get("ABC", "abc"), enum=["A", "B", "C"], example="A", description="ABC分类")
    unit: str = Field(alias=uv.t_material.get("Unit", "unit"), description='单位', example="PCS")
    price: Decimal = Field(uv.default_price, alias=uv.t_material.get("Price", "price"), description="价格", example=100.50)
    groupno: str = Field(..., alias=uv.t_material.get("GroupNo", "groupno"), description="型号", example="G001")
    type: str = Field(... if uv.myaps_is_pro else None, alias=uv.t_material.get("type", "type"), enum=["E", "F"], example="E", description="物料类型  E-自制件 F-采购件")
    phantom: str = Field(uv.default_phantom, alias=uv.t_material.get("Phantom", "phantom"), enum=["N", "Y"], example="N", description='虚拟件')
    phantommin: int = Field(uv.default_phantommin, alias=uv.t_material.get("PhantomMin", "phantommin"), ge=0, description='虚拟时间(Minute)', example=0)
    firmday: int = Field(uv.default_firmday, alias=uv.t_material.get("FirmDay", "firmday"), ge=0, description="固定天数", example=0)
    daygap: int = Field(uv.default_daygap, alias=uv.t_material.get("DayGap", "daygap"), ge=0, description='MTO拆分天数', example=1)
    candelay: str = Field(uv.default_candelay, alias=uv.t_material.get("CanDelay", "candelay"), enum=["N", "Y"], example="N", description='可否延迟')
    lotsize: str = Field(
        uv.default_lotsize, alias=uv.t_material.get("LotSize", "lotsize"),
        enum=list(gc.LOT_SIZE.keys()),
        example="EX", description='批量')
    lotfix: float = Field(uv.default_lotfix, alias=uv.t_material.get("LotFix", "lotfix"), ge=0, description='固定批', example=0.0)
    lotmin: float = Field(uv.default_lotmin, alias=uv.t_material.get("LotMin", "lotmin"), ge=0, description='最小批', example=0.0)
    lotmax: float = Field(uv.default_lotmax, alias=uv.t_material.get("LotMax", "lotmax"), ge=0, description='最大批', example=0.0)
    lotround: float = Field(uv.default_lotround, alias=uv.t_material.get("LotRound", "lotround"), ge=0, description='取整', example=0.0)
    lotss: float = Field(uv.default_lotss, alias=uv.t_material.get("LotSS", "lotss"), ge=0, description='安全库存', example=0.0)
    lotpoint: float = Field(uv.default_lotpoint, alias=uv.t_material.get("LotPoint", "lotpoint"), ge=0, description='重订货点', example=0.0)
    lottop: float = Field(uv.default_lottop, alias=uv.t_material.get("LotTop", "lottop"), ge=0, description='最大库存点', example=0.0)
    planitem: str = Field(None, alias=uv.t_material.get("PlanItem", "planitem"), description='产品组', example="PI001")
    preday: int = Field(uv.default_preday, alias=uv.t_material.get("PreDay", "preday"), ge=0, description='向前冲销(天)', example=999)
    subday: int = Field(uv.default_subday, alias=uv.t_material.get("SubDay", "subday"), ge=0, description='向后冲销(天)', example=999)
    memo: str = Field(None,alias=uv.t_material.get("Memo", "memo"),  description='备注', example="无特殊要求")

    class Config:
        title = "验证规则 - 物料"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "description": "测试物料A",
                "size": "100x100mm",
                "plant": "1600",
                "planner": "haida",
                "fifo": 1,
                "leadday": 7,
                "expday": 365,
                "grday": 1,
                "abc": "A",
                "unit": "PCS",
                "price": 100.50,
                "groupno": "G001",
                "type": "E",
                "phantom": "N",
                "memo": "标准物料"
            }
        }
    
    @model_validator(mode="before")
    def model_valid(self):
        if not self.get("leadday"):
            self["leadday"] = uv.default_leadday_e if self.get("type") == "E" else uv.default_leadday_f
        if not self.get("grday"):
            self["grday"] = uv.default_grday_e if self.get("type") == "E" else uv.default_grday_f
        if not self.get("abc"):
            self["abc"] = "A" if self.get("type") == "E" else "B"
        return self
        


class AcceptWorkcenter(BaseModel):
    workcenter: str = Field(..., alias=uv.t_workcenter.get("WorkCenter", "workcenter"), max_length=32, description="工作中心代码", example="WC001")
    workcentername: str = Field(..., alias=uv.t_workcenter.get("WorkCenterName", "workcentername"), max_length=255, description="工作中心名称", example="装配车间")
    pri_wc: int = Field(1, alias=uv.t_workcenter.get("Pri_Wc", "pri_wc"), description='优先级', example=1)
    bottleneck: str = Field("N", alias=uv.t_workcenter.get("Bottleneck", "bottleneck"), enum=["N", "Y"], example="N", description='瓶颈')
    sortno: str = Field(None, alias=uv.t_workcenter.get("SortNo", "sortno"), max_length=4, description="序号", example="0001")
    plant: str = Field(uv.default_plant, alias=uv.t_workcenter.get("Plant", "plant"), max_length=32, description="工厂", example="1600")
    location: str = Field(None, alias=uv.t_workcenter.get("Location", "location"), max_length=32, description="车间", example="A区")
    finite: str = Field(None, alias=uv.t_workcenter.get("Finite", "finite"), enum=list(gc.YES_NO.keys()), example="N", description='有限')
    type: str = Field(None, alias=uv.t_workcenter.get("Type", "type"), enum=list(gc.YES_NO.keys()), example="N", description="首页显示")
    capnum: int = Field(None, alias=uv.t_workcenter.get("CapNum", "capnum"), gt=0, description="默认机台数", example=5)
    capmax: int = Field(None, alias=uv.t_workcenter.get("CapMax", "capmax"), gt=0, description="最大机台数", example=10)
    worker: float = Field(None, alias=uv.t_workcenter.get("Worker", "worker"), ge=0, description='工时', example=8.0)
    setupno: str = Field(None, alias=uv.t_workcenter.get("SetupNo", "setupno"), max_length=6, description='切换组别', example="S001")
    grpno: str = Field(None, alias=uv.t_workcenter.get("GrpNo", "grpno"), max_length=6, description='同组号', example="G001")
    memo: str = Field(None, alias=uv.t_workcenter.get("Memo", "memo"), max_length=255, description="备注", example="标准工作中心")
    
    class Config:
        title = "验证规则 - 工作中心"
        json_schema_extra = {
            "example": {
                "workcenter": "WC001",
                "workcentername": "装配车间",
                "pri_wc": 1,
                "bottleneck": "N",
                "plant": "1600",
                "capnum": 5,
                "capmax": 10,
                "worker": 8.0,
                "memo": "标准工作中心"
            }
        }

    @model_validator(mode="before")
    def model_valid(self):
        if not self.get("sortno"):
            workcenter = self.get("workcenter")
            self["sortno"] = uv.workcenter_sort.get(workcenter, '')
        return self


class AcceptMatWc(BaseModel):
    materialno: str = Field(..., alias=uv.t_mat_wc.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    matver: str = Field(..., alias=uv.t_mat_wc.get("MatVer", "matver"), max_length=4, example=uv.example_matver, description='产线版本')
    itemno: str = Field(..., alias=uv.t_mat_wc.get("ItemNo", "itemno"), max_length=6, description='工序项目', example="0010")
    workcenter: str = Field(..., alias=uv.t_mat_wc.get("WorkCenter", "workcenter"), max_length=32, description='工作中心', example="WC001")
    sortno: int = Field(..., alias=uv.t_mat_wc.get("SortNo", "sortno"), ge=0, description='序号', example=1)
    basesec: int = Field(..., alias=uv.t_mat_wc.get("BaseSec", "basesec"), ge=0, description='节拍T/T(秒/100)', example=600)
    fixqty: int = Field(0, alias=uv.t_mat_wc.get("FixQty", "fixqty"), ge=0, description='额定量', example=100)
    fixsec: int = Field(0, alias=uv.t_mat_wc.get("FixSec", "fixsec"), ge=0, description='额定时间(秒)', example=300)
    sf: str = Field(..., alias=uv.t_mat_wc.get("SF", "sf"), enum=["S", "F"], example="F", description='并行S/串行F')
    offsetsec: int = Field(0, alias=uv.t_mat_wc.get("OffsetSec", "offsetsec"), description='偏置+/-(秒)', example=0)
    memo: str = Field(None, alias=uv.t_mat_wc.get("Memo", "memo"), max_length=255, description='备注', example="标准工序")

    class Config:
        title = "验证规则 - 工序"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "matver": "V1",
                "itemno": "0010",
                "workcenter": "WC001",
                "sortno": 1,
                "basesec": 600,
                "fixqty": 100,
                "fixsec": 300,
                "sf": "F",
                "offsetsec": 0,
                "memo": "标准工序"
            }
        }



class AcceptMatVer(BaseModel):
    materialno: str = Field(..., alias=uv.t_mat_ver.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    matver: str = Field(..., alias=uv.t_mat_ver.get("MatVer", "matver"), example=uv.example_matver, max_length=4, description='产线版本号')
    lotfrom: int = Field(0, alias=uv.t_mat_ver.get("LotFrom", "lotfrom"), description='批量起点', example=1)
    lotto: int = Field(9999999, alias=uv.t_mat_ver.get("LotTo", "lotto"), description='批量终点', example=9999999)
    priority: int = Field(1, alias=uv.t_mat_ver.get("Priority", "priority"), description='优先级', example=1)
    refno: str = Field(None, alias=uv.t_mat_ver.get("RefNo", "refno"), max_length=64, description='MTO订单号/认证线', example="SO123456")
    active: str = Field("Y", alias=uv.t_mat_ver.get("Active", "active"), enum=list(gc.YES_NO.keys()), example="Y", description='生效')
    memo: str = Field(None, alias=uv.t_mat_ver.get("Memo", "memo"), max_length=255, description='备注', example="标准版本")

    class Config:
        title = "验证规则 - 产线版本"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "matver": "V1",
                "lotfrom": 1,
                "lotto": 9999999,
                "priority": 1,
                "active": "Y",
                "memo": "标准版本"
            }
        }



class AcceptMatWcBom(BaseModel):
    productno: str = Field(..., alias=uv.t_mat_wc_bom.get("ProductNo", "productno"), max_length=64, description='产品料号', example="P001")
    matver: str = Field(..., alias=uv.t_mat_wc_bom.get("MatVer", "matver"), example=uv.example_matver, max_length=4, description='产线版本')
    itemno: str = Field(..., alias=uv.t_mat_wc_bom.get("ItemNo", "itemno"), max_length=6, description='工序项目', example="0010")
    materialno: str = Field(..., alias=uv.t_mat_wc_bom.get("MaterialNo", "materialno"), max_length=64, description='子件料号', example="M001")
    qty: float = Field(..., alias=uv.t_mat_wc_bom.get("Qty", "qty"), ge=0, description='数量', example=2.0)
    offsethour: int = Field(0, alias=uv.t_mat_wc_bom.get("OffsetHour", "offsethour"), description='偏置+/-(小时)', example=0)
    treeno: int = Field(None, alias=uv.t_mat_wc_bom.get("TreeNo", "treeno"), description='层级', example=1)
    mto: str = Field("N", alias=uv.t_mat_wc_bom.get("MTO", "mto"), enum=list(gc.YES_NO.keys()), example="N", description='MTO')
    scrap: float = Field(0, alias=uv.t_mat_wc_bom.get("Scrap", "scrap"), description='报废率%', example=0.0)
    alt: str = Field("N", alias=uv.t_mat_wc_bom.get("Alt", "alt"), enum=list(gc.YES_NO.keys()), example="N", description='Y/N是否是替代')
    memo: str = Field(None, alias=uv.t_mat_wc_bom.get("Memo", "memo"), max_length=255, description='备注', example="标准BOM组件")

    class Config:
        title = "验证规则 - BOM"
        json_schema_extra = {
            "example": {
                "productno": "P001",
                "matver": "V1",
                "itemno": "0010",
                "materialno": "M001",
                "qty": 2.0,
                "offsethour": 0,
                "treeno": 1,
                "mto": "N",
                "scrap": 0.0,
                "alt": "N",
                    "memo": "标准BOM组件"
                }
            }



class AcceptMold(BaseModel):
    moldno: str = Field(..., alias=uv.t_mold.get("MoldNo", "moldno"), max_length=64, description='模具编号', example="MOLD001")
    moldname: str = Field(..., alias=uv.t_mold.get("MoldName", "moldname"), max_length=64, description='模具名称', example="测试模具A")
    type: str = Field(..., alias=uv.t_mold.get("Type", "type"), example="T1", max_length=4, description='类型')
    status: str = Field(..., alias=uv.t_mold.get("Status", "status"), max_length=6, description='状态', example="AVL")
    moldnum: int = Field(..., alias=uv.t_mold.get("MoldNum", "moldnum"), ge=0, description='模具穴数', example=4)
    qty: int = Field(..., alias=uv.t_mold.get("Qty", "qty"), ge=0, description='模具台数', example=2)
    memo: str = Field(None, alias=uv.t_mold.get("Memo", "memo"), max_length=255, description="备注", example="标准模具")
    
    class Config:
        title = "验证规则 - 模具"
        json_schema_extra = {
            "example": {
                "moldno": "MOLD001",
                "moldname": "测试模具A",
                "type": "T1",
                "status": "AVL",
                "moldnum": 4,
                "qty": 2,
                "memo": "标准模具"
            }
        }


class AcceptMatWcMold(BaseModel):
    materialno: str = Field(..., alias=uv.t_mat_wc_mold.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    workcenter: str = Field(..., alias=uv.t_mat_wc_mold.get("WorkCenter", "workcenter"), max_length=64, description='工作中心', example="WC001")
    moldno: str = Field(..., alias=uv.t_mat_wc_mold.get("MoldNo", "moldno"), max_length=64, description='模具编号', example="MOLD001")
    basesec: int = Field(..., alias=uv.t_mat_wc_mold.get("BaseSec", "basesec"), ge=0, description='节拍T/T(秒/100)', example=600)
    fixsec: int = Field(..., alias=uv.t_mat_wc_mold.get("FixSec", "fixsec"), ge=0, description='额定时间(秒)', example=300)
    priority: int = Field(..., alias=uv.t_mat_wc_mold.get("Priority", "priority"), description='优先级', example=1)
    memo: str = Field(None, alias=uv.t_mat_wc_mold.get("Memo", "memo"), max_length=255, description='备注', example="标准机台模具配置")

    class Config:
        title = "验证规则 - 机台模具"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "workcenter": "WC001",
                "moldno": "MOLD001",
                "basesec": 600,
                "fixsec": 300,
                "priority": 1,
                "memo": "标准机台模具配置"
            }
        }



class AcceptSupply(BaseModel):
    materialno: str = Field(..., alias=uv.t_supply.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    supplyno: str = Field(..., alias=uv.t_supply.get("SupplyNo", "supplyno"), max_length=64, description='供应单号', example="MO123456")
    matver: Optional[str] = Field(None, alias=uv.t_supply.get("MatVer", "matver"), max_length=32, example=uv.example_matver, description='产线版本')
    itemno: str = Field(None, alias=uv.t_supply.get("ItemNo", "itemno"), max_length=6, description='项目号', example="0010")
    type: str = Field(..., alias=uv.t_supply.get("Type", "type"), enum=list(gc.SUPPLY_TYPE.keys()), example="MO", description='类型 PL-生产计划 MO-生产工单 ST-库存 PO-采购订单')
    category: str = Field(None, alias=uv.t_supply.get("Category", "category"), enum=list(gc.PRODUCT_CATEGORY.keys()), example="MTO", description='分类(MTO/MTS)')
    priority: int = Field(..., alias=uv.t_supply.get("Priority", "priority"), description='优先级', example=1)
    status: str = Field(
        None, alias=uv.t_supply.get("Status", "status"),
        enum=list(gc.ORDER_STATUS.keys()),
        example="NEW", description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    avail_qty: float = Field(..., alias=uv.t_supply.get("Avail_Qty", "avail_qty"), ge=0, description='可用数量', example=100.0)
    create_date: Optional[str] = Field(None, alias=uv.t_supply.get("Create_Date", "create_date"), description='创建日期', example="2023-01-01")
    avail_date: str = Field(..., alias=uv.t_supply.get("Avail_Date", "avail_date"), description='可用日期 / 开工日期', example="2023-01-01")
    dt_req: Optional[str] = Field(..., alias=uv.t_supply.get("DT_Req", "dt_req"), description='需求日期 / 完工日期', example="2023-01-07")
    avail_end_date: Optional[str] = Field(None, alias=uv.t_supply.get("Avail_End_Date", "avail_end_date"), description='可用结束日期', example="2023-01-07")
    batchno: Optional[str] = Field(None, alias=uv.t_supply.get("BatchNo", "batchno"), max_length=64, description='批次号', example="BATCH001")
    vendorno: Optional[str] = Field(None, alias=uv.t_supply.get("VendorNo", "vendorno"), max_length=64, description='供应商编号', example="V001")
    partnerno: Optional[str] = Field(None, alias=uv.t_supply.get("PartnerNo", "partnerno"), max_length=64, description='合作商编号', example="P001")
    partnername: Optional[str] = Field(None, alias=uv.t_supply.get("PartnerName", "partnername"), max_length=255, description='合作商名称', example="合作伙伴A")
    memo: Optional[str] = Field(None, alias=uv.t_supply.get("Memo", "memo"), max_length=255, description='备注', example="标准供应单")
    # plno: Optional[str] = Field(None, alias=uv.t_supply.get("PlNo", "plno"), max_length=64, description='原PL（若传入此值则将对应的PL号改写成MO号，若索引不到原PL则新增MO）', example="PL123456")

    class Config:
        title = "验证规则 - 供应"
        extra = "allow"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "supplyno": "MO123456",
                "matver": "V1",
                "itemno": "0010",
                "type": "MO",
                "category": "MTO",
                "priority": 1,
                "status": "NEW",
                "avail_qty": 100.0,
                "avail_date": "2023-01-01",
                "dt_req": "2023-01-07",
                "memo": "标准生产工单"
            }
        }

    @model_validator(mode="before")
    def model_valid(self):
        if not self.get("itemno"):
            self["itemno"] = uv.default_itemno
        return self


class PatchPl(BaseModel):
    type: str = Field(..., example="MO", description='类型 PL-生产计划 MO-生产工单 ST-库存 PO-采购订单')
    plno: str = Field(..., max_length=64, description='PL号', example="PL123456")
    mono: str = Field(None, max_length=64, description='MO号', example="MO123456")
    status: str = Field(None, enum=list(gc.ORDER_STATUS.keys()), example="CRE", description=f'状态 {gc.ORDER_STATUS}')

    class Config:
        title = "验证规则 - 生产计划"
        extra = "allow"
        json_schema_extra = {
            "example": {
                "type": "MO",
                "plno": "PL123456",
                "mono": "MO123456",
                "status": "CRE"
            }
        }

    @model_validator(mode="before")
    def model_valid(self):
        if not self.get("mono"):
            self["mono"] = self["plno"]
        if not self.get("status"):
            self["status"] = "CRE"
        return self


class DeleteSupply(BaseModel):
    materialno: str = Field(..., alias=uv.t_supply.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    supplyno: str = Field(..., alias=uv.t_supply.get("SupplyNo", "supplyno"), max_length=64, description='供应单号', example="MO123456")



class AcceptDemand(BaseModel):
    materialno: str = Field(..., alias=uv.t_demand.get("MaterialNo", "materialno"), max_length=64, description='料号', example="M001")
    demandno: str = Field(..., alias=uv.t_demand.get("DemandNo", "demandno"), max_length=64, description='需求单号', example="SO123456")
    itemno: str = Field(..., alias=uv.t_demand.get("ItemNo", "itemno"), max_length=6, description='项目号（若类型为SO则可传入订单号或其他标识符，不超过6位）', example="0010")
    type: str = Field(..., alias=uv.t_demand.get("Type", "type"), enum=list(gc.DEMAND_TYPE.keys()), example="SO", description='类型 SO-销售订单 DM-计划需求 RS-工单预留 FC-预测 SS-安全库存')
    category: str = Field(..., alias=uv.t_demand.get("Category", "category"), enum=list(gc.PRODUCT_CATEGORY.keys()), example="MTO", description='分类(MTO/MTS)')
    priority: int = Field(..., alias=uv.t_demand.get("Priority", "priority"), description='优先级', example=1)
    workcenter: str = Field(None, alias=uv.t_demand.get("WorkCenter", "workcenter"), max_length=32, description='工作中心', example="WC001")
    status: str = Field(..., alias=uv.t_demand.get("Status", "status"), enum=list(gc.ORDER_STATUS.keys()), example="NEW", description='状态 NEW-新增 CRE-已创建 SCH-计划 REL-已发布 PNF-已报工, CMP-已完成')
    req_qty: float = Field(..., alias=uv.t_demand.get("Req_Qty", "req_qty"), description='需求数量（须为负数，若输入正数则自动转为负数）', example=-100.0)
    req_date: datetime = Field(..., alias=uv.t_demand.get("Req_Date", "req_date"), description='需求日期', example="2023-01-07T10:00:00")
    refno: Optional[str] = Field(None, alias=uv.t_demand.get("RefNo", "refno"), max_length=64, description='MTO订单号', example="MTO123456")
    partnerno: Optional[str] = Field(None, alias=uv.t_demand.get("PartnerNo", "partnerno"), max_length=64, description='合作商编号', example="P001")
    partnername: Optional[str] = Field(None, alias=uv.t_demand.get("PartnerName", "partnername"), max_length=255, description='合作商名称', example="客户A")
    ori_qty: Optional[float] = Field(None, alias=uv.t_demand.get("Ori_Qty", "ori_qty"), ge=0, description='原始需求数量', example=100.0)
    memo: Optional[str] = Field(None, alias=uv.t_demand.get("Memo", "memo"), max_length=255, description='备注', example="标准销售订单")

    class Config:
        title = "验证规则 - 需求"
        json_schema_extra = {
            "example": {
                "materialno": "M001",
                "demandno": "SO123456",
                "itemno": "0010",
                "type": "SO",
                "category": "MTO",
                "priority": 1,
                "workcenter": "WC001",
                "status": "NEW",
                "req_qty": -100.0,
                "req_date": "2023-01-07T10:00:00",
                "refno": "MTO123456",
                "ori_qty": 100.0,
                "memo": "标准销售订单"
            }
        }

    @model_validator(mode="before")
    def model_valid(self):
        req_qty = float(self.get("req_qty", 0))
        if req_qty > 0:
            self["req_qty"] = -1 * req_qty
        return self